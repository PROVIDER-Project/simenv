"""Volume nobody takes carries over as stock while buyers take by share."""

import pytest
from test_economic_config import configured_pdl, model_for

from provider_simenv.model import SupplyChainModel


def test_capped_mill_keeps_the_excess_and_its_stock_grows(tmp_path, monkeypatch):
    pdl = configured_pdl(tmp_path, {"eu_oil_mills": {
        "parameters": {"throughput_capacity": 250.},
    }})
    monkeypatch.setattr(SupplyChainModel, "_event_registry", None, raising=False)
    model = model_for(pdl, monkeypatch)
    model.scenario.period_num = 5
    for t, _ in enumerate(model.run_stepwise()):
        mill = model.eu_oil_mills.agents[0]
        assert mill.input_received == pytest.approx(300.)
        assert mill.input_processed == pytest.approx(250.)
        assert mill.stock == pytest.approx(300. + 50. * t)
        assert mill.unused_input == pytest.approx(50. * (t + 1))
        assert model.feed_mills.agents[0].input_received == pytest.approx(200.)
        assert model.overdrawn_suppliers() == []
