"""Isolated PostgreSQL fixtures for the playback contract."""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from provider_simenv.db_schema import ENVIRONMENT_PROPS, initialize_schema
from provider_simenv.tick_writer import TickWriter


@pytest.fixture
def playback_db():
    url = os.environ.get("SIMENV_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("set SIMENV_TEST_POSTGRES_URL")
    engine = create_engine(url)
    # Each test uses its own schema so catalogues and mutations stay isolated.
    schema = "test_" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    initialize_schema(test_engine)
    yield test_engine
    test_engine.dispose()
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


def seed_run(engine, identity="run-1", status="completed", scene=True):
    snapshot = {"schema_version": 1, "pdl": "test.yaml", "honesty_note": "Approximate",
                "nodes": [], "edges": []} if scene else None
    writer = TickWriter(engine)
    writer.open_run({
        "run_id": identity, "started_at": datetime.now(timezone.utc), "finished_at": None,
        "status": "running", "pdl": "test.yaml", "pdl_sha256": None, "roster_sha256": None,
        "scenario_ids": [0, 1], "period_num": 3, "git_sha": None, "label": identity,
    }, scene=snapshot)
    conn = writer._conn
    for entity, role, agent in [("farm", "producer", 0), ("farm", "producer", 1),
                                ("environment", "environment", 0)]:
        key = conn.execute(text(
            "INSERT INTO sim_agent (run_id,entity_id,role,agent_id)"
            " VALUES (:run,:entity,:role,:agent) RETURNING agent_key"
        ), {"run": identity, "entity": entity, "role": role, "agent": agent}).scalar_one()
        props = ENVIRONMENT_PROPS if entity == "environment" else ["unit_price"]
        for scenario in [0, 1]:
            for period in range(3):
                for prop in props:
                    conn.execute(text(
                        "INSERT INTO sim_tick (agent_key,id_scenario,metric_id,period,value)"
                        " SELECT :key,:scenario,metric_id,:period,:value FROM sim_metric WHERE name=:prop"
                    ), {"key": key, "scenario": scenario, "period": period, "prop": prop,
                        "value": 1.123456789012345 + agent + scenario + period})
    conn.commit()
    writer.close_run(identity, status=status)
