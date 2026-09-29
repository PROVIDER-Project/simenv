import json
import os
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from provider_simenv import export_bundle, run_registry
from provider_simenv.data_collector import result_table_name
from provider_simenv.db_config import PostgresDBConfig
from provider_simenv.db_schema import (
    ENVIRONMENT_AGENT_ID,
    ENVIRONMENT_ENTITY_ID,
)

PARITY_RUN_VAR = "PROVIDER_SIMENV_PARITY_RUN"
OUTPUT_ROOT = Path(run_registry.__file__).parent / "data" / "output"
ENVIRONMENT_CSV = "Result_Simulator_Environment.csv"
KEY_COLUMNS = {"id_scenario", "id_run", "period", "id"}


def bundle_text(bundle: dict) -> str:
    meta = {**bundle["meta"], "generatedAt": ""}
    return json.dumps(
        {**bundle, "meta": meta}, ensure_ascii=False, separators=(",", ":"),
    )


def first_difference(left: str, right: str) -> str:
    for i, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return (
                f"char {i}: csv ...{left[max(0, i - 60):i + 60]}... "
                f"postgres ...{right[max(0, i - 60):i + 60]}..."
            )
    return f"lengths {len(left)} and {len(right)}"


def csv_values(path: Path, entity_id: str) -> dict:
    frame = pd.read_csv(path, float_precision="round_trip")
    metrics = [c for c in frame.columns if c not in KEY_COLUMNS]
    values = {}
    for row in frame.to_dict("records"):
        agent_id = int(row["id"]) if "id" in row else ENVIRONMENT_AGENT_ID
        for metric in metrics:
            value = row[metric]
            if pd.isna(value):
                continue
            key = (
                int(row["id_scenario"]), int(row["period"]),
                entity_id, agent_id, metric,
            )
            values[key] = float(value)
    return values


@pytest.fixture(scope="module")
def parity():
    requested = os.environ.get(PARITY_RUN_VAR)
    if not requested:
        pytest.skip(f"opt-in: set {PARITY_RUN_VAR} to a run id or 'latest'")
    pytest.importorskip("psycopg2")
    run_id = run_registry.resolve_run(
        str(OUTPUT_ROOT), None if requested == "latest" else requested,
    )

    engine = create_engine(PostgresDBConfig().sqlalchemy_url())
    try:
        engine.connect().close()
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"Postgres unreachable: {exc}")
    with engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM sim_run WHERE run_id = :r"),
            {"r": run_id},
        ).scalar_one_or_none()
        entities = conn.execute(
            text(
                "SELECT DISTINCT entity_id FROM sim_agent WHERE run_id = :r"
            ),
            {"r": run_id},
        ).scalars().all()
        rows = conn.execute(
            text(
                "SELECT id_scenario, period, entity_id, agent_id, metric,"
                " value FROM sim_tick_readable WHERE run_id = :r"
            ),
            {"r": run_id},
        ).all()
    engine.dispose()
    if status is None:
        pytest.fail(f"run {run_id} has no sim_run row")

    file_entity = {
        f"{result_table_name(entity)}.csv": entity
        for entity in entities if entity != ENVIRONMENT_ENTITY_ID
    }
    file_entity[ENVIRONMENT_CSV] = ENVIRONMENT_ENTITY_ID

    csv = {}
    unmatched = []
    run_path = OUTPUT_ROOT / run_id
    for path in sorted(run_path.glob("Result_Simulator_*.csv")):
        entity_id = file_entity.get(path.name)
        if entity_id is None:
            unmatched.append(path.name)
            continue
        csv.update(csv_values(path, entity_id))

    db = {
        (row.id_scenario, row.period, row.entity_id, row.agent_id,
         row.metric): row.value
        for row in rows
    }
    return run_id, csv, db, unmatched


def test_live_parity_csv_values_are_in_postgres(parity):
    run_id, csv, db, unmatched = parity
    missing = csv.keys() - db.keys()

    assert csv, f"no CSV values found for run {run_id}"
    assert unmatched == [], (
        f"CSV files with no entity in sim_agent: {unmatched}"
    )
    assert not missing, (
        f"{len(missing)} CSV values missing from Postgres, "
        f"e.g. {sorted(missing)[:5]}"
    )


def test_live_parity_postgres_has_nothing_extra(parity):
    _run_id, csv, db, _unmatched = parity
    extra = db.keys() - csv.keys()

    assert not extra, (
        f"{len(extra)} Postgres values not in the CSVs, "
        f"e.g. {sorted(extra)[:5]}"
    )


def test_live_parity_values_are_identical(parity):
    _run_id, csv, db, _unmatched = parity
    differing = sorted(
        (key, csv[key], db[key])
        for key in csv.keys() & db.keys()
        if csv[key] != db[key]
    )

    assert not differing, (
        f"{len(differing)} values differ (key, csv, postgres), "
        f"e.g. {differing[:5]}"
    )


def test_live_parity_bundle_is_identical(parity):
    run_id, _csv, _db, _unmatched = parity
    engine = create_engine(PostgresDBConfig().sqlalchemy_url())
    with engine.connect() as conn:
        run = conn.execute(
            text("SELECT pdl, scenario_ids FROM sim_run WHERE run_id = :r"),
            {"r": run_id},
        ).one()
    engine.dispose()
    if run.pdl is None:
        pytest.skip(f"run {run_id} recorded no PDL to export it with")

    for scenario in run.scenario_ids:
        from_csv = bundle_text(export_bundle.build_bundle(
            str(OUTPUT_ROOT / run_id), scenario, run.pdl,
        ))
        from_postgres = bundle_text(export_bundle._postgres_bundle(
            run_id, scenario, run.pdl,
        ))

        assert from_csv == from_postgres, (
            f"scenario {scenario} bundles differ at "
            f"{first_difference(from_csv, from_postgres)}"
        )
