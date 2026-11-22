"""Spare passes through transports, split per buyer and never counted twice."""

import pytest
from test_economic_config import SHIPPED, configured_pdl, model_for

from provider_simenv.model import SupplyChainModel

WHOLESALERS = ("brazil_wholesaler", "argentina_wholesaler", "us_wholesaler")


def capped_mill(tmp_path, monkeypatch):
    pdl = configured_pdl(tmp_path, {"eu_oil_mills": {
        "parameters": {"throughput_capacity": 250.},
    }})
    monkeypatch.setattr(SupplyChainModel, "_event_registry", None, raising=False)
    model = model_for(pdl, monkeypatch)
    model.scenario.period_num = 10
    return model


def test_brazil_spare_is_split_between_its_two_routes_by_orders(tmp_path, monkeypatch):
    model = capped_mill(tmp_path, monkeypatch)
    for _ in model.run_stepwise():
        brazil = model.brazil_wholesaler.agents[0]
        santos = model.spare_for(brazil, model.santos_port.agents[0])
        paranagua = model.spare_for(brazil, model.paranagua_port.agents[0])
        assert santos + paranagua == pytest.approx(brazil._spare)
    assert santos > 0
    assert santos == pytest.approx(0.7 * brazil._spare)


def test_the_mill_never_sees_more_spare_than_the_wholesalers_hold(tmp_path, monkeypatch):
    model = capped_mill(tmp_path, monkeypatch)
    for _ in model.run_stepwise():
        mill = model.eu_oil_mills.agents[0]
        held = sum(getattr(model, name).agents[0]._spare for name in WHOLESALERS)
        seen = sum(model.spare_for(port.agents[0], mill)
                   for port in (model.rotterdam_port, model.hamburg_port))
        assert seen <= held + 1e-9
    assert seen > 0


def test_rotterdam_shifts_a_short_route_to_a_lane_whose_wholesaler_holds_stock(monkeypatch):
    monkeypatch.setattr(SupplyChainModel, "_event_registry", None, raising=False)
    model = model_for(SHIPPED, monkeypatch)
    farm = model.brazil_farms.agents[0]
    harvest = farm.base_yield
    us = model.us_wholesaler.agents[0]
    lane = model.sea_transport_us_gulf_ports__rotterdam_port.agents[0]
    rotterdam = model.rotterdam_port.agents[0]
    mill = model.eu_oil_mills.agents[0]
    received = []
    for t in range(7):
        farm.base_yield = harvest / 2 if t >= 3 else harvest
        model._do_step(t)
        if t == 1:
            us.quantity_available += 200.  # holds 200 more than its buyers ordered
        assert model.overdrawn_suppliers() == []
        received.append(mill.input_received)
    assert rotterdam.last_orders[lane.key] > rotterdam.baseline_orders[lane.key]
    assert received[3:5] == pytest.approx([250., 250.])
    assert min(received[5:]) > 250.
