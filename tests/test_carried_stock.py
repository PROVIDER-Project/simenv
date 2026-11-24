"""A capped mill orders what it can process, and what it leaves stays with the wholesalers."""

import pytest
from test_economic_config import configured_pdl, model_for

from provider_simenv.agents import ROLE_PRODUCER, ROLE_WHOLESALER
from provider_simenv.model import SupplyChainModel


def test_capped_mill_settles_and_the_wholesalers_keep_the_surplus(tmp_path, monkeypatch):
    pdl = configured_pdl(tmp_path, {"eu_oil_mills": {
        "parameters": {"throughput_capacity": 250.},
    }})
    monkeypatch.setattr(SupplyChainModel, "_event_registry", None, raising=False)
    model = model_for(pdl, monkeypatch)
    model.scenario.period_num = 14
    agents = {role: [getattr(model, entry.archetype.name).agents[0]
                     for entry in model._roster if entry.archetype.role == role]
              for role in (ROLE_PRODUCER, ROLE_WHOLESALER)}
    held = []
    for t, _ in enumerate(model.run_stepwise()):
        mill = model.eu_oil_mills.agents[0]
        assert mill.input_processed <= 250. + 1e-9
        assert model.overdrawn_suppliers() == []
        held.append(sum(agent.stock for agent in agents[ROLE_WHOLESALER]))
        if t < 10:
            continue
        assert mill.input_received == pytest.approx(250.)
        assert mill.stock == pytest.approx(250.)
        assert mill.unused_input == pytest.approx(0.)
        assert model.feed_mills.agents[0].input_received == pytest.approx(200.)
        assert held[t] - held[t - 1] == pytest.approx(50.)
        for farm in agents[ROLE_PRODUCER]:
            assert farm.stock == pytest.approx(100.)
