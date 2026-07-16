"""
PDL-entity-driven roster and flow wiring (hybrid archetype resolution).

Resolution order for each PDL entity:
    1. ID_OVERRIDES[id]                  explicit: tuned role/params, or a
                                         type+sector collision (oil_mills vs feed_mills)
    2. KIND_ARCHETYPES[(type, sector)]   generic "kind library": a new same-kind
                                         entity (china_farms) maps with no edits
    3. EXCLUDE                           in the PDL but deliberately not a node-agent
                                         (edge origins / not-yet-modelled)
    4. otherwise                         unmodelled -> skipped

Synthetic agents (wholesalers, feed_traders) have no PDL entity and are always
created. Sea crossings are edges, materialised as sea-lane agents (TRANSITIONAL_SEA).

The model imports build_roster / build_flow_adjacency / execution_order to drive
create(), setup(), and the per-step loop.
"""
from __future__ import annotations
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from .agents import (
    Farmer, Trader, Transport, Process,
    ROLE_PRODUCER, ROLE_CONSUMER,
    ROLE_WHOLESALER, ROLE_FEED_TRADER,
    ROLE_SA_SANTOS, ROLE_SA_PARANAGUA, ROLE_EU_RTM, ROLE_EU_HAM,
    ROLE_SEA_SANTOS, ROLE_SEA_PARANAGUA, ROLE_SEA_ARG, ROLE_SEA_USA,
    ROLE_PROCESSOR, ROLE_FEED_MANUFACTURER,
)
from .pdl_loader import PDLLoader
from .scenario import SupplyChainScenario


# ---------------------------------------------------------------------------
# Nodes: PDL entity -> agent archetype
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Archetype:
    name: str              # model attribute name (parity with the current roster)
    agent_class: type
    role: str
    count_attr: str        # scenario attribute holding the instance count
    # Declarative agent init, applied to instances by model.setup(); agents
    # never read it. Keys (all optional):
    #   "bindings"        semantic slot -> PDL (entity, impact_field) verbatim.
    #                     Cross-entity dependencies only — the "capacity" slot
    #                     (an agent's OWN entity) stays entity-driven in setup().
    #   "scenario_attrs"  agent attribute <- scenario attribute name
    #   "attrs"           agent attribute <- literal value
    # compare=False keeps eq/hash on the identity fields: a dict field would
    # make the frozen class unhashable, and build_roster keys dicts by Archetype.
    params: Mapping[str, Any] = field(default_factory=dict, compare=False)


# ---------------------------------------------------------------------------
# Archetype params: the ROLE_BINDINGS tables and post_setup `if role ==` values
# that used to live in the agent files. Bindings are cross-entity dependency
# slots only (fertilizer -> input cost scaling, energy -> freight cost scaling).
# Fragments are shared by reference across archetypes.
# ---------------------------------------------------------------------------

_ENERGY = {"energy": ("gas_supply", "price")}   # gas price scales freight operating costs

_FARMER_BRA = {
    "bindings":       {"fertilizer": ("fertilizer_supply", "price")},
    "scenario_attrs": {"fixed_costs": "fixed_costs_bra_farmer",
                       "margin":      "margin_bra_farmer",
                       "size_sigma":  "farm_size_sigma_bra"},
    "attrs":          {"base_yield": 100.0},    # placeholder; loaded from data later
}
_FARMER_ARG = {
    "scenario_attrs": {"fixed_costs": "fixed_costs_arg_farmer",
                       "margin":      "margin_arg_farmer",
                       "size_sigma":  "farm_size_sigma_arg"},
    "attrs":          {"base_yield": 100.0},
}
_FARMER_USA = {
    "scenario_attrs": {"fixed_costs": "fixed_costs_usa_farmer",
                       "margin":      "margin_usa_farmer",
                       "size_sigma":  "farm_size_sigma_usa"},
    "attrs":          {"base_yield": 100.0},
}
_FARMER_EU = {    # end consumer: no margin; base_yield stays 0.0 -> buyer init
    "scenario_attrs": {"fixed_costs": "fixed_costs_eu_farmer",
                       "size_sigma":  "farm_size_sigma_eu"},
}
_TRANSPORT_SA = {
    "bindings":       _ENERGY,
    "scenario_attrs": {"fixed_costs": "fixed_costs_transport_sa"},
    "attrs":          {"capacity": 500.0},
}
_TRANSPORT_EU = {
    "bindings":       _ENERGY,
    "scenario_attrs": {"fixed_costs": "fixed_costs_transport_eu"},
    "attrs":          {"capacity": 500.0},
}
_PROCESSOR = {
    "scenario_attrs": {"fixed_costs": "fixed_costs_processor",
                       "margin":      "margin_processor"},
    "attrs":          {"conversion_ratio": 0.8},    # ~80 % meal yield from raw soja
}
_FEED_MFR = {
    "scenario_attrs": {"fixed_costs": "fixed_costs_feed_manufacturer",
                       "margin":      "margin_feed_manufacturer"},
    "attrs":          {"conversion_ratio": 1.0},    # no significant yield loss yet
}
_WHOLESALER = {
    "scenario_attrs": {"fixed_costs":      "fixed_costs_wholesaler",
                       "margin":           "margin_wholesaler",
                       "storage_capacity": "wholesaler_storage_capacity"},
}
_FEED_TRADER = {
    "scenario_attrs": {"fixed_costs": "fixed_costs_feed_trader",
                       "margin":      "margin_feed_trader"},
}


# generic kind library: (type, sector) -> default archetype
KIND_ARCHETYPES: dict[tuple[str, str], Archetype] = {
    ("region", "agriculture"):       Archetype("arg_farmers", Farmer, ROLE_PRODUCER, "n_arg_farmers", _FARMER_ARG),
    ("infrastructure", "logistics"): Archetype("transport_sa_santos", Transport, ROLE_SA_SANTOS, "n_transport_sa_santos", _TRANSPORT_SA),
    ("manufacturer", "processing"):  Archetype("processors", Process, ROLE_PROCESSOR, "n_processors", _PROCESSOR),
    ("manufacturer", "agriculture"): Archetype("eu_farmers", Farmer, ROLE_CONSUMER, "n_eu_farmers", _FARMER_EU),
}

# id overrides: tuned role/count, or type+sector collisions
ID_OVERRIDES: dict[str, Archetype] = {
    "brazil_farms":   Archetype("bra_farmers", Farmer, ROLE_PRODUCER, "n_bra_farmers", _FARMER_BRA),
    "us_farms":       Archetype("usa_farmers", Farmer, ROLE_PRODUCER, "n_usa_farmers", _FARMER_USA),
    # argentina_farms -> region/agriculture default (arg_farmers)
    "paranagua_port": Archetype("transport_sa_paranagua", Transport, ROLE_SA_PARANAGUA, "n_transport_sa_paranagua", _TRANSPORT_SA),
    "rotterdam_port": Archetype("transport_eu_rtm", Transport, ROLE_EU_RTM, "n_transport_eu_rtm", _TRANSPORT_EU),
    "hamburg_port":   Archetype("transport_eu_ham", Transport, ROLE_EU_HAM, "n_transport_eu_ham", _TRANSPORT_EU),
    # santos_port -> infrastructure/logistics default (transport_sa_santos)
    "feed_mills":     Archetype("feed_manufacturers", Process, ROLE_FEED_MANUFACTURER, "n_feed_manufacturers", _FEED_MFR),
    # eu_oil_mills -> manufacturer/processing default (processors)
}

# present in PDL but deliberately not a node-agent (yet)
EXCLUDE: frozenset[str] = frozenset({
    "us_gulf_ports",   # origin of the USA sea edge, not a handler node today
})

# synthetic agents (no PDL entity), always created
SYNTHETIC: list[Archetype] = [
    Archetype("wholesalers", Trader, ROLE_WHOLESALER, "n_wholesalers", _WHOLESALER),
    Archetype("feed_traders", Trader, ROLE_FEED_TRADER, "n_feed_traders", _FEED_TRADER),
]


def resolve(entity: dict) -> Archetype | None:
    """Resolve one PDL entity dict to an Archetype, or None if unmodelled."""
    eid = entity.get("id")
    if eid in EXCLUDE:
        return None
    if eid in ID_OVERRIDES:
        return ID_OVERRIDES[eid]
    return KIND_ARCHETYPES.get((entity.get("type"), entity.get("sector")))


# ---------------------------------------------------------------------------
# Edges: which PDL stages are sea crossings (carrier edges)
# ---------------------------------------------------------------------------
# A stage from supply_chains.stages is a crossing iff its two endpoints sit on
# different (known) continents; every other stage is a land / process link with
# no carrier. A region-swap PDL only needs its new location added to
# LOCATION_CONTINENT (e.g. China -> "Asia") for crossings to auto-classify.

LOCATION_CONTINENT: dict[str, str] = {
    "Brazil": "South America",
    "Argentina": "South America",
    "United States": "North America",
    "Netherlands": "Europe",
    "Germany": "Europe",
    "EU": "Europe",
}

# sea-crossing defaults (the old sea-role post_setup values)
SEA_CAPACITY: float = 1000.0
SEA_FREIGHT_ATTR: str = "fixed_costs_transport_sea"

# sea-lane archetype params, single-sourced from the SeaEdge defaults above
_SEA_LANE = {
    "bindings":       _ENERGY,
    "scenario_attrs": {"fixed_costs": SEA_FREIGHT_ATTR},
    "attrs":          {"capacity": SEA_CAPACITY, "transit_steps": 60},   # ~2-month Atlantic crossing
}


@dataclass(frozen=True)
class SeaEdge:
    src: str
    dst: str
    capacity: float
    freight_cost_attr: str     # scenario attribute holding the freight fixed cost


def derive_sea_edges(pdl_path: str | Path) -> list[SeaEdge]:
    """
    Walk supply_chains.stages and return the sea crossings: stages whose endpoints
    sit on different known continents (deduplicated). Land/process links are omitted.
    """
    doc = PDLLoader(pdl_path)._doc
    loc = {e.get("id"): e.get("location") for e in (doc.get("entities") or [])}

    seen: set[tuple[str, str]] = set()
    edges: list[SeaEdge] = []
    for chain in (doc.get("supply_chains") or []):
        for stage in (chain.get("stages") or []):
            src, dst = stage[0], stage[1]
            if (src, dst) in seen:
                continue
            c_src = LOCATION_CONTINENT.get(loc.get(src))
            c_dst = LOCATION_CONTINENT.get(loc.get(dst))
            if c_src and c_dst and c_src != c_dst:
                seen.add((src, dst))
                edges.append(SeaEdge(src, dst, SEA_CAPACITY, SEA_FREIGHT_ATTR))
    return edges


# ---------------------------------------------------------------------------
# Materialise each sea crossing as its sea-lane agent, so the dynamic builder
# reproduces the current roster.
# ---------------------------------------------------------------------------
TRANSITIONAL_SEA: dict[tuple[str, str], Archetype] = {
    ("santos_port", "rotterdam_port"):     Archetype("sea_lane_santos", Transport, ROLE_SEA_SANTOS, "n_sea_lane_santos", _SEA_LANE),
    ("paranagua_port", "hamburg_port"):    Archetype("sea_lane_paranagua", Transport, ROLE_SEA_PARANAGUA, "n_sea_lane_paranagua", _SEA_LANE),
    ("argentina_farms", "rotterdam_port"): Archetype("sea_lane_arg", Transport, ROLE_SEA_ARG, "n_sea_lane_arg", _SEA_LANE),
    ("us_gulf_ports", "rotterdam_port"):   Archetype("sea_lane_usa", Transport, ROLE_SEA_USA, "n_sea_lane_usa", _SEA_LANE),
}


@dataclass(frozen=True)
class RosterEntry:
    archetype: Archetype
    entity_ids: tuple[str, ...]   # PDL entities represented; () for synthetic / sea edges


PRODUCER_ROLES: frozenset[str] = frozenset({ROLE_PRODUCER})


def build_roster(pdl_path: str | Path) -> list[RosterEntry]:
    """
    Ordered roster from a PDL: synthetic agents, node archetypes, sea-lane agents.

    Producer kinds split per-entity (each carries its own id-named list, count, and
    shock); non-producer kinds still pool (e.g. poultry/pig/dairy into eu_farmers).
    """
    entities = PDLLoader(pdl_path)._doc.get("entities") or []

    order: list[Archetype] = list(SYNTHETIC)
    ids_by_arc: dict[Archetype, list[str]] = {arc: [] for arc in SYNTHETIC}

    for e in entities:
        arc = resolve(e)
        if arc is None:
            continue
        eid = e.get("id")
        # producer already in use -> this is an additional producer region: give
        # it its own per-entity list (name from id, count from a scenario-specific
        # n_<id> if defined, else the kind default).
        if arc.role in PRODUCER_ROLES and arc in ids_by_arc:
            specific = f"n_{eid}"
            count_attr = specific if hasattr(SupplyChainScenario, specific) else arc.count_attr
            arc = replace(arc, name=eid, count_attr=count_attr)
        if arc not in ids_by_arc:
            order.append(arc)
            ids_by_arc[arc] = []
        ids_by_arc[arc].append(eid)

    for edge in derive_sea_edges(pdl_path):
        arc = TRANSITIONAL_SEA.get((edge.src, edge.dst))
        if arc is not None and arc not in ids_by_arc:
            order.append(arc)
            ids_by_arc[arc] = []

    return [RosterEntry(arc, tuple(ids_by_arc[arc])) for arc in order]


# ---------------------------------------------------------------------------
# Flow wiring: the supply-chain adjacency as explicit data, maps each archetype
# (by model-attr name) to the upstream archetypes it pulls from. Step methods
# read this instead of naming lists directly.
#
# It is not isomorphic to supply_chains.stages: the model splices in synthetic
# hubs (wholesalers, feed_traders) and origin routing (santos_share, arg/usa
# bypass) the PDL doesn't carry. build_flow_adjacency() rederives it from the PDL.
# ---------------------------------------------------------------------------

FLOW_ADJACENCY: dict[str, tuple[str, ...]] = {
    "wholesalers":            ("bra_farmers", "arg_farmers", "usa_farmers"),
    "transport_sa_santos":    ("wholesalers",),
    "transport_sa_paranagua": ("wholesalers",),
    "sea_lane_santos":        ("transport_sa_santos",),
    "sea_lane_paranagua":     ("transport_sa_paranagua",),
    "sea_lane_arg":           ("wholesalers",),
    "sea_lane_usa":           ("wholesalers",),
    "transport_eu_rtm":       ("sea_lane_santos", "sea_lane_arg", "sea_lane_usa"),
    "transport_eu_ham":       ("sea_lane_paranagua",),
    "processors":             ("transport_eu_rtm", "transport_eu_ham"),
    "feed_manufacturers":     ("processors",),
    "feed_traders":           ("feed_manufacturers",),
    "eu_farmers":             ("feed_traders",),
}

SYNTHETIC_NAMES: frozenset[str] = frozenset({"wholesalers", "feed_traders"})


def _sea_lane_crossings() -> dict[str, tuple[str, str]]:
    """Sea-lane archetype name -> the (src_entity, dst_entity) crossing it carries."""
    return {arc.name: pair for pair, arc in TRANSITIONAL_SEA.items()}


def producer_lists(adjacency: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    """
    The producers: source lists that supply others but have no upstream. Pass a
    run's derived graph for a swapped PDL; defaults to the literal FLOW_ADJACENCY.
    """
    adj = FLOW_ADJACENCY if adjacency is None else adjacency
    dsts = set(adj)
    out: list[str] = []
    for srcs in adj.values():
        for s in srcs:
            if s not in dsts and s not in out:
                out.append(s)
    return out


def export_port_lists(adjacency: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    """
    The export ports: land lists feeding a sea crossing (non-source, non-synthetic,
    so the wholesaler bypass is excluded). Defaults to FLOW_ADJACENCY; pass a graph.
    """
    adj = FLOW_ADJACENCY if adjacency is None else adjacency
    sea_lanes = set(_sea_lane_crossings())
    sources = set(producer_lists(adj))
    out: list[str] = []
    for dst, srcs in adj.items():
        if dst in sea_lanes:
            for src in srcs:
                if src not in sources and src not in SYNTHETIC_NAMES and src not in out:
                    out.append(src)
    return out


def _pdl_stage_pairs(pdl_path: str | Path) -> set[tuple[str, str]]:
    """All (src, dst) stage pairs across every supply chain in the PDL."""
    doc = PDLLoader(pdl_path)._doc
    pairs: set[tuple[str, str]] = set()
    for chain in (doc.get("supply_chains") or []):
        for stage in (chain.get("stages") or []):
            pairs.add((stage[0], stage[1]))
    return pairs


def build_flow_adjacency(pdl_path: str | Path) -> dict[str, tuple[str, ...]]:
    """
    Rederive the flow adjacency from the PDL: the de-hardcoded FLOW_ADJACENCY.

    PDL-derived from supply_chains.stages: land/process stage -> dst <- src;
    sea crossing -> lane <- land-port and dst-port <- lane.

    Declared overlay the PDL doesn't carry: a 'wholesalers' hub aggregates producers
    and feeds export ports/bypass lanes; a 'feed_traders' hub sits before EU consumers.

    On the shipped PDL this reproduces the literal FLOW_ADJACENCY exactly.
    """
    roster = build_roster(pdl_path)
    name_of: dict[str, str] = {}
    for entry in roster:
        for eid in entry.entity_ids:
            name_of[eid] = entry.archetype.name

    producers = {e.archetype.name for e in roster
                 if e.archetype.agent_class is Farmer
                 and e.archetype.role in (ROLE_PRODUCER)}
    consumers = {e.archetype.name for e in roster
                 if e.archetype.agent_class is Farmer and e.archetype.role == ROLE_CONSUMER}
    producer_e = {eid for eid, nm in name_of.items() if nm in producers}
    consumer_e = {eid for eid, nm in name_of.items() if nm in consumers}

    wholesaler = next(a.name for a in SYNTHETIC if a.role == ROLE_WHOLESALER)
    feed_trader = next(a.name for a in SYNTHETIC if a.role == ROLE_FEED_TRADER)

    crossings = {(e.src, e.dst): TRANSITIONAL_SEA.get((e.src, e.dst))
                 for e in derive_sea_edges(pdl_path)}
    stages = _pdl_stage_pairs(pdl_path)

    adj: dict[str, set[str]] = {}

    def add(dst: str, src: str) -> None:
        adj.setdefault(dst, set()).add(src)

    def producer_fed(eid: str) -> bool:
        return eid in producer_e or any(p in producer_e for (p, q) in stages if q == eid)

    # --- 1. PDL-derived spine + sea crossings ---
    for (s, d) in stages:
        if (s, d) in crossings:
            lane = crossings[(s, d)]
            if lane is None:
                continue                            # crossing with no materialised lane
            if d in name_of:
                add(name_of[d], lane.name)          # exit: dst port <- lane
            if s in name_of and s not in producer_e:
                add(lane.name, name_of[s])          # entry: lane <- land port
        elif (s in name_of and d in name_of
                and s not in producer_e and s not in consumer_e
                and d not in consumer_e):
            add(name_of[d], name_of[s])

    # --- 2. declared overlay: synthetic hubs the PDL doesn't name ---
    for nm in producers:
        add(wholesaler, nm)                         # market hub aggregates producers
    for (s, d) in stages:                           # export ports / bypass lanes pull from the hub
        if s not in producer_e:
            continue
        lane = crossings.get((s, d))
        if lane is not None:
            add(lane.name, wholesaler)              # producer's direct sea bypass (ARG)
        elif d in name_of:
            add(name_of[d], wholesaler)             # producer's land export port
    for (s, d), lane in crossings.items():
        if lane is not None and s not in name_of and producer_fed(s):
            add(lane.name, wholesaler)              # producer-fed excluded origin (US gulf)
    for (s, d) in stages:                           # distribution hub before consumers
        if d in consumer_e and s in name_of:
            add(name_of[d], feed_trader)
            add(feed_trader, name_of[s])

    # Order each dst's srcs by roster position (not alphabetically): this is the
    # byte-safe order the step methods sum over, and it reproduces the literal
    # FLOW_ADJACENCY exactly on the shipped PDL so the runtime can consume the
    # derived graph without changing float-sum grouping.
    pos = {entry.archetype.name: i for i, entry in enumerate(roster)}
    return {dst: tuple(sorted(srcs, key=lambda s: pos.get(s, len(pos))))
            for dst, srcs in adj.items()}


def execution_order(adjacency: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    """
    Per-step execution order: a topological sort of the flow graph, so each source
    is stepped before any list that consumes it. Replaces the hardcoded step sequence.

    Independent nodes are tie-broken by first appearance, reproducing the legacy order;
    since each step reads only upstream, any valid topological order gives the same result.

    On a cycle, remaining nodes are appended in declaration order with a warning.
    """
    import heapq

    adj = FLOW_ADJACENCY if adjacency is None else adjacency

    appearance: dict[str, int] = {}
    for dst, srcs in adj.items():
        appearance.setdefault(dst, len(appearance))
        for src in srcs:
            appearance.setdefault(src, len(appearance))

    nodes = list(appearance)
    indeg = {n: 0 for n in nodes}
    dependents: dict[str, list[str]] = {n: [] for n in nodes}
    for dst, srcs in adj.items():
        for src in srcs:
            indeg[dst] += 1
            dependents[src].append(dst)

    ready = [(appearance[n], n) for n in nodes if indeg[n] == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        _, n = heapq.heappop(ready)
        order.append(n)
        for dst in dependents[n]:
            indeg[dst] -= 1
            if indeg[dst] == 0:
                heapq.heappush(ready, (appearance[dst], dst))

    if len(order) < len(nodes):
        placed = set(order)
        remaining = sorted((n for n in nodes if n not in placed),
                           key=lambda n: appearance[n])
        logger.warning("flow graph has a cycle; stepping %s in declaration order after the acyclic prefix", remaining)
        order.extend(remaining)

    return order


