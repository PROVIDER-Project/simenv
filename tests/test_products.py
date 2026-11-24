"""Product ids from the roster: inherited by transports, carried on source records, recorded per agent."""

from pathlib import Path

import pytest
import yaml
from test_economic_config import SHIPPED, model_for
from test_tick_writer import FakeConnection

from provider_simenv import db_schema
from provider_simenv.export_bundle import _shipped_products
from provider_simenv.model import SupplyChainModel
from provider_simenv.products import resolve_products
from provider_simenv.scene import build_scene
from provider_simenv.tick_writer import TickWriter
from provider_simenv.topology import (
    build_flow_adjacency,
    build_roster,
    load_roster_sidecar,
    sidecar_path,
)

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


@pytest.mark.parametrize("products", [
    False, True, 0, 1, None, "", "soybean", [], ["soybean"], {},
])
def test_loader_rejects_malformed_products_sections(tmp_path, products):
    pdl = tmp_path / SHIPPED.name
    pdl.write_text(SHIPPED.read_text(encoding="utf-8"), encoding="utf-8")
    sidecar_path(pdl).write_text(
        yaml.safe_dump({"products": products}), encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid products section"):
        load_roster_sidecar(pdl)


@pytest.mark.parametrize("roster, expected", [
    ({}, {}),
    ({"products": {"brazil_farms": "soybean"}},
     {"brazil_farms": "soybean"}),
])
def test_loader_accepts_optional_products(tmp_path, roster, expected):
    pdl = tmp_path / SHIPPED.name
    pdl.write_text(SHIPPED.read_text(encoding="utf-8"), encoding="utf-8")
    sidecar_path(pdl).write_text(
        yaml.safe_dump(roster), encoding="utf-8",
    )
    assert load_roster_sidecar(pdl).products == expected


def test_a_transport_with_sources_of_two_products_is_rejected(tmp_path, monkeypatch):
    pdl = tmp_path / SHIPPED.name
    pdl.write_text(SHIPPED.read_text(encoding="utf-8"), encoding="utf-8")
    roster = sidecar_path(SHIPPED).read_text(encoding="utf-8")
    for name in ("us_farms", "us_wholesaler"):
        roster = roster.replace(f"  {name}: soybean\n", f"  {name}: corn\n")
    sidecar_path(pdl).write_text(roster, encoding="utf-8")
    with pytest.raises(ValueError, match="'rotterdam_port'.*one product per link"):
        model(pdl, monkeypatch)


def pdl_with_products(tmp_path, changes):
    pdl = tmp_path / SHIPPED.name
    pdl.write_text(SHIPPED.read_text(encoding="utf-8"), encoding="utf-8")
    roster = sidecar_path(SHIPPED).read_text(encoding="utf-8")
    for old, new in changes.items():
        assert roster.count(old) == 1
        roster = roster.replace(old, new)
    sidecar_path(pdl).write_text(roster, encoding="utf-8")
    return pdl


@pytest.mark.parametrize(("changes", "message"), [
    ({"  brazil_farms: soybean\n": "  brazil_farms: corn\n"},
     "'brazil_wholesaler' takes 'soybean', but 'brazil_farms' ships 'corn'"),
    ({"  eu_feed_trader: compound_feed\n": "  eu_feed_trader: soybean_meal\n"},
     ("'eu_feed_trader' takes 'soybean_meal', but 'feed_mills' ships "
      "'compound_feed'")),
])
def test_a_trader_whose_supplier_ships_another_product_is_rejected(
    tmp_path, monkeypatch, changes, message,
):
    with pytest.raises(ValueError, match=message):
        model(pdl_with_products(tmp_path, changes), monkeypatch)


def test_a_process_whose_supplier_ships_another_product_is_rejected(
    tmp_path, monkeypatch,
):
    pdl = pdl_with_products(tmp_path, {
        "takes: soybean}": "takes: corn}",
    })
    with pytest.raises(
        ValueError, match=r"'eu_oil_mills' takes 'corn', but '\w+_port' ships 'soybean'",
    ):
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


def test_order_products_survive_the_next_tick(monkeypatch):
    m = model(SHIPPED, monkeypatch)
    supplier = m.brazil_farms.agents[0]
    buyer = m.brazil_wholesaler.agents[0]
    expected = [{
        "key": buyer.key,
        "quantity": buyer.baseline_orders[supplier.key],
        "product": "soybean",
    }]
    assert supplier._step_input()["orders"] == expected
    m._do_step(0)
    assert supplier._step_input()["orders"] == expected
    m._do_step(1)


@pytest.mark.parametrize("product", ["corn", ""])
def test_supplier_rejects_a_mismatched_routed_order(monkeypatch, product):
    m = model(SHIPPED, monkeypatch)
    supplier = m.brazil_farms.agents[0]
    buyer = m.brazil_wholesaler.agents[0]
    original_step = buyer._implementation.step

    def changed_order(data):
        result = original_step(data)
        for order in result["orders"]:
            order["product"] = product
        return result

    monkeypatch.setattr(buyer._implementation, "step", changed_order)
    m._do_step(0)
    assert supplier._step_input()["orders"] == [{
        "key": buyer.key,
        "quantity": buyer.baseline_orders[supplier.key],
        "product": product,
    }]
    with pytest.raises(ValueError, match="Order for"):
        m._do_step(1)


def test_an_order_without_a_product_is_rejected_before_it_is_booked(
    monkeypatch,
):
    m = model(SHIPPED, monkeypatch)
    supplier = m.brazil_farms.agents[0]
    buyer = m.brazil_wholesaler.agents[0]
    original_step = buyer._implementation.step

    def unlabelled_order(data):
        result = original_step(data)
        for order in result["orders"]:
            del order["product"]
        return result

    monkeypatch.setattr(buyer._implementation, "step", unlabelled_order)
    with pytest.raises(ValueError, match="names no product, expected 'soybean'"):
        m._do_step(0)
    assert id(supplier) not in m._next_orders


def test_routed_orders_without_products_remain_untagged(monkeypatch):
    m = model(WITHOUT_PRODUCTS, monkeypatch)
    m._do_step(0)
    orders = [
        order
        for name in m._execution_order
        for agent in getattr(m, name).agents
        for order in agent._step_input()["orders"]
    ]
    assert orders
    assert all("product" not in order for order in orders)
    m._do_step(1)


def test_delivery_products_are_stored_and_forwarded(monkeypatch):
    m = model(SHIPPED, monkeypatch)
    supplier = m.brazil_farms.agents[0]
    buyer = m.brazil_wholesaler.agents[0]
    m._do_step(0)
    assert m.delivered(supplier, buyer) > 0
    assert m.delivered_product(supplier, buyer) == "soybean"
    monkeypatch.setattr(supplier, "product", "corn")
    records, _ = buyer._sources([supplier])
    assert records[0]["product"] == "soybean"


@pytest.mark.parametrize("product", ["corn", "", None])
def test_invalid_delivery_labels_are_rejected_before_booking(
    monkeypatch, product,
):
    m = model(SHIPPED, monkeypatch)
    supplier = m.brazil_farms.agents[0]
    buyer = m.brazil_wholesaler.agents[0]
    original_step = supplier._implementation.step
    before = supplier.quantity_available

    def changed_delivery(data):
        result = original_step(data)
        result["quantity_available"] = 12345.0
        result["deliveries"] = [
            {"key": buyer.key, "quantity": 1.0, "product": "soybean"},
            {"key": buyer.key, "quantity": 1.0},
        ]
        if product is not None:
            result["deliveries"][1]["product"] = product
        return result

    monkeypatch.setattr(
        supplier._implementation, "step", changed_delivery,
    )
    with pytest.raises(ValueError, match="invalid delivery product"):
        m._do_step(0)
    assert m.delivered(supplier, buyer) == 0
    assert m.delivered_product(supplier, buyer) is None
    assert supplier.quantity_available == before


def test_untagged_deliveries_remain_supported(monkeypatch):
    m = model(WITHOUT_PRODUCTS, monkeypatch)
    m._do_step(0)
    buyer = m.eu_oil_mills.agents[0]
    records, sources = buyer._sources(m.upstream("eu_oil_mills"))
    assert records
    assert any(record["delivered"] > 0 for record in records)
    assert all("product" not in record for record in records)
    for source in sources.values():
        assert m.delivered_product(source, buyer) == ""


def test_scene_names_what_each_component_ships():
    scene = build_scene(SHIPPED)
    nodes = {node["id"]: node for node in scene["nodes"]}
    assert (nodes["brazil_farms"]["product"], nodes["brazil_farms"]["inputProduct"]) == ("soybean", None)
    assert (nodes["eu_oil_mills"]["product"], nodes["eu_oil_mills"]["inputProduct"]) == (
        "soybean_meal", "soybean")
    assert nodes["rotterdam_port"]["product"] == "soybean"
    assert nodes["pig_farms"]["product"] is None
    edges = {edge["id"]: edge["product"] for edge in scene["edges"]}
    assert edges["santos_port->rotterdam_port"] == "soybean"
    assert edges["eu_oil_mills->feed_mills"] == "soybean_meal"


def test_scene_without_a_products_section_names_nothing():
    scene = build_scene(WITHOUT_PRODUCTS)
    assert {node["product"] for node in scene["nodes"]} == {None}
    assert {node["inputProduct"] for node in scene["nodes"]} == {None}
    assert {edge["product"] for edge in scene["edges"]} == {None}


def test_exported_products_match_the_model(monkeypatch):
    m = model(SHIPPED, monkeypatch)
    exported = _shipped_products(build_roster(SHIPPED), build_flow_adjacency(SHIPPED))
    for entry in m._roster:
        agents = getattr(m, entry.archetype.name).agents
        if agents:
            assert exported[entry.archetype.name] == (agents[0].product or None), entry.archetype.name
