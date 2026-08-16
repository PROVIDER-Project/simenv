"""
Export a simulation run's CSV output into the JSON bundle the web view consumes.

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
(keyed by the PDL entity ids carried in ``entityIds``). This is the geolocatable
projection of the model graph — sea crossings are drawn port-to-port rather than
routed through the sea-lane agents, which have no single map location.

Usage:
    python -m provider_simenv.export_bundle [--scenario 1] [--input DIR] [--output FILE]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone

import pandas as pd

from .tick_writer import AGENT_TABLES

logger = logging.getLogger(__name__)

# Column aggregation rules for collapsing a list's instances into one node/step.
SUM_COLS = {
    "quantity_available", "bra_volume", "arg_volume", "usa_volume",
    "feed_received", "livestock_output",
}
MEAN_COLS = {"unit_price", "storage_utilization"}
BOOL_ANY_COLS = {"active"}


def _csv_table(list_name: str) -> str:
    return "Result_Simulator_" + "".join(p.title() for p in list_name.split("_"))


# The geolocatable node overlay: display name, agent role, and the PDL entity ids
# the gazetteer places by. Recorded nodes come from AGENT_TABLES; ports are added
# here (they are real places but the DataCollector records no series for them).
NODE_META: dict[str, dict] = {
    "brazil_farms":           {"label": "Brazil soy farms",   "role": "producer",           "entityIds": ["brazil_farms"]},
    "argentina_farms":        {"label": "Argentina soy farms","role": "producer",           "entityIds": ["argentina_farms"]},
    "us_farms":               {"label": "US soy farms",       "role": "producer",           "entityIds": ["us_farms"]},
    "wholesalers":            {"label": "Wholesalers",        "role": "wholesaler",         "entityIds": []},
    "feed_traders":           {"label": "Feed traders",       "role": "feed_trader",        "entityIds": []},
    "processors":             {"label": "EU oil mills",       "role": "processor",          "entityIds": ["eu_oil_mills"]},
    "feed_manufacturers":     {"label": "Feed mills",         "role": "feed_manufacturer",  "entityIds": ["feed_mills"]},
    "eu_farmers":             {"label": "EU livestock farms", "role": "consumer",           "entityIds": ["poultry_farms", "pig_farms", "dairy_farms"]},
}

PORT_META: dict[str, dict] = {
    "transport_sa_santos":    {"label": "Port of Santos",     "role": "sa_santos",    "entityIds": ["santos_port"]},
    "transport_sa_paranagua": {"label": "Port of Paranaguá",  "role": "sa_paranagua", "entityIds": ["paranagua_port"]},
    "transport_eu_rtm":       {"label": "Port of Rotterdam",  "role": "eu_rtm",       "entityIds": ["rotterdam_port"]},
    "transport_eu_ham":       {"label": "Port of Hamburg",    "role": "eu_ham",       "entityIds": ["hamburg_port"]},
}

# Geolocatable flow overlay (sea crossings collapsed port-to-port).
EDGES: list[tuple[str, str, bool]] = [
    ("brazil_farms", "wholesalers", False),
    ("argentina_farms", "wholesalers", False),
    ("us_farms", "wholesalers", False),
    ("wholesalers", "transport_sa_santos", False),
    ("wholesalers", "transport_sa_paranagua", False),
    ("transport_sa_santos", "transport_eu_rtm", True),
    ("transport_sa_paranagua", "transport_eu_ham", True),
    ("argentina_farms", "transport_eu_rtm", True),
    ("us_farms", "transport_eu_rtm", True),
    ("transport_eu_rtm", "processors", False),
    ("transport_eu_ham", "processors", False),
    ("processors", "feed_manufacturers", False),
    ("feed_manufacturers", "feed_traders", False),
    ("feed_traders", "eu_farmers", False),
]

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
    nodes: list[dict] = []
    ticks: list[dict] = []

    # Recorded nodes + their aggregated series.
    for _pg_table, (list_name, props) in AGENT_TABLES.items():
        node_id = list_name
        meta = NODE_META.get(node_id)
        if meta is None:
            logger.warning("no geolocatable metadata for recorded node %r — skipping", node_id)
            continue
        nodes.append({
            "id": node_id, "label": meta["label"], "role": meta["role"],
            "entityIds": meta["entityIds"], "hasRecordedData": True,
        })
        path = os.path.join(input_dir, f"{_csv_table(list_name)}.csv")
        if not os.path.exists(path):
            logger.warning("missing CSV for %s: %s", node_id, path)
            continue
        df = pd.read_csv(path)
        df = df[df["id_scenario"] == scenario]
        for period, values in _aggregate(df, props).items():
            ticks.append({"period": period, "nodeId": node_id, "values": values})

    # Ports — real places, no recorded series.
    for node_id, meta in PORT_META.items():
        nodes.append({
            "id": node_id, "label": meta["label"], "role": meta["role"],
            "entityIds": meta["entityIds"], "hasRecordedData": False,
        })

    edges = [
        {"id": f"{s}->{t}", "source": s, "target": t, "isSeaCrossing": sea}
        for (s, t, sea) in EDGES
    ]

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
            "pdl": os.path.basename(pdl) if pdl else "s1-soja.pdl.yaml",
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
