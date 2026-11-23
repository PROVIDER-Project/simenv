"""Product ids from the roster: inherited by transports, carried on source records, recorded per agent."""

from pathlib import Path

import pytest
import yaml
from test_economic_config import SHIPPED, model_for
from test_tick_writer import FakeConnection

from provider_simenv import db_schema
from provider_simenv.model import SupplyChainModel
from provider_simenv.products import resolve_products
from provider_simenv.tick_writer import TickWriter
from provider_simenv.topology import build_roster, sidecar_path

WITHOUT_PRODUCTS = Path(__file__).parent / "fixtures" / "s1-soja-argentina-in-netherlands.pdl.yaml"


def model(pdl, monkeypatch):
    monkeypatch.setattr(SupplyChainModel, "_event_registry", None, raising=False)
    return model_for(pdl, monkeypatch)


def shipped_products():
    return dict(yaml.safe_load(sidecar_path(SHIPPED).read_text(encoding="utf-8"))["products"])


def test_transports_carry_the_product_of_their_sources(monkeypatch):
    m = model(SHIPPED, monkeypatch)
    for name in ("santos_port", "sea_transport_santos_port__rotterdam_port", "rotterdam_port",
                 "paranagua_port", "hamburg_port"):
        assert getattr(m, name).agents[0].product == "soybean"
    mill = m.eu_oil_mills.agents[0]
    assert (mill.product, mill.input_product) == ("soybean_meal", "soybean")


def test_source_records_name_the_product(monkeypatch):
    m = model(SHIPPED, monkeypatch)
    records, _ = m.eu_oil_mills.agents[0]._sources(m.upstream("eu_oil_mills"))
    assert {record["product"] for record in records} == {"soybean"}


@pytest.mark.parametrize("change, message", [
    ({"nowhere": "soybean"}, "unknown roster targets"),
    ({"rotterdam_port": "soybean"}, "transports carry"),
    ({"brazil_farms": None}, "no product for"),
    ({"brazil_wholesaler": {"ships": "soybean", "takes": "soybean"}}, "only processes"),
    ({"eu_feed_trader": ""}, "non-empty"),
])
def test_bad_products_section_is_rejected(change, message):
    products = {**shipped_products(), **change}
    products = {name: value for name, value in products.items() if value is not None}
    with pytest.raises(ValueError, match=message):
        resolve_products(build_roster(SHIPPED), products)


def test_a_transport_with_sources_of_two_products_is_rejected(tmp_path, monkeypatch):
    pdl = tmp_path / SHIPPED.name
    pdl.write_text(SHIPPED.read_text(encoding="utf-8"), encoding="utf-8")
    roster = sidecar_path(SHIPPED).read_text(encoding="utf-8")
    for name in ("us_farms", "us_wholesaler"):
        roster = roster.replace(f"  {name}: soybean\n", f"  {name}: maize\n")
    sidecar_path(pdl).write_text(roster, encoding="utf-8")
    with pytest.raises(ValueError, match="'rotterdam_port'.*one product per link"):
        model(pdl, monkeypatch)


def test_without_a_products_section_nothing_is_named(monkeypatch):
    m = model(WITHOUT_PRODUCTS, monkeypatch)
    agents = [agent for entry in m._roster for agent in getattr(m, entry.archetype.name).agents]
    assert {agent.product for agent in agents} == {""}
    records, _ = m.eu_oil_mills.agents[0]._sources(m.upstream("eu_oil_mills"))
    assert all("product" not in record for record in records)


def test_agents_are_registered_with_their_product(monkeypatch):
    m = model(SHIPPED, monkeypatch)
    writer = TickWriter(None)
    writer._metric_ids = {metric.name: key for key, metric in enumerate(db_schema.METRICS)}
    conn = FakeConnection()
    writer._agent_rows(conn, m, id_scenario=1, run_id="run", t=0)
    products = {row["entity_id"]: row["product"] for row in conn.inserted}
    assert products["eu_oil_mills"] == "soybean_meal"
    assert products["rotterdam_port"] == "soybean"
    assert products["poultry_farms"] is None
