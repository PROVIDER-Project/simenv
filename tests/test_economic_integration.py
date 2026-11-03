"""Economic settings, shocks and recorded/exported contracts work together."""

import json
from typing import Any

import pandas as pd
import pytest
from provider_agents.offis_agents import ProcessProviderAgent
from sqlalchemy import text
from test_economic_config import SHIPPED, configured_pdl, model_for

from provider_simenv import db_schema, export_bundle, run_registry
from provider_simenv.data_collector import _PROPS_BY_ROLE, result_table_name
from provider_simenv.model import SupplyChainModel
from provider_simenv.tick_writer import TickWriter


def test_real_model_constrains_input_and_reprices_only_exposed_costs(
    tmp_path, monkeypatch,
):
    pdl = configured_pdl(tmp_path, {"eu_oil_mills": {
        "parameters": {"throughput_capacity": 100., "conversion_ratio": .8,
                       "fixed_costs": 100., "margin": .1,
                       "input_cost_shares": {"fuel": .25}},
        "bindings": {"fuel": ["gas_supply", "price"]},
    }})
    model = model_for(pdl, monkeypatch)
    model.scenario.period_num = 2
    # Exercise real tracker timing: baseline tick, then physical and price shocks.
    monkeypatch.setattr(SupplyChainModel, "_event_registry", {
        "events": [
            {"id": "closure", "entity": "eu_oil_mills",
             "impacts": {"supply": .5}},
            {"id": "fuel", "entity": "gas_supply",
             "impacts": {"price": 2.}},
        ],
        "timeline": [{"at_day": 1, "event_id": "closure"},
                     {"at_day": 1, "event_id": "fuel"}],
    }, raising=False)
    for snapshot in model.run_stepwise():
        process = model.eu_oil_mills.agents[0]
        assert snapshot["step"] in (0, 1)
        shocked = snapshot["step"] == 1
        processed, output, cost = (50., 40., 125.) if shocked else (100., 80., 100.)
        assert process.input_processed == processed
        assert process.quantity_available == output
        assert process.stock == (500. if shocked else 300.)
        assert process.stock == pytest.approx(
            process.input_processed + process.unused_input,
        )
        sources: list[dict[str, Any]] = [
            {"key": str(i), "quantity_available": source.quantity_available,
             "unit_price": source.unit_price}
            for i, source in enumerate(model.upstream("eu_oil_mills"))
        ]
        standalone = ProcessProviderAgent()
        standalone.setup(process._state())
        result = standalone.step({"upstream": sources, "peer_count": 1,
                                  "effects": {"capacity": .5 if shocked else 1.,
                                              "fuel": 2. if shocked else 1.}})
        assert process.unit_price == result["unit_price"]
        total = sum(source["quantity_available"] for source in sources)
        average = sum(source["unit_price"] * source["quantity_available"]
                      for source in sources) / total
        assert process.unit_price * output / 1.1 == pytest.approx(
            average * processed + cost,
        )


@pytest.mark.parametrize("diagnostic", [None, 50.])
def test_old_and_new_csv_exports_keep_public_bundle_fields(tmp_path, diagnostic):
    env = {name: 1. for name, _ in export_bundle.ENV_COLS}
    pd.DataFrame([{"period": 0, "id_scenario": 1, **env}]).to_csv(
        tmp_path / "Result_Simulator_Environment.csv", index=False,
    )
    diagnostics = {} if diagnostic is None else {
        "input_received": diagnostic, "input_processed": diagnostic,
        "unused_input": diagnostic,
    }
    pd.DataFrame([{
        "period": 0, "id_scenario": 1, "quantity_available": 40.,
        "unit_price": 14.3, **diagnostics,
    }]).to_csv(tmp_path / f"{result_table_name('eu_oil_mills')}.csv", index=False)
    bundle = export_bundle.build_bundle(str(tmp_path), 1, str(SHIPPED))
    assert bundle["ticks"] == [{"period": 0, "nodeId": "eu_oil_mills",
                                "values": {"quantity_available": 40.,
                                           "unit_price": 14.3}}]
    json.dumps(bundle, allow_nan=False)


def test_process_diagnostics_are_registered_for_recording():
    for role in ("processor", "feed_manufacturer"):
        assert _PROPS_BY_ROLE[role] == (
            "quantity_available", "unit_price", "input_received",
            "input_processed", "unused_input", "stock",
        )
    for name in ("input_received", "input_processed", "unused_input"):
        assert db_schema.METRICS_BY_NAME[name].unit == "input units per period"


def test_database_view_upgrade_and_historical_export(
    playback_db, tmp_path, monkeypatch,
):
    # Recreate the prior view shape to exercise PostgreSQL's append-only rule.
    with playback_db.begin() as conn:
        conn.execute(text("DROP VIEW sim_processor_view"))
        conn.execute(text(db_schema._role_view(
            "processor", ("quantity_available", "unit_price"),
            ("a.run_id", "t.id_scenario", "t.period", "a.entity_id", "a.agent_id"),
        )))
    db_schema.initialize_schema(playback_db)
    pdl = configured_pdl(tmp_path, {"eu_oil_mills": {
        "parameters": {"throughput_capacity": 50.},
    }})
    model = model_for(pdl, monkeypatch)
    writer = TickWriter(playback_db)
    record = run_registry.run_record(
        "economics", pdl=str(pdl), scenario_ids=[1], period_num=2,
    )
    writer.open_run(record)
    csv_rows = {}
    env_rows = []
    for tick in (0, 1):
        model._do_step(tick)
        writer.write_tick(model, 1, "economics", tick)
        for entry in model._roster:
            props = _PROPS_BY_ROLE.get(entry.archetype.role, ())
            if not props:
                continue
            agent = getattr(model, entry.archetype.name).agents[0]
            values = {prop: getattr(agent, prop) for prop in props}
            if tick == 0:
                for name in ("input_received", "input_processed", "unused_input"):
                    values.pop(name, None)
            csv_rows.setdefault(entry.archetype.name, []).append({
                "id_scenario": 1, "period": tick, **values,
            })
        env_rows.append({"id_scenario": 1, "period": tick, **{
            name: getattr(model.environment, name)
            for name, _ in export_bundle.ENV_COLS
        }})
    writer.close_run("economics", status="completed")
    with playback_db.begin() as conn:
        # Historical periods have only the original recorded metrics.
        conn.execute(text(
            "DELETE FROM sim_tick WHERE period=0 AND metric_id IN "
            "(SELECT metric_id FROM sim_metric WHERE name IN "
            "('input_received','input_processed','unused_input'))"
        ))
        rows = conn.execute(text(
            "SELECT input_processed, unused_input FROM sim_processor_view "
            "ORDER BY period"
        )).all()
        assert tuple(rows[0]) == (None, None)
        assert rows[1].input_processed == 50.
        bundle = export_bundle.build_bundle(
            export_bundle.PostgresRunReader(conn, "economics"), 1, str(pdl),
        )
        json.dumps(bundle, allow_nan=False)
        assert all("input_processed" not in tick["values"]
                   for tick in bundle["ticks"])
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    for name, values in csv_rows.items():
        pd.DataFrame(values).to_csv(
            csv_dir / f"{result_table_name(name)}.csv", index=False,
        )
    pd.DataFrame(env_rows).to_csv(
        csv_dir / "Result_Simulator_Environment.csv", index=False,
    )
    csv_bundle = export_bundle.build_bundle(str(csv_dir), 1, str(pdl))
    for field in ("ticks", "env", "nodes", "edges"):
        assert csv_bundle[field] == bundle[field]
    json.dumps(csv_bundle, allow_nan=False)
