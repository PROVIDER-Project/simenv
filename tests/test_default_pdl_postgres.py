"""A run started without --pdl records the default topology in Postgres and exports."""

import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from provider_simenv import execution, export_bundle
from provider_simenv.db_schema import initialize_schema

SCENARIOS = Path(__file__).parents[1] / "src/provider_simenv/scenarios"
PDL_NAME = "s1-soja.pdl.yaml"
ROSTER_NAME = "s1-soja.roster.yaml"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def scoped_db(monkeypatch):
    url = os.environ.get("SIMENV_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("set SIMENV_TEST_POSTGRES_URL")
    schema = "test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = make_url(url).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    ).render_as_string(hide_password=False)
    engine = create_engine(scoped)
    initialize_schema(engine)
    monkeypatch.setenv("PROVIDER_SIMENV_POSTGRES_URL", scoped)
    yield engine
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def test_run_without_pdl_is_recorded_and_exports(tmp_path, monkeypatch, scoped_db):
    private = tmp_path / "input"
    private.mkdir()
    rows = pd.read_csv(execution.INPUT_DIR / "SimulatorScenarios_template.csv")
    rows["period_num"] = 2
    rows.to_csv(private / "SimulatorScenarios_template.csv", index=False)
    monkeypatch.setattr(execution, "INPUT_DIR", private)
    monkeypatch.setattr(execution, "OUTPUT_ROOT", tmp_path / "output")

    execution.execute_cli(pdl=None, cascade=None, label=None, postgres_url=None)

    manifest = json.loads((tmp_path / "output/runs.json").read_text())
    run_id = manifest["runs"][0]["run_id"]
    with scoped_db.connect() as conn:
        run = conn.execute(
            text(
                "SELECT status, pdl, pdl_sha256, roster_sha256, cascade, scene"
                " FROM sim_run WHERE run_id = :r"
            ),
            {"r": run_id},
        ).one()
    assert run.status == "completed"
    assert run.pdl == PDL_NAME
    assert run.pdl_sha256 == sha256(SCENARIOS / PDL_NAME)
    assert run.roster_sha256 == sha256(SCENARIOS / ROSTER_NAME)
    assert run.cascade is None
    assert run.scene["pdl"] == PDL_NAME

    bundle_path = tmp_path / "bundle.json"
    monkeypatch.setattr(
        sys, "argv",
        ["export_bundle", "--run", run_id, "--output", str(bundle_path)],
    )
    export_bundle.main()
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert bundle["meta"]["pdl"] == PDL_NAME
    assert bundle["meta"]["ticks"] == 2
