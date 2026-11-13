"""Transport impairment survives simulation, collection and public export."""

import json
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd
import pytest
from sqlalchemy import text
from test_tick_writer import FakeConnection

from provider_simenv import db_schema, export_bundle, run_registry
from provider_simenv.data_collector import result_table_name
from provider_simenv.event_tracker import EventTracker
from provider_simenv.model import DEFAULT_PDL, SupplyChainModel
from provider_simenv.playback.store import PlaybackStore
from provider_simenv.scenario import SupplyChainScenario
from provider_simenv.scene import build_scene
from provider_simenv.tick_writer import TickWriter

SEA = "sea_transport_santos_port__rotterdam_port"
TRANSPORT_PROPS = (
    "quantity_available", "unit_price", "utilisation", "capacity", "active",
    "effective_capacity",
)


def congestion_model(base_yield=100.) -> Any:
    model: Any = SupplyChainModel(
        cast(Any, SimpleNamespace()), SupplyChainScenario(1),
    )
    model._setup()
    model.brazil_farms.agents[0].base_yield = base_yield
    model.environment._tracker = EventTracker(
        events=[{"id": "congestion", "entity": "santos_port",
                 "impacts": {"supply": .2}, "duration": 2}],
        timeline=[{"at_day": 1, "event_id": "congestion"}],
    )
    return model


@pytest.mark.parametrize("base_yield,quantities,feeds,utils", [
    (100., [70., 70., 70., 70.], [240., 240., 240., 240.],
     [.14, .7, .7, .14]),
    (200., [140., 100., 100., 140.], [320., 288., 288., 320.],
     [.28, 1., 1., .28]),
])
def test_congestion_onset_and_recovery_preserve_real_capacity_semantics(
    base_yield, quantities, feeds, utils,
):
    model = congestion_model(base_yield)
    port = model.santos_port.agents[0]
    prices = []
    for day in range(4):
        model._do_step(day)
        assert port.capacity == 500.
        assert port.effective_capacity == [500., 100., 100., 500.][day]
        assert port.quantity_available == quantities[day]
        assert port.utilisation == utils[day]
        assert model.eu_feed_trader.agents[0].quantity_available == feeds[day]
        prices.append(model.environment.feed_price)
    assert prices[0] == prices[3]
    if base_yield == 100.:
        assert prices[0] == prices[1]
    else:
        assert prices[1] > prices[0]
    # Observability must not become provider-owned state or a mutable setting.
    assert "effective_capacity" not in port._state()
    with pytest.raises(AttributeError):
        port.effective_capacity = 0.


def test_csv_collection_and_export_include_ports_but_hide_sea_nodes(tmp_path):
    model = congestion_model()
    model._do_step(0)
    model._do_step(1)
    collector = model.data_collector
    # Use the real collected tables and CSV serialization, without opening a DB.
    assert "santos_port" in collector.agent_properties_dict
    assert SEA in collector.agent_properties_dict
    for name, table in collector.agent_properties_dict.items():
        table.to_file(str(tmp_path / f"{result_table_name(name)}.csv"))
    collector.environment_properties_list.to_file(
        str(tmp_path / "Result_Simulator_Environment.csv"),
    )
    for name, expected in (("santos_port", [500., 100.]),
                           (SEA, [1000., 1000.])):
        frame = pd.read_csv(tmp_path / f"{result_table_name(name)}.csv")
        assert set(TRANSPORT_PROPS).issubset(frame.columns)
        assert frame["effective_capacity"].tolist() == expected
        assert frame["quantity_available"].tolist() == [70., 70.]
    bundle = export_bundle.build_bundle(str(tmp_path), 1, str(DEFAULT_PDL))
    nodes = {node["id"]: node for node in bundle["nodes"]}
    assert nodes["santos_port"]["hasRecordedData"] is True
    assert SEA not in nodes
    assert all(tick["nodeId"] != SEA for tick in bundle["ticks"])
    port_ticks = [tick["values"] for tick in bundle["ticks"]
                  if tick["nodeId"] == "santos_port"]
    assert port_ticks == [
        {"quantity_available": 70., "unit_price": 742.0286,
         "utilisation": .14, "capacity": 500., "active": True,
         "effective_capacity": 500.},
        {"quantity_available": 70., "unit_price": 742.0286,
         "utilisation": .7, "capacity": 500., "active": True,
         "effective_capacity": 100.},
    ]
    json.dumps(bundle, allow_nan=False)


def test_tick_writer_records_individual_port_and_sea_measurements():
    model = congestion_model()
    model._do_step(1)
    writer = TickWriter(None)
    writer._metric_ids = {m.name: i for i, m in enumerate(db_schema.METRICS)}
    conn = FakeConnection()
    rows = writer._agent_rows(conn, model, 1, "transport", 1)
    for entity, role, expected in (
        ("santos_port", "land_transport", 100.),
        (SEA, "sea_transport", 1000.),
    ):
        agent_key = writer._agent_keys.get((entity, role, 0))
        assert agent_key is not None, f"missing recorded transport {entity}"
        values = {db_schema.METRICS[row["metric_id"]].name: row["value"]
                  for row in rows if row["agent_key"] == agent_key}
        assert set(values) == set(TRANSPORT_PROPS)
        assert values["quantity_available"] == 70.
        assert values["effective_capacity"] == expected


def test_transport_aggregation_weights_utilisation_by_effective_capacity():
    frame = pd.DataFrame([
        {"period": 0, "quantity_available": 50., "capacity": 100.,
         "effective_capacity": 100., "utilisation": .5,
         "unit_price": 10., "active": False},
        {"period": 0, "quantity_available": 300., "capacity": 600.,
         "effective_capacity": 300., "utilisation": 1.,
         "unit_price": 20., "active": True},
    ])
    assert export_bundle._aggregate(frame, list(TRANSPORT_PROPS)) == {0: {
        "quantity_available": 350., "capacity": 700.,
        "effective_capacity": 400., "utilisation": .875,
        "unit_price": 15., "active": True,
    }}


@pytest.mark.parametrize("rows,expected", [
    ([{"utilisation": .5}], None),
    ([{"effective_capacity": 100.}], None),
    ([{"utilisation": .5, "effective_capacity": None}], None),
    ([{"utilisation": None, "effective_capacity": 100.}], None),
    ([{"utilisation": 0., "effective_capacity": 0.}], None),
    ([{"utilisation": .5, "effective_capacity": 100.},
      {"utilisation": None, "effective_capacity": 100.}], None),
    ([{"utilisation": .5, "effective_capacity": 100.},
      {"utilisation": 1., "effective_capacity": None}], None),
    ([{"utilisation": 0., "effective_capacity": 100.}], 0.),
])
def test_utilisation_missing_weights_or_values_is_not_fabricated(rows, expected):
    frame = pd.DataFrame([{"period": 0, **row} for row in rows])
    result = export_bundle._aggregate(frame, ["utilisation"])
    assert result == {0: {"utilisation": expected}}
    json.dumps(result, allow_nan=False)


def test_all_missing_metrics_remain_null_and_absent_columns_stay_absent():
    frame = pd.DataFrame([{
        "period": 0, "quantity_available": None, "capacity": None,
        "effective_capacity": None, "unit_price": None, "active": None,
    }])
    result = export_bundle._aggregate(frame, list(TRANSPORT_PROPS))
    assert result == {0: dict.fromkeys(TRANSPORT_PROPS)}
    json.dumps(result, allow_nan=False)
    assert export_bundle._aggregate(
        pd.DataFrame([{"period": 0, "unit_price": 5.}]),
        ["unit_price", "effective_capacity"],
    ) == {0: {"unit_price": 5.}}


@pytest.mark.parametrize("port_rows", [
    None,
    [{"period": 0, "id_scenario": 0, "quantity_available": 70.}],
    [{"period": 0, "id_scenario": 1, "quantity_available": None}],
])
def test_historical_csv_does_not_invent_transport_ticks(tmp_path, port_rows):
    pd.DataFrame([{"period": 0, "id_scenario": 1, **{
        name: 0. for name, _ in export_bundle.ENV_COLS
    }}]).to_csv(tmp_path / "Result_Simulator_Environment.csv", index=False)
    if port_rows is not None:
        pd.DataFrame(port_rows).to_csv(
            tmp_path / f"{result_table_name('santos_port')}.csv", index=False,
        )
    bundle = export_bundle.build_bundle(str(tmp_path), 1, str(DEFAULT_PDL))
    nodes = {node["id"]: node for node in bundle["nodes"]}
    assert nodes["santos_port"]["hasRecordedData"] is False
    assert nodes["paranagua_port"]["hasRecordedData"] is False
    assert all(value is None for tick in bundle["ticks"]
               for value in tick["values"].values())
    json.dumps(bundle, allow_nan=False)


@pytest.mark.parametrize("role", ["land_transport", "sea_transport"])
@pytest.mark.parametrize("metric", [
    "quantity_available", "capacity", "effective_capacity",
])
def test_transport_partial_extensive_measurements_are_not_totals(role, metric):
    frame = pd.DataFrame([
        {"period": 0, metric: 100.}, {"period": 0, metric: None},
    ])
    # Exercise public export to ensure it chooses strict transport aggregation.
    class PartialReader:
        def agent_rows(self, node_id, recorded_role, scenario):
            return frame if node_id == "santos_port" else None

        def environment_rows(self, scenario):
            return pd.DataFrame({"period": []})

    if role == "land_transport":
        bundle = export_bundle.build_bundle(
            cast(Any, PartialReader()), 1, str(DEFAULT_PDL),
        )
        assert bundle["ticks"][0]["values"][metric] is None
    assert export_bundle._aggregate(frame, [metric], role=role) == {
        0: {metric: None},
    }
    # Other roles retain their existing partial-observation behavior.
    assert export_bundle._aggregate(frame, [metric], role="producer") == {
        0: {metric: 100.},
    }


@pytest.mark.parametrize("source", ["export", "scene"])
def test_legacy_db_scene_and_export_use_recorded_measurements(
    playback_db, source,
):
    model = congestion_model()
    model._do_step(0)
    writer = TickWriter(playback_db)
    writer.open_run(run_registry.run_record(
        "legacy", pdl=str(DEFAULT_PDL), scenario_ids=[1], period_num=1,
    ))
    writer.write_tick(model, 1, "legacy", 0)
    writer.close_run("legacy", status="completed")
    with playback_db.begin() as conn:
        # Keep agent identities but remove all transport measurements, as an
        # older/partial recording might have. Identity alone is not evidence.
        conn.execute(text(
            "DELETE FROM sim_tick WHERE agent_key IN "
            "(SELECT agent_key FROM sim_agent WHERE run_id='legacy' "
            "AND role IN ('land_transport', 'sea_transport'))"
        ))
        # One port really was recorded; the reconstructed flag must detect it.
        conn.execute(text(
            "INSERT INTO sim_tick "
            "(agent_key, id_scenario, period, metric_id, value) "
            "SELECT a.agent_key, 1, 0, m.metric_id, 30. "
            "FROM sim_agent a CROSS JOIN sim_metric m "
            "WHERE a.run_id='legacy' AND a.entity_id='paranagua_port' "
            "AND m.name='quantity_available'"
        ))
        bundle = export_bundle.build_bundle(
            export_bundle.PostgresRunReader(conn, "legacy"),
            1, str(DEFAULT_PDL),
        )
    scene = PlaybackStore(playback_db).get_scene("legacy", 1)
    nodes = bundle["nodes"] if source == "export" else scene.nodes
    flags = {node["id"]: node["hasRecordedData"] for node in nodes}
    assert flags["santos_port"] is False
    assert flags["paranagua_port"] is True
    assert flags["brazil_farms"] is True
    json.dumps(bundle, allow_nan=False)


def test_stored_scene_flags_are_not_rewritten_from_measurements(playback_db):
    scene = build_scene(DEFAULT_PDL)
    for node in scene["nodes"]:
        node["hasRecordedData"] = node["id"] == "santos_port"
    writer = TickWriter(playback_db)
    writer.open_run(run_registry.run_record(
        "snapshot", pdl=str(DEFAULT_PDL), scenario_ids=[1], period_num=1,
    ), scene=scene)
    writer.close_run("snapshot", status="completed")
    received = PlaybackStore(playback_db).get_scene("snapshot", 1)
    assert received.nodes == scene["nodes"]


def test_live_transport_views_and_playback_preserve_individuals(playback_db):
    model = congestion_model()
    # Two different handlers in the same list must remain separate in raw data.
    ports = model.santos_port
    first = ports.agents[0]
    extra = ports.add(params=first._state())
    extra.list_name = "santos_port"
    extra.binding = dict(first.binding)
    extra.capacity = 250.
    scene = build_scene(DEFAULT_PDL)
    assert next(n for n in scene["nodes"] if n["id"] == "santos_port")[
        "hasRecordedData"
    ] is True
    writer = TickWriter(playback_db)
    record = run_registry.run_record(
        "transport", pdl=str(DEFAULT_PDL), scenario_ids=[1], period_num=2,
    )
    writer.open_run(record, scene=scene)
    for day in (0, 1):
        model._do_step(day)
        writer.write_tick(model, 1, "transport", day)
    writer.close_run("transport", status="completed")
    with playback_db.connect() as conn:
        ports = conn.execute(text(
            "SELECT agent_id, effective_capacity FROM sim_land_transport_view"
            " WHERE entity_id='santos_port' AND period=1 ORDER BY agent_id"
        )).all()
        assert [tuple(row) for row in ports] == [(first.id, 100.), (extra.id, 50.)]
        sea = conn.execute(text(
            "SELECT quantity_available, effective_capacity "
            "FROM sim_sea_transport_view WHERE entity_id=:entity AND period=1"
        ), {"entity": SEA}).one()
        assert tuple(sea) == (70., 1000.)
    frames = PlaybackStore(playback_db).get_frames("transport", 1, 1, 1)
    agents = frames.frames[0].agents
    assert len([a for a in agents if a.entity_id == "santos_port"]) == 2
    assert next(a for a in agents if a.entity_id == SEA).values[
        "effective_capacity"
    ] == 1000.
