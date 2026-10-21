import os

import pytest
from sqlalchemy import create_engine, text

from provider_simenv.db_schema import initialize_schema
from provider_simenv.tick_writer import TickWriter


@pytest.fixture
def pg_engine():
    url = os.environ.get("SIMENV_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("set SIMENV_TEST_POSTGRES_URL to an isolated test database")
    engine = create_engine(url)
    initialize_schema(engine)
    yield engine
    engine.dispose()


def test_schema_is_repeatable_and_scene_round_trips(pg_engine):
    from datetime import datetime, timezone
    from uuid import uuid4

    identity = str(uuid4())
    record = {"run_id": identity, "started_at": datetime.now(timezone.utc),
              "finished_at": None, "status": "running", "pdl": "example.yaml",
              "pdl_sha256": None, "roster_sha256": None, "scenario_ids": [0],
              "period_num": 2, "git_sha": None, "label": "test"}
    writer = TickWriter(pg_engine)
    writer.open_run(record, scene={"schema_version": 1, "nodes": [], "edges": []})
    writer.close_run(identity, status="completed")
    initialize_schema(pg_engine)
    with pg_engine.connect() as conn:
        scene = conn.execute(text("SELECT scene FROM sim_run WHERE run_id=:id"),
                             {"id": identity}).scalar_one()
    assert scene == {"schema_version": 1, "nodes": [], "edges": []}
