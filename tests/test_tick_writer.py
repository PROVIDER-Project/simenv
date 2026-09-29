import re
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

from provider_simenv import db_schema, run_registry
from provider_simenv.data_collector import _PROPS_BY_ROLE, ENVIRONMENT_PROPS
from provider_simenv.db_config import PostgresDBConfig
from provider_simenv.tick_writer import TickWriter

TEST_SCHEMA_PREFIX = "simenv_test_"


@pytest.fixture(autouse=True)
def stable_git_sha(monkeypatch):
    monkeypatch.setattr(run_registry, "git_sha", lambda: "abc123")


class FakeConnection:
    def __init__(self):
        self.inserted = []

    def execute(self, statement, params):
        self.inserted.append(params)
        key = len(self.inserted)
        return SimpleNamespace(scalar_one=lambda: key)


def table_columns(ddl: str) -> list[str]:
    body = ddl[ddl.index("(") + 1:ddl.rindex(")")]
    columns = []
    for line in body.splitlines():
        words = line.split()
        if words and words[0] not in ("CHECK", "PRIMARY", "UNIQUE"):
            columns.append(words[0])
    return columns


def view_statement(name: str) -> str:
    (statement,) = [
        s for s in db_schema.VIEW_DDL
        if f"CREATE OR REPLACE VIEW {name} AS" in s
    ]
    return statement


def test_catalogue_matches_recorded_metrics():
    names = [metric.name for metric in db_schema.METRICS]
    recorded = {prop for props in _PROPS_BY_ROLE.values() for prop in props}
    recorded |= set(ENVIRONMENT_PROPS)

    assert len(names) == len(set(names))
    assert set(names) == recorded


def test_stored_units_are_plain_ascii():
    for metric in db_schema.METRICS:
        assert metric.unit.isascii(), metric.name


def test_run_record_keys_match_sim_run_columns():
    (sim_run_ddl,) = [
        s for s in db_schema.DDL if "TABLE IF NOT EXISTS sim_run" in s
    ]
    record = run_registry.run_record(
        "20260929T120411Z-f465c8d8",
        pdl=None,
        scenario_ids=[0, 1],
        period_num=365,
    )

    assert list(record) == table_columns(sim_run_ddl)


def test_missing_metric_emits_no_row():
    writer = TickWriter(None)
    writer._metric_ids = {
        "quantity_available": 1, "unit_price": 2, "active": 6,
    }
    agent = SimpleNamespace(
        quantity_available=5, unit_price=None, active=True,
    )

    rows = writer._value_rows(
        agent,
        ("quantity_available", "unit_price", "active", "storage_utilization"),
        agent_key=7,
        id_scenario=1,
        t=3,
    )

    assert rows == [
        {"agent_key": 7, "id_scenario": 1, "metric_id": 1, "period": 3,
         "value": 5.0},
        {"agent_key": 7, "id_scenario": 1, "metric_id": 6, "period": 3,
         "value": 1.0},
    ]
    assert all(type(row["value"]) is float for row in rows)


@pytest.mark.parametrize(
    "name", ["unit_price'; --", "Producer", "feed trader", "", "1role"],
)
def test_identifier_rejects_unsafe_names(name):
    with pytest.raises(ValueError):
        db_schema._identifier(name)


def test_view_set_is_fixed():
    roles = [*_PROPS_BY_ROLE, db_schema.ENVIRONMENT_ROLE]

    assert {db_schema.role_view_name(role) for role in roles} == {
        "sim_producer_view",
        "sim_consumer_view",
        "sim_wholesaler_view",
        "sim_processor_view",
        "sim_feed_manufacturer_view",
        "sim_feed_trader_view",
        "sim_environment_view",
    }
    assert len(db_schema.VIEW_DDL) == len(roles) + 1
    view_statement(db_schema.SIM_TICK_READABLE_VIEW)


@pytest.mark.parametrize(
    "view, columns",
    [
        ("sim_producer_view",
         ["quantity_available", "unit_price", "active"]),
        ("sim_consumer_view",
         ["feed_received", "livestock_output", "active"]),
        ("sim_wholesaler_view",
         ["quantity_available", "unit_price", "storage_utilization"]),
        ("sim_processor_view", ["quantity_available", "unit_price"]),
        ("sim_feed_manufacturer_view", ["quantity_available", "unit_price"]),
        ("sim_feed_trader_view", ["quantity_available", "unit_price"]),
        ("sim_environment_view",
         ["soy_price", "feed_price", "shock_scale", "drought_severity",
          "total_soy_supply", "transport_utilisation", "current_step"]),
    ],
)
def test_role_view_metric_columns_are_fixed(view, columns):
    assert re.findall(r" AS (\w+)", view_statement(view)) == columns


def test_environment_view_has_no_agent_columns():
    statement = view_statement(
        db_schema.role_view_name(db_schema.ENVIRONMENT_ROLE)
    )

    assert "entity_id" not in statement
    assert "agent_id" not in statement


def test_write_tick_before_open_run_raises():
    writer = TickWriter(None)

    with pytest.raises(RuntimeError, match="open_run"):
        writer.write_tick(None, id_scenario=0, run_id="r", t=0)


def test_agent_is_registered_once_per_run():
    writer = TickWriter(None)
    conn = FakeConnection()

    first = writer._agent_key(conn, "r", "brazil_farms", "producer", 0)
    second = writer._agent_key(conn, "r", "brazil_farms", "producer", 0)

    assert first == second
    assert len(conn.inserted) == 1


def test_environment_entity_collision_reaches_the_database():
    writer = TickWriter(None)
    conn = FakeConnection()

    environment = writer._agent_key(
        conn, "r", db_schema.ENVIRONMENT_ENTITY_ID,
        db_schema.ENVIRONMENT_ROLE, db_schema.ENVIRONMENT_AGENT_ID,
    )
    impostor = writer._agent_key(conn, "r", "environment", "producer", 0)

    assert environment != impostor
    assert [row["role"] for row in conn.inserted] == [
        "environment", "producer",
    ]


@pytest.fixture
def live_engine():
    pytest.importorskip("psycopg2")
    url = PostgresDBConfig().sqlalchemy_url()
    schema = f"{TEST_SCHEMA_PREFIX}{uuid4().hex[:12]}"
    admin = create_engine(url)
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            conn.commit()
    except OperationalError as exc:
        admin.dispose()
        pytest.skip(f"Postgres unreachable: {exc}")
    engine = create_engine(
        url, connect_args={"options": f"-csearch_path={schema}"},
    )
    try:
        yield engine
    finally:
        engine.dispose()
        if not schema.startswith(TEST_SCHEMA_PREFIX):
            raise RuntimeError(f"refusing to drop schema {schema!r}")
        with admin.connect() as conn:
            conn.execute(text("SET lock_timeout = '5s'"))
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            conn.commit()
        admin.dispose()


def new_record() -> dict:
    return run_registry.run_record(
        run_registry.new_run_id(),
        pdl=None,
        scenario_ids=[0, 1],
        period_num=2,
    )


def fake_model():
    farms = [
        SimpleNamespace(
            id=0, quantity_available=10.0, unit_price=2.5, active=True,
        ),
        SimpleNamespace(
            id=1, quantity_available=0.0, unit_price=0.0, active=False,
        ),
    ]
    return SimpleNamespace(
        _roster=[
            SimpleNamespace(
                archetype=SimpleNamespace(
                    name="brazil_farms", role="producer",
                ),
            ),
        ],
        brazil_farms=SimpleNamespace(agents=farms),
        environment=SimpleNamespace(
            soy_price=500.0,
            feed_price=1200.0,
            shock_scale=0.0,
            drought_severity=0.0,
            total_soy_supply=10.0,
            transport_utilisation=0.5,
            current_step=0,
        ),
    )


def test_live_round_trip_through_views(live_engine):
    record = new_record()
    run_id = record["run_id"]
    model = fake_model()
    writer = TickWriter(live_engine)

    writer.open_run(record)
    for id_scenario in (0, 1):
        for t in (0, 1):
            writer.write_tick(model, id_scenario, run_id, t)
    writer.close_run(run_id, status="completed")

    with live_engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM sim_run WHERE run_id = :r"),
            {"r": run_id},
        ).scalar_one()
        agents = conn.execute(text("SELECT count(*) FROM sim_agent")).scalar()
        values = conn.execute(
            text("SELECT count(*) FROM sim_tick_readable")
        ).scalar()
        producer_rows = conn.execute(
            text(
                "SELECT agent_id, unit_price, active FROM sim_producer_view"
                " WHERE id_scenario = 1 AND period = 1 ORDER BY agent_id"
            )
        ).all()
        environment_rows = conn.execute(
            text("SELECT count(*) FROM sim_environment_view")
        ).scalar()

    assert status == "completed"
    assert agents == 3
    assert values == 2 * 2 * (2 * 3 + len(ENVIRONMENT_PROPS))
    assert [tuple(row) for row in producer_rows] == [
        (0, 2.5, True), (1, 0.0, False),
    ]
    assert environment_rows == 2 * 2


def test_live_environment_collision_fails_on_unique_constraint(live_engine):
    record = new_record()
    run_id = record["run_id"]
    writer = TickWriter(live_engine)
    writer.open_run(record)

    with live_engine.connect() as conn:
        writer._agent_key(
            conn, run_id, db_schema.ENVIRONMENT_ENTITY_ID,
            db_schema.ENVIRONMENT_ROLE, db_schema.ENVIRONMENT_AGENT_ID,
        )
        with pytest.raises(IntegrityError):
            writer._agent_key(conn, run_id, "environment", "producer", 0)

    writer.close_run(run_id, status="failed")


def test_live_unit_mismatch_fails_and_keeps_stored_unit(live_engine):
    first = new_record()
    writer = TickWriter(live_engine)
    writer.open_run(first)
    writer.close_run(first["run_id"], status="completed")
    with live_engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE sim_metric SET unit = 'tonnes'"
                " WHERE name = 'unit_price'"
            )
        )
        conn.commit()

    second = new_record()
    writer = TickWriter(live_engine)
    with pytest.raises(RuntimeError, match="unit_price"):
        writer.open_run(second)
    writer.close_run(second["run_id"], status="failed")

    with live_engine.connect() as conn:
        unit = conn.execute(
            text("SELECT unit FROM sim_metric WHERE name = 'unit_price'")
        ).scalar_one()
        status = conn.execute(
            text("SELECT status FROM sim_run WHERE run_id = :r"),
            {"r": second["run_id"]},
        ).scalar_one()

    assert unit == "tonnes"
    assert status == "failed"
