"""A shortage at a Brazilian port reaches Europe after the sea transit time."""

import pytest
from test_economic_config import SHIPPED, model_for

from provider_simenv.model import SupplyChainModel

LANE = "sea_transport_santos_port__rotterdam_port"


def test_halved_harvest_reaches_rotterdam_after_the_transit_time(monkeypatch):
    monkeypatch.setattr(SupplyChainModel, "_event_registry", None, raising=False)
    model = model_for(SHIPPED, monkeypatch)
    farm = model.brazil_farms.agents[0]
    harvest = farm.base_yield
    santos = model.santos_port.agents[0]
    lane = getattr(model, LANE).agents[0]
    mill = model.eu_oil_mills.agents[0]
    transit = lane.transit_steps
    assert transit > 0
    shock = range(3, 7)
    arrival = range(3 + transit, 7 + transit)
    for t in range(arrival.stop + 2):
        farm.base_yield = harvest / 2 if t in shock else harvest
        before = lane.quantity_in_transit
        model._do_step(t)
        if t == 0:
            price = lane.unit_price
        assert santos.quantity_available == pytest.approx(35. if t in shock else 70.)
        assert lane.quantity_available == pytest.approx(35. if t in arrival else 70.)
        assert mill.input_received == pytest.approx(250. if t in arrival else 300.)
        if t > 0:
            assert before + model.delivered(santos, lane) == pytest.approx(
                lane.quantity_in_transit + lane.quantity_available)
        if t in arrival:
            assert lane.unit_price > price
        else:
            assert lane.unit_price == pytest.approx(price)
        assert model.overdrawn_suppliers() == []
