"""
Export a simulation run's CSV output into the JSON bundle the web view consumes.

Reads the ``Result_Simulator_*.csv`` files a run writes to ``data/output`` and emits
a single ``bundle.json`` matching the frontend ``Bundle`` contract
(``web/src/data/types.ts``): nodes, edges, per-node time-series (``ticks``) and the
environment time-series (``env``).

Each recorded agent list holds many instances; a map node is the aggregate of its
list per step — extensive quantities are summed, prices/utilisation are averaged,
and ``active`` is true if any instance is active. Ports produce no recorded rows,
so they carry no ticks (``hasRecordedData: false``), exactly as the frontend
expects.

Entity placements declared in the PDL or roster are emitted with their entity ids.
Entities without coordinates retain the frontend gazetteer fallback. Sea crossings
are drawn endpoint-to-endpoint rather than routed through sea-lane agents, which
have no single map location.

Usage:
    python -m provider_simenv.export_bundle [--scenario 1] [--input DIR] [--output FILE]
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .agents import Transport
from .data_collector import _PROPS_BY_ROLE
from .pdl_loader import PDLLoader
from .topology import build_flow_adjacency, build_roster, load_roster_sidecar

logger = logging.getLogger(__name__)

# Column aggregation rules for collapsing a list's instances into one node/step.
SUM_COLS = {
    "quantity_available", "feed_received", "livestock_output",
}
MEAN_COLS = {"unit_price", "storage_utilization"}
BOOL_ANY_COLS = {"active"}


def _csv_table(list_name: str) -> str:
    return "Result_Simulator_" + "".join(p.title() for p in list_name.split("_"))


def _resolve_pdl_path(pdl: str) -> Path:
    path = Path(pdl)
    if path.is_file():
        return path
    if not path.is_absolute() and path.parent == Path("."):
        scenario_path = Path(__file__).resolve().parent / "scenarios" / path.name
        if scenario_path.is_file():
            return scenario_path
    raise FileNotFoundError(f"PDL file not found: {pdl}")


def _entity_metadata(pdl_path: Path) -> dict[str, dict]:
    doc = PDLLoader(pdl_path)._doc
    sidecar = load_roster_sidecar(pdl_path)
    entities = [*(doc.get("entities") or []), *sidecar.entities]
    return {entity["id"]: dict(entity) for entity in entities}


def _entity_placement(entity_id: str, entity: dict) -> dict | None:
    fields = ("lat", "lng", "illustrative")
    present = [field in entity for field in fields]
    if not any(present):
        return None
    if not all(present):
        logger.error("incomplete placement for entity %r", entity_id)
        raise ValueError(f"incomplete placement for entity {entity_id!r}")

    lat_raw = entity["lat"]
    lng_raw = entity["lng"]
    illustrative = entity["illustrative"]
    if (
        isinstance(lat_raw, bool)
        or not isinstance(lat_raw, (int, float))
        or isinstance(lng_raw, bool)
        or not isinstance(lng_raw, (int, float))
    ):
        logger.error("non-numeric placement for entity %r", entity_id)
        raise ValueError(f"non-numeric placement for entity {entity_id!r}")
    if not isinstance(illustrative, bool):
        logger.error("placement flag for entity %r must be boolean", entity_id)
        raise ValueError(f"invalid placement flag for entity {entity_id!r}")

    lat = float(lat_raw)
    lng = float(lng_raw)
    if not math.isfinite(lat) or not math.isfinite(lng):
        logger.error("non-finite placement for entity %r", entity_id)
        raise ValueError(f"non-finite placement for entity {entity_id!r}")
    if not -90.0 <= lat <= 90.0 or not -180.0 <= lng <= 180.0:
        logger.error("out-of-range placement for entity %r", entity_id)
        raise ValueError(f"out-of-range placement for entity {entity_id!r}")

    return {
        "entityId": entity_id,
        "label": str(entity["name"]),
        "lat": lat,
        "lng": lng,
        "illustrative": illustrative,
    }


def _node_metadata(entry, entities: dict[str, dict]) -> dict:
    node_id = entry.archetype.name
    entity_ids = list(entry.entity_ids)
    labels: list[str] = []
    placements: list[dict] = []
    unresolved: list[str] = []
    for entity_id in entity_ids:
        entity = entities.get(entity_id)
        label = entity.get("name") if entity is not None else None
        if not label:
            unresolved.append(entity_id)
        else:
            labels.append(str(label))
            placement = _entity_placement(entity_id, entity)
            if placement is not None:
                placements.append(placement)
    if not entity_ids or unresolved:
        logger.error(
            "unresolved export metadata for roster node %r (entity ids: %s, unresolved: %s)",
            node_id, entity_ids, unresolved,
        )
        raise ValueError(f"unresolved export metadata for roster node {node_id!r}")
    return {
        "id": node_id,
        "label": " / ".join(labels),
        "role": entry.archetype.role,
        "entityIds": entity_ids,
        "placements": placements,
        "hasRecordedData": entry.archetype.role in _PROPS_BY_ROLE,
    }


def _collapsed_edges(
    adjacency: dict[str, tuple[str, ...]], sea_lanes: set[str], node_ids: set[str],
) -> list[dict]:
    downstream_lanes = {
        source
        for sources in adjacency.values()
        for source in sources
        if source in sea_lanes
    }
    for lane in sea_lanes:
        if lane not in adjacency or lane not in downstream_lanes:
            logger.error("sea lane %r lacks an exportable upstream/downstream path", lane)
            raise ValueError(f"incomplete sea-lane path for {lane!r}")

    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(source: str, target: str, is_sea: bool) -> None:
        if source not in node_ids or target not in node_ids:
            logger.error("edge %r -> %r references a node absent from the export roster", source, target)
            raise ValueError(f"unresolved export edge {source!r} -> {target!r}")
        pair = (source, target)
        if pair in seen:
            return
        seen.add(pair)
        edges.append({
            "id": f"{source}->{target}",
            "source": source,
            "target": target,
            "isSeaCrossing": is_sea,
        })

    for target, sources in adjacency.items():
        if target in sea_lanes:
            continue
        for source in sources:
            if source in sea_lanes:
                for lane_source in adjacency[source]:
                    add(lane_source, target, True)
            else:
                add(source, target, False)
    return edges

ENV_COLS = [
    ("soja_price", "sojaPrice"),
    ("feed_price", "feedPrice"),
    ("shock_scale", "shockScale"),
    ("drought_severity", "droughtSeverity"),
    ("total_soja_supply", "totalSojaSupply"),
    ("transport_utilisation", "transportUtilisation"),
    ("current_step", "currentStep"),
]

HONESTY_NOTE = "Approximate geographic positions — not GIS accurate"


def _aggregate(df: pd.DataFrame, props: list[str]) -> dict[int, dict]:
    """Collapse a list's per-instance rows into one value dict per period."""
    out: dict[int, dict] = {}
    grouped = df.groupby("period")
    for period, group in grouped:
        values: dict = {}
        for prop in props:
            if prop not in group.columns:
                continue
            if prop in SUM_COLS:
                values[prop] = round(float(group[prop].sum()), 4)
            elif prop in MEAN_COLS:
                values[prop] = round(float(group[prop].mean()), 4)
            elif prop in BOOL_ANY_COLS:
                values[prop] = bool(group[prop].astype(bool).any())
            else:
                values[prop] = round(float(group[prop].mean()), 4)
        out[int(period)] = values
    return out


def build_bundle(input_dir: str, scenario: int, pdl: str) -> dict:
    pdl_path = _resolve_pdl_path(pdl)
    roster = build_roster(pdl_path)
    adjacency = build_flow_adjacency(pdl_path)
    entities = _entity_metadata(pdl_path)
    sea_lanes = {
        entry.archetype.name
        for entry in roster
        if entry.archetype.agent_class is Transport and not entry.entity_ids
    }

    nodes: list[dict] = []
    ticks: list[dict] = []

    for entry in roster:
        node_id = entry.archetype.name
        if node_id in sea_lanes:
            continue
        nodes.append(_node_metadata(entry, entities))

        props = _PROPS_BY_ROLE.get(entry.archetype.role)
        if props is None:
            continue
        path = os.path.join(input_dir, f"{_csv_table(node_id)}.csv")
        if not os.path.exists(path):
            logger.warning("missing CSV for %s: %s", node_id, path)
            continue
        df = pd.read_csv(path)
        df = df[df["id_scenario"] == scenario]
        for period, values in _aggregate(df, list(props)).items():
            ticks.append({"period": period, "nodeId": node_id, "values": values})

    edges = _collapsed_edges(adjacency, sea_lanes, {node["id"] for node in nodes})

    # Environment series.
    env: list[dict] = []
    env_path = os.path.join(input_dir, "Result_Simulator_Environment.csv")
    edf = pd.read_csv(env_path)
    edf = edf[edf["id_scenario"] == scenario].sort_values("period")
    for _, row in edf.iterrows():
        snapshot = {"period": int(row["period"])}
        for csv_col, out_key in ENV_COLS:
            snapshot[out_key] = round(float(row[csv_col]), 4)
        env.append(snapshot)

    return {
        "meta": {
            "pdl": pdl_path.name,
            "scenario": f"scenario_{scenario}",
            "ticks": len(env),
            "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "honestyNote": HONESTY_NOTE,
        },
        "nodes": nodes,
        "edges": edges,
        "ticks": ticks,
        "env": env,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))

    parser = argparse.ArgumentParser(description="Export a run's CSVs to the web bundle.json")
    parser.add_argument("--scenario", type=int, default=1,
                        help="id_scenario to export (0 = baseline, 1 = PDL shock). Default 1.")
    parser.add_argument("--input", type=str, default=os.path.join(here, "data", "output"),
                        help="Directory holding Result_Simulator_*.csv.")
    parser.add_argument("--output", type=str, default=os.path.join(repo_root, "web", "public", "bundle.json"),
                        help="Path to write bundle.json.")
    parser.add_argument("--pdl", type=str, default="s1-soja.pdl.yaml", help="PDL name for metadata.")
    args = parser.parse_args()

    bundle = build_bundle(args.input, args.scenario, args.pdl)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, ensure_ascii=False, separators=(",", ":"))

    logger.info("wrote %s — %d nodes, %d edges, %d ticks, %d env steps (scenario %d)",
                args.output, len(bundle["nodes"]), len(bundle["edges"]),
                len(bundle["ticks"]), len(bundle["env"]), args.scenario)


if __name__ == "__main__":
    main()
