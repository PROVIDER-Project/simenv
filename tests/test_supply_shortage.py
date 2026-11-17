"""A supplier that runs short ships in proportion to its orders and the gap passes down the chain."""

import pytest
from test_economic_config import SHIPPED, model_for

from provider_simenv.agents import ROLE_CONSUMER
from provider_simenv.model import SupplyChainModel


def test_halved_harvest_is_split_by_orders_and_leaves_no_backlog(monkeypatch):
    monkeypatch.setattr(SupplyChainModel, "_event_registry", None, raising=False)
    model = model_for(SHIPPED, monkeypatch)
    farm = model.brazil_farms.agents[0]
    harvest = farm.base_yield
    santos, paranagua = model.santos_port.agents[0], model.paranagua_port.agents[0]
    rotterdam = model.rotterdam_port.agents[0]
    consumers = [agent for entry in model._roster if entry.archetype.role == ROLE_CONSUMER
                 for agent in getattr(model, entry.archetype.name).agents]
    orders = dict(rotterdam.baseline_orders)
    for t in range(10):
        short = 3 <= t <= 6
        farm.base_yield = harvest / 2 if short else harvest
        model._do_step(t)
        assert santos.quantity_available == pytest.approx(35. if short else 70.)
        assert paranagua.quantity_available == pytest.approx(15. if short else 30.)
        assert model.eu_oil_mills.agents[0].input_received == pytest.approx(250. if short else 300.)
        assert sum(agent.livestock_output for agent in consumers) == pytest.approx(
            200. if short else 240.)
        assert rotterdam.last_orders == pytest.approx(orders)
        assert model.overdrawn_suppliers() == []
