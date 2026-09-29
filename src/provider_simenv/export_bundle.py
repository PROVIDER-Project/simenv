"""
Export a simulation run into the JSON bundle the web view consumes.

Reads a run either from the PostgreSQL views (``--source postgres``, the default)
or from the ``Result_Simulator_*.csv`` files it writes to ``data/output/<run-id>/``
(``--source csv``), and emits a single ``bundle.json`` matching the frontend ``Bundle`` contract
(``web/src/data/types.ts``): nodes, edges, per-node time-series (``ticks``) and the
environment time-series (``env``). Both sources feed the same aggregation, so the
same run gives the same bundle.

Each recorded agent list holds many instances; a map node is the aggregate of its
list per step — extensive quantities are summed, prices/utilisation are averaged,
and ``active`` is true if any instance is active. Ports produce no recorded rows,
so they carry no ticks (``hasRecordedData: false``), exactly as the frontend
expects.

Entity placements declared in the PDL or roster are emitted with their entity ids.
Entities without coordinates retain the frontend gazetteer fallback. Sea crossings
are drawn endpoint-to-endpoint rather than routed through sea-transport agents, which
have no single map location.

Usage:
    python -m provider_simenv.export_bundle [--scenario 1] [--source postgres|csv] [--input DIR] [--run ID] [--output FILE]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .agents import Transport
from .data_collector import _PROPS_BY_ROLE, result_table_name
from .db_config import PostgresDBConfig
from .db_schema import ENVIRONMENT_ROLE, role_view_name
from .pdl_loader import PDLLoader
from .run_registry import resolve_run, run_dir
from .topology import build_flow_adjacency, build_roster, load_roster_sidecar

logger = logging.getLogger(__name__)

# Column aggregation rules for collapsing a list's instances into one node/step.
SUM_COLS = {
    "quantity_available", "feed_received", "livestock_output",
}
MEAN_COLS = {"unit_price", "storage_utilization"}
BOOL_ANY_COLS = {"active"}


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
    adjacency: dict[str, tuple[str, ...]], sea_transports: set[str], node_ids: set[str],
) -> list[dict]:
    downstream_transports = {
        source
        for sources in adjacency.values()
        for source in sources
        if source in sea_transports
    }
    for transport in sea_transports:
        if transport not in adjacency or transport not in downstream_transports:
            logger.error("sea transport %r lacks an exportable upstream/downstream path", transport)
            raise ValueError(f"incomplete sea-transport path for {transport!r}")

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
        if target in sea_transports:
            continue
        for source in sources:
            if source in sea_transports:
                for sea_source in adjacency[source]:
                    add(sea_source, target, True)
            else:
                add(source, target, False)
    return edges

ENV_COLS = [
    ("soy_price", "soyPrice"),
    ("feed_price", "feedPrice"),
    ("shock_scale", "shockScale"),
    ("drought_severity", "droughtSeverity"),
    ("total_soy_supply", "totalSoySupply"),
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


class CsvRunReader:
    """A run's per-instance rows from its Result_Simulator_*.csv files."""

    def __init__(self, input_dir: str) -> None:
        self.input_dir = input_dir

    def agent_rows(
        self, node_id: str, role: str, scenario: int,
    ) -> pd.DataFrame | None:
        path = os.path.join(self.input_dir, f"{result_table_name(node_id)}.csv")
        if not os.path.exists(path):
            logger.warning("missing CSV for %s: %s", node_id, path)
            return None
        df = pd.read_csv(path)
        return df[df["id_scenario"] == scenario]

    def environment_rows(self, scenario: int) -> pd.DataFrame:
        env_path = os.path.join(self.input_dir, "Result_Simulator_Environment.csv")
        edf = pd.read_csv(env_path)
        return edf[edf["id_scenario"] == scenario].sort_values("period")


class PostgresRunReader:
    """
    A run's per-instance rows from the sim_<role>_view views. Rows come back
    in period, then agent order - the order Melodie writes the CSVs in - so
    aggregation sums in the same order and the bundle matches the CSV one.
    """

    def __init__(self, conn, run_id: str) -> None:
        self.conn = conn
        self.run_id = run_id

    def agent_rows(
        self, node_id: str, role: str, scenario: int,
    ) -> pd.DataFrame | None:
        from sqlalchemy import text
        columns = ", ".join(_PROPS_BY_ROLE[role])
        query = text(
            f"SELECT period, agent_id AS id, {columns}"
            f" FROM {role_view_name(role)}"
            " WHERE run_id = :run_id AND id_scenario = :scenario"
            " AND entity_id = :entity_id ORDER BY period, agent_id"
        )
        df = pd.read_sql(query, self.conn, params={
            "run_id": self.run_id, "scenario": scenario, "entity_id": node_id,
        })
        if df.empty:
            logger.warning("no rows for %s in run %s", node_id, self.run_id)
            return None
        return df

    def environment_rows(self, scenario: int) -> pd.DataFrame:
        from sqlalchemy import text
        columns = ", ".join(csv_col for csv_col, _ in ENV_COLS)
        query = text(
            f"SELECT period, {columns}"
            f" FROM {role_view_name(ENVIRONMENT_ROLE)}"
            " WHERE run_id = :run_id AND id_scenario = :scenario"
            " ORDER BY period"
        )
        return pd.read_sql(query, self.conn, params={
            "run_id": self.run_id, "scenario": scenario,
        })


def build_bundle(
    source: str | CsvRunReader | PostgresRunReader, scenario: int, pdl: str,
) -> dict:
    """
    The bundle for one scenario of a run. source is a CSV run directory or a
    reader; everything after reading is shared, so the source cannot change
    the bundle.
    """
    reader = CsvRunReader(source) if isinstance(source, str) else source
    pdl_path = _resolve_pdl_path(pdl)
    roster = build_roster(pdl_path)
    adjacency = build_flow_adjacency(pdl_path)
    entities = _entity_metadata(pdl_path)
    sea_transports = {
        entry.archetype.name
        for entry in roster
        if entry.archetype.agent_class is Transport and not entry.entity_ids
    }

    nodes: list[dict] = []
    ticks: list[dict] = []

    for entry in roster:
        node_id = entry.archetype.name
        if node_id in sea_transports:
            continue
        nodes.append(_node_metadata(entry, entities))

        props = _PROPS_BY_ROLE.get(entry.archetype.role)
        if props is None:
            continue
        df = reader.agent_rows(node_id, entry.archetype.role, scenario)
        if df is None:
            continue
        for period, values in _aggregate(df, list(props)).items():
            ticks.append({"period": period, "nodeId": node_id, "values": values})

    edges = _collapsed_edges(adjacency, sea_transports, {node["id"] for node in nodes})

    # Environment series.
    env: list[dict] = []
    edf = reader.environment_rows(scenario)
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


def _postgres_bundle(run_id: str | None, scenario: int, pdl: str) -> dict:
    """
    The bundle for a run read from PostgreSQL: the named run, or the newest
    completed one in sim_run. The --pdl file must be the one the run was made
    with (sim_run.pdl_sha256), so one PDL's topology is never bound to another
    run's numbers.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import OperationalError

    url = PostgresDBConfig().sqlalchemy_url()
    engine = create_engine(url)
    try:
        try:
            engine.connect().close()
        except OperationalError as exc:
            masked = make_url(url).render_as_string(hide_password=True)
            raise RuntimeError(
                f"could not connect to Postgres at {masked}: {exc}"
            ) from exc

        with engine.connect() as conn:
            if run_id is None:
                run = conn.execute(text(
                    "SELECT run_id, status, pdl, pdl_sha256 FROM sim_run"
                    " WHERE status = 'completed'"
                    " ORDER BY run_id DESC LIMIT 1"
                )).one_or_none()
                if run is None:
                    raise RuntimeError("no completed run in sim_run")
            else:
                run = conn.execute(text(
                    "SELECT run_id, status, pdl, pdl_sha256 FROM sim_run"
                    " WHERE run_id = :run_id"
                ), {"run_id": run_id}).one_or_none()
                if run is None:
                    raise RuntimeError(f"run {run_id} is not in sim_run")
            if run.status != "completed":
                logger.warning("run %s has status %s", run.run_id, run.status)

            pdl_path = _resolve_pdl_path(pdl)
            digest = hashlib.sha256(pdl_path.read_bytes()).hexdigest()
            if digest != run.pdl_sha256:
                raise RuntimeError(
                    f"--pdl {pdl_path.name} is not the PDL run {run.run_id} "
                    f"was made with ({run.pdl or 'none recorded'})"
                )

            logger.info("Resolved run %s from sim_run", run.run_id)
            return build_bundle(
                PostgresRunReader(conn, run.run_id), scenario, pdl,
            )
    finally:
        engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    output_root = os.path.join(here, "data", "output")

    parser = argparse.ArgumentParser(description="Export a run's CSVs to the web bundle.json")
    parser.add_argument("--scenario", type=int, default=1,
                        help="id_scenario to export (0 = baseline, 1 = PDL shock). Default 1.")
    parser.add_argument("--input", type=str, default=None,
                        help="Directory holding Result_Simulator_*.csv.")
    parser.add_argument("--run", type=str, default=None,
                        help="Run id to export. Defaults to the newest completed run.")
    parser.add_argument("--output", type=str, default=os.path.join(repo_root, "web", "public", "bundle.json"),
                        help="Path to write bundle.json.")
    parser.add_argument("--pdl", type=str, default="s1-soja.pdl.yaml", help="PDL name for metadata.")
    parser.add_argument("--source", choices=("postgres", "csv"), default="postgres",
                        help="Read the run from PostgreSQL or from its CSV files. Default postgres.")
    args = parser.parse_args()

    if args.source == "postgres":
        if args.input is not None:
            parser.error("--input names a CSV directory; add --source csv to read it")
        try:
            bundle = _postgres_bundle(args.run, args.scenario, args.pdl)
        except RuntimeError as exc:
            parser.error(str(exc))
    else:
        if args.input is not None:
            input_dir = args.input
            logger.info(
                "Using explicit input directory %s; not resolved through the run registry",
                input_dir,
            )
        else:
            try:
                resolved_run_id = resolve_run(output_root, args.run)
            except RuntimeError as exc:
                parser.error(str(exc))
            input_dir = run_dir(output_root, resolved_run_id)
            logger.info("Resolved run %s at %s", resolved_run_id, input_dir)
        bundle = build_bundle(input_dir, args.scenario, args.pdl)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, ensure_ascii=False, separators=(",", ":"))

    logger.info("wrote %s — %d nodes, %d edges, %d ticks, %d env steps (scenario %d)",
                args.output, len(bundle["nodes"]), len(bundle["edges"]),
                len(bundle["ticks"]), len(bundle["env"]), args.scenario)


if __name__ == "__main__":
    main()
