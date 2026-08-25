"""
PDL-entity-driven roster and flow wiring (hybrid archetype resolution).

Resolution order for each entity:
    1. entity / sidecar declaration      declared mapping, or silent exclusion
    2. KIND_KEYS[(type, sector)]         fallback when no declaration exists
    3. otherwise                         unmodelled -> skipped (logged)

Producers are built per entity from {param}_{eid} columns. Non-producers still
use pooled recipes where the model shares an agent list.

Sidecar entities participate in the roster and flow graph. Sea crossings are
edges, materialised as sea-lane agents (TRANSITIONAL_SEA).

The model imports build_roster / build_flow_adjacency / execution_order to drive
create(), setup(), and the per-step loop.
"""
from __future__ import annotations
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

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


# Place-specific transport recipes preserve distinct peer lists and cost groups.
KIND_ARCHETYPES: dict[tuple[str, str], Archetype] = {
    ("infrastructure", "logistics"): Archetype("transport_sa_santos", Transport, ROLE_SA_SANTOS, "n_transport_sa_santos", _TRANSPORT_SA),
}

# id overrides: tuned role/count, or type+sector collisions
ID_OVERRIDES: dict[str, Archetype] = {
    "paranagua_port": Archetype("transport_sa_paranagua", Transport, ROLE_SA_PARANAGUA, "n_transport_sa_paranagua", _TRANSPORT_SA),
    "rotterdam_port": Archetype("transport_eu_rtm", Transport, ROLE_EU_RTM, "n_transport_eu_rtm", _TRANSPORT_EU),
    "hamburg_port":   Archetype("transport_eu_ham", Transport, ROLE_EU_HAM, "n_transport_eu_ham", _TRANSPORT_EU),
    # santos_port -> infrastructure/logistics default (transport_sa_santos)
}

# present in PDL but deliberately not a node-agent (yet)
EXCLUDE: frozenset[str] = frozenset({
    "us_gulf_ports",   # origin of the USA sea edge, not a handler node today
})

# ---------------------------------------------------------------------------
# Sidecar: declarations the PDL does not carry (s1-soja.roster.yaml)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RosterSidecar:
    archetypes: Mapping[str, str]
    exclude: Mapping[str, str]
    entities: tuple[Mapping[str, Any], ...]
    edges: tuple[tuple[str, str], ...]
    dependencies: tuple[Mapping[str, Any], ...]


def _sidecar_path(pdl_path: str | Path) -> Path:
    p = Path(pdl_path)
    stem = p.name[:-len(".pdl.yaml")] if p.name.endswith(".pdl.yaml") else p.stem
    return p.with_name(stem + ".roster.yaml")


def load_roster_sidecar(pdl_path: str | Path) -> RosterSidecar:
    """Load the roster sidecar beside the PDL. Additive only: a sidecar entity id
    may not collide with a PDL entity, and every added entity must carry a reason."""
    path = _sidecar_path(pdl_path)
    if not path.exists():
        return RosterSidecar({}, {}, (), (), ())

    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    pdl_ids = {e.get("id") for e in (PDLLoader(pdl_path)._doc.get("entities") or [])}

    entities = tuple(doc.get("entities") or [])
    for ent in entities:
        eid = ent.get("id")
        if eid in pdl_ids:
            raise ValueError(f"roster sidecar entity {eid!r} collides with a PDL entity; sidecar is additive-only")
        if not ent.get("reason"):
            raise ValueError(f"roster sidecar entity {eid!r} is missing a required 'reason'")

    return RosterSidecar(
        archetypes=dict(doc.get("archetypes") or {}),
        exclude=dict(doc.get("exclude") or {}),
        entities=entities,
        edges=tuple((e[0], e[1]) for e in (doc.get("edges") or [])),
        dependencies=tuple(doc.get("dependencies") or []),
    )


def resolve(entity: Mapping[str, Any]) -> Archetype | None:
    """Resolve one entity to a place-specific transport recipe."""
    eid = entity.get("id")
    if eid in EXCLUDE:
        return None
    if eid in ID_OVERRIDES:
        return ID_OVERRIDES[eid]
    return KIND_ARCHETYPES.get((entity.get("type"), entity.get("sector")))


# ---------------------------------------------------------------------------
# Archetype resolution: PDL entity -> archetype key (sidecar-driven)
# ---------------------------------------------------------------------------

ARCHETYPE_REGISTRY: dict[str, tuple[type, str]] = {
    "producer":          (Farmer,  ROLE_PRODUCER),
    "consumer":          (Farmer,  ROLE_CONSUMER),
    "processor":         (Process, ROLE_PROCESSOR),
    "feed_manufacturer": (Process, ROLE_FEED_MANUFACTURER),
    "wholesaler":        (Trader,  ROLE_WHOLESALER),
    "feed_trader":       (Trader,  ROLE_FEED_TRADER),
}

_DECLARED_ARCHETYPES: dict[str, tuple[str, str, Mapping[str, Any]]] = {
    "consumer":          ("eu_farmers", "n_eu_farmers", _FARMER_EU),
    "processor":         ("processors", "n_processors", _PROCESSOR),
    "feed_manufacturer": ("feed_manufacturers", "n_feed_manufacturers", _FEED_MFR),
    "wholesaler":        ("", "n_wholesalers", _WHOLESALER),
    "feed_trader":       ("feed_traders", "n_feed_traders", _FEED_TRADER),
}

# land_transport / sea_lane keep per-place roles, resolved via the id/kind path.
KNOWN_ARCHETYPES: frozenset[str] = frozenset(ARCHETYPE_REGISTRY) | {"land_transport", "sea_lane"}

# (type, sector) fallback when the sidecar doesn't name an entity.
KIND_KEYS: dict[tuple[str, str], str] = {
    ("region", "agriculture"):       "producer",
    ("infrastructure", "logistics"): "land_transport",
    ("manufacturer", "processing"):  "processor",
    ("manufacturer", "agriculture"): "consumer",
}


def resolve_archetype(entity: Mapping[str, Any], sidecar: RosterSidecar) -> str | None:
    """Archetype key from the entity, sidecar, or kind fallback."""
    eid = entity.get("id")
    if eid in sidecar.exclude:
        return None
    key = (
        entity.get("archetype")
        or sidecar.archetypes.get(eid)
        or KIND_KEYS.get((entity.get("type"), entity.get("sector")))
    )
    if key is None:
        logger.warning(
            "entity %r (%s/%s) resolved to no archetype - not modelled; declare it in the roster sidecar",
            eid, entity.get("type"), entity.get("sector"),
        )
        return None
    if key not in KNOWN_ARCHETYPES:
        raise ValueError(f"roster sidecar assigns entity {eid!r} unknown archetype {key!r}")
    return key


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
    entity_ids: tuple[str, ...]   # entities represented; () for sea edges


_PRODUCER_SCENARIO_ATTRS = ("fixed_costs", "margin", "size_sigma")


def _producer_count_attr(eid: str) -> str:
    specific = f"n_{eid}"
    if hasattr(SupplyChainScenario, specific):
        return specific
    logger.warning("producer %r has no %s; falling back to n_producer", eid, specific)
    return "n_producer"


def _producer_scenario_attrs(eid: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for attr in _PRODUCER_SCENARIO_ATTRS:
        specific = f"{attr}_{eid}"
        if hasattr(SupplyChainScenario, specific):
            out[attr] = specific
        else:
            fallback = f"{attr}_producer"
            logger.warning(
                "producer %r has no %s; falling back to %s",
                eid, specific, fallback,
            )
            out[attr] = fallback
    return out


def _producer_input_bindings(
    eid: str, dependencies: list,
) -> dict[str, tuple[str, str]]:
    bindings: dict[str, tuple[str, str]] = {}
    for dep in dependencies:
        if dep.get("from") != eid or dep.get("type") != "input":
            continue
        target = dep.get("to")
        if not target:
            continue
        slot = target[:-len("_supply")] if target.endswith("_supply") else target
        bindings[slot] = (target, "price")
    return bindings


def _pdl_dependencies(doc: Mapping[str, Any]) -> list:
    deps: list = []
    for chain in (doc.get("supply_chains") or []):
        deps.extend(chain.get("dependencies") or [])
    return deps


def _declared_archetype(entity: Mapping[str, Any], key: str) -> Archetype | None:
    eid = entity.get("id")
    if key == "land_transport":
        arc = resolve(entity)
    else:
        spec = _DECLARED_ARCHETYPES.get(key)
        if spec is None or not eid:
            arc = None
        else:
            default_name, count_attr, params = spec
            cls, role = ARCHETYPE_REGISTRY[key]
            name = eid if key == "wholesaler" else default_name
            arc = Archetype(name, cls, role, count_attr, params)
    if arc is None:
        logger.warning(
            "entity %r resolved to archetype %r but has no runtime recipe",
            eid, key,
        )
    return arc


def build_roster(pdl_path: str | Path) -> list[RosterEntry]:
    """
    Ordered roster from PDL and sidecar entities, followed by sea-lane agents.

    Producer kinds split per-entity (each carries its own id-named list, count, and
    shock); declared non-producer kinds use their model recipes.
    """
    doc = PDLLoader(pdl_path)._doc
    sidecar = load_roster_sidecar(pdl_path)
    entities = [*(doc.get("entities") or []), *sidecar.entities]
    pdl_deps = _pdl_dependencies(doc)

    order: list[Archetype] = []
    ids_by_arc: dict[Archetype, list[str]] = {}

    for e in entities:
        key = resolve_archetype(e, sidecar)
        if key is None:
            continue
        eid = e.get("id")
        if key == "producer":
            cls, role = ARCHETYPE_REGISTRY["producer"]
            arc = Archetype(
                eid, cls, role,
                _producer_count_attr(eid),
                {
                    "bindings": _producer_input_bindings(eid, pdl_deps),
                    "scenario_attrs": _producer_scenario_attrs(eid),
                    "attrs": {"base_yield": 100.0},
                },
            )
        else:
            arc = _declared_archetype(e, key)
            if arc is None:
                continue
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
# Flow wiring maps each model list to the upstream lists it pulls from. Sidecar
# edges insert declared actors that the PDL does not yet carry.
# ---------------------------------------------------------------------------


def _sea_lane_crossings() -> dict[str, tuple[str, str]]:
    """Sea-lane archetype name -> the (src_entity, dst_entity) crossing it carries."""
    return {arc.name: pair for pair, arc in TRANSITIONAL_SEA.items()}


def producer_lists(adjacency: dict[str, tuple[str, ...]]) -> list[str]:
    """Source lists that supply others but have no upstream."""
    dsts = set(adjacency)
    out: list[str] = []
    for srcs in adjacency.values():
        for s in srcs:
            if s not in dsts and s not in out:
                out.append(s)
    return out


def export_port_lists(adjacency: dict[str, tuple[str, ...]]) -> list[str]:
    """Land transport lists feeding a sea crossing."""
    sea_lanes = set(_sea_lane_crossings())
    sources = set(producer_lists(adjacency))
    out: list[str] = []
    for dst, srcs in adjacency.items():
        if dst in sea_lanes:
            for src in srcs:
                upstream = set(adjacency.get(src, ()))
                if src not in sources and upstream.isdisjoint(sources) and src not in out:
                    out.append(src)
    return out


def _pdl_stage_pairs(pdl_path: str | Path) -> list[tuple[str, str]]:
    """Unique stage pairs in first declaration order."""
    doc = PDLLoader(pdl_path)._doc
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for chain in (doc.get("supply_chains") or []):
        for stage in (chain.get("stages") or []):
            pair = (stage[0], stage[1])
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)
    return pairs


def build_flow_adjacency(pdl_path: str | Path) -> dict[str, tuple[str, ...]]:
    """
    Derive flow adjacency from PDL stages and sidecar edges. Sea crossings are
    materialised as lane agents between their endpoint actors.
    """
    roster = build_roster(pdl_path)
    sidecar = load_roster_sidecar(pdl_path)
    name_of: dict[str, str] = {}
    for entry in roster:
        for eid in entry.entity_ids:
            name_of[eid] = entry.archetype.name

    producers = {e.archetype.name for e in roster
                 if e.archetype.agent_class is Farmer
                 and e.archetype.role in (ROLE_PRODUCER,)}
    consumers = {e.archetype.name for e in roster
                 if e.archetype.agent_class is Farmer and e.archetype.role == ROLE_CONSUMER}
    producer_e = {eid for eid, nm in name_of.items() if nm in producers}
    consumer_e = {eid for eid, nm in name_of.items() if nm in consumers}

    crossings = {(e.src, e.dst): TRANSITIONAL_SEA.get((e.src, e.dst))
                 for e in derive_sea_edges(pdl_path)}
    stages = _pdl_stage_pairs(pdl_path)

    incoming: dict[str, list[str]] = {}
    outgoing: dict[str, list[str]] = {}
    for src, dst in sidecar.edges:
        outgoing.setdefault(src, []).append(dst)
        incoming.setdefault(dst, []).append(src)

    replaced_stages: set[tuple[str, str]] = set()
    replacement_crossings: dict[tuple[str, str], Archetype | None] = {}
    for entity in sidecar.entities:
        eid = entity.get("id")
        for src in incoming.get(eid, ()):
            for dst in outgoing.get(eid, ()):
                pair = (src, dst)
                if pair not in stages:
                    continue
                replaced_stages.add(pair)
                if pair in crossings:
                    replacement_crossings[(eid, dst)] = crossings[pair]

    adj: dict[str, set[str]] = {}

    def add(dst: str, src: str) -> None:
        adj.setdefault(dst, set()).add(src)

    # PDL spine, excluding direct edges replaced by a declared sidecar actor.
    for (s, d) in stages:
        if (s, d) in replaced_stages:
            continue
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

    # Sidecar edges insert declared actors into matching PDL stages.
    crossings_from: dict[str, list[Archetype]] = {}
    for (src, _), lane in crossings.items():
        if lane is not None:
            crossings_from.setdefault(src, []).append(lane)

    for s, d in sidecar.edges:
        pair = (s, d)
        if pair in replacement_crossings:
            lane = replacement_crossings[pair]
            if lane is None:
                continue
            if d in name_of:
                add(name_of[d], lane.name)
            if s in name_of:
                add(lane.name, name_of[s])
        elif s in name_of and d in name_of:
            add(name_of[d], name_of[s])
        elif s in name_of:
            for lane in crossings_from.get(d, ()):
                add(lane.name, name_of[s])

    # Order each destination's sources by roster position so summed flows follow
    # roster declaration order.
    pos = {entry.archetype.name: i for i, entry in enumerate(roster)}
    return {dst: tuple(sorted(srcs, key=lambda s: pos.get(s, len(pos))))
            for dst, srcs in adj.items()}


def execution_order(adjacency: dict[str, tuple[str, ...]]) -> list[str]:
    """
    Per-step execution order: a topological sort of the flow graph, so each source
    is stepped before any list that consumes it. Replaces the hardcoded step sequence.

    Independent nodes are tie-broken by first appearance, reproducing the legacy order;
    since each step reads only upstream, any valid topological order gives the same result.

    On a cycle, remaining nodes are appended in declaration order with a warning.
    """
    import heapq

    appearance: dict[str, int] = {}
    for dst, srcs in adjacency.items():
        appearance.setdefault(dst, len(appearance))
        for src in srcs:
            appearance.setdefault(src, len(appearance))

    nodes = list(appearance)
    indeg = {n: 0 for n in nodes}
    dependents: dict[str, list[str]] = {n: [] for n in nodes}
    for dst, srcs in adjacency.items():
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


