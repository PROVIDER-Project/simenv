"""
Export a PDL topology, optionally with simulation CSV data, into a web bundle.

Reads the ``Result_Simulator_*.csv`` files a run writes to ``data/output`` and emits
a single ``bundle.json`` matching the frontend ``Bundle`` contract
(``web/src/data/types.ts``): nodes, edges, per-node time-series (``ticks``) and the
environment time-series (``env``).

Each recorded agent list holds many instances; a map node is the aggregate of its
list per step — extensive quantities are summed, prices/utilisation are averaged,
and ``active`` is true if any instance is active. Ports and sea-lanes are
geographically real but produce no recorded rows, so they carry no ticks
(``hasRecordedData: false``), exactly as the frontend expects.

Geography is deliberately NOT emitted: placement is the frontend gazetteer's job
(keyed by the PDL entity ids carried in ``entityIds``). Nodes and edges follow the
PDL-derived model graph directly, including materialised sea-lane agents.

Usage:
    python -m provider_simenv.export_bundle [--scenario 1] [--input DIR] [--output FILE]
    python -m provider_simenv.export_bundle --topology-only --output FILE
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone

import pandas as pd

from .tick_writer import AGENT_TABLES
from .topology import (
    SYNTHETIC_NAMES,
    TRANSITIONAL_SEA,
    build_flow_adjacency,
    build_roster,
    execution_order,
)

logger = logging.getLogger(__name__)

# Column aggregation rules for collapsing a list's instances into one node/step.
SUM_COLS = {
    "quantity_available", "bra_volume", "arg_volume", "usa_volume",
    "feed_received", "livestock_output",
}
MEAN_COLS = {"unit_price", "storage_utilization"}
BOOL_ANY_COLS = {"active"}

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

_LABEL_TOKENS = {
    "arg": "Argentina",
    "eu": "EU",
    "paranagua": "Paranaguá",
    "us": "US",
    "usa": "US",
}


def _humanize(identifier: str) -> str:
    """Turn a model or PDL identifier into a minimal English label."""
    words: list[str] = []
    for token in identifier.split("_"):
        replacement = _LABEL_TOKENS.get(token)
        if replacement is not None:
            words.append(replacement)
        elif not words:
            words.append(token.capitalize())
        else:
            words.append(token)
    return " ".join(words)


def _node_label(node_id: str, role: str, entity_ids: tuple[str, ...]) -> str:
    """Derive the bundle's secondary English label from stable PDL/model ids."""
    if role == "producer":
        if len(entity_ids) == 1 and entity_ids[0].endswith("_farms"):
            region = entity_ids[0].removesuffix("_farms")
            return f"{_humanize(region)} soy farms"
        return "Soy farms"
    if role == "consumer":
        return _humanize(node_id).replace("farmers", "livestock farms")
    if role.startswith("sea_"):
        return f"{_humanize(role.removeprefix('sea_'))} sea lane"
    if len(entity_ids) == 1:
        entity_id = entity_ids[0]
        if entity_id.endswith("_port"):
            return f"Port of {_humanize(entity_id.removesuffix('_port'))}"
        return _humanize(entity_id)
    return _humanize(node_id)


def build_graph(pdl_path: str | os.PathLike[str]) -> tuple[list[dict], list[dict]]:
    """Build the web node and edge graph directly from one PDL document."""
    roster = build_roster(pdl_path)
    recorded_order = {
        node_id: index
        for index, (node_id, _) in enumerate(AGENT_TABLES.values())
    }
    roster_order = {
        entry.archetype.name: index for index, entry in enumerate(roster)
    }
    ordered_roster = sorted(
        roster,
        key=lambda entry: (
            0,
            recorded_order[entry.archetype.name],
        )
        if entry.archetype.name in recorded_order
        else (1, roster_order[entry.archetype.name]),
    )

    nodes = [
        {
            "id": entry.archetype.name,
            "label": _node_label(
                entry.archetype.name,
                entry.archetype.role,
                entry.entity_ids,
            ),
            "role": entry.archetype.role,
            "entityIds": list(entry.entity_ids),
            "hasRecordedData": entry.archetype.name in recorded_order,
        }
        for entry in ordered_roster
    ]

    adjacency = build_flow_adjacency(pdl_path)
    ordered_adjacency = {
        node_id: adjacency[node_id]
        for node_id in roster_order
        if node_id in adjacency
    }
    lane_names = {
        archetype.name for archetype in TRANSITIONAL_SEA.values()
    }
    edges = [
        {
            "id": f"{source}->{target}",
            "source": source,
            "target": target,
            "isSeaCrossing": source in lane_names or target in lane_names,
            "kind": (
                "commercial"
                if source in SYNTHETIC_NAMES or target in SYNTHETIC_NAMES
                else "physical"
            ),
        }
        for target in execution_order(ordered_adjacency)
        if target in ordered_adjacency
        for source in adjacency[target]
    ]
    return nodes, edges


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


def build_bundle(
    input_dir: str,
    scenario: int,
    pdl: str,
    *,
    topology_only: bool = False,
) -> dict:
    nodes, edges = build_graph(pdl)
    ticks: list[dict] = []
    env: list[dict] = []

    if not topology_only:
        node_ids = {node["id"] for node in nodes}

        # Recorded nodes and their aggregated series.
        for table, (node_id, props) in AGENT_TABLES.items():
            if node_id not in node_ids:
                raise ValueError(
                    f"recorded node {node_id!r} is absent from the PDL-derived roster"
                )
            path = os.path.join(input_dir, f"{table}.csv")
            if not os.path.exists(path):
                logger.warning("missing CSV for %s: %s", node_id, path)
                continue
            df = pd.read_csv(path)
            df = df[df["id_scenario"] == scenario]
            for period, values in _aggregate(df, props).items():
                ticks.append({"period": period, "nodeId": node_id, "values": values})

        # Environment series.
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
            "pdl": os.path.basename(pdl) if pdl else "s1-soja.pdl.yaml",
            "scenario": "topology_only" if topology_only else f"scenario_{scenario}",
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

    default_output = os.path.join(repo_root, "web", "public", "bundle.json")
    parser = argparse.ArgumentParser(description="Export a PDL-derived web bundle")
    parser.add_argument("--scenario", type=int, default=1,
                        help="id_scenario to export (0 = baseline, 1 = PDL shock). Default 1.")
    parser.add_argument("--input", type=str, default=os.path.join(here, "data", "output"),
                        help="Directory holding Result_Simulator_*.csv.")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path. Required with --topology-only; full exports default to web/public/bundle.json.",
    )
    parser.add_argument(
        "--pdl",
        type=str,
        default=os.path.join(here, "scenarios", "s1-soja.pdl.yaml"),
        help="PDL file used to derive topology and recorded in bundle metadata.",
    )
    parser.add_argument(
        "--topology-only",
        action="store_true",
        help="Derive nodes and edges without reading simulation CSV output.",
    )
    args = parser.parse_args()

    if args.topology_only and args.output is None:
        parser.error("--output is required with --topology-only")

    output = os.path.abspath(args.output or default_output)
    bundle = build_bundle(
        args.input,
        args.scenario,
        args.pdl,
        topology_only=args.topology_only,
    )
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, ensure_ascii=False, separators=(",", ":"))

    mode = "topology only" if args.topology_only else f"scenario {args.scenario}"
    logger.info("wrote %s — %d nodes, %d edges, %d ticks, %d env steps (%s)",
                output, len(bundle["nodes"]), len(bundle["edges"]),
                len(bundle["ticks"]), len(bundle["env"]), mode)


if __name__ == "__main__":
    main()
