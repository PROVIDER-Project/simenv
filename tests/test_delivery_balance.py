"""What buyers take from a supplier never exceeds what it had."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from provider_simenv.agents import ROLE_CONSUMER
from provider_simenv.model import DEFAULT_PDL, SupplyChainModel
from provider_simenv.scenario import SupplyChainScenario

TICKS = 30
ARGENTINA_IN_NETHERLANDS = (Path(__file__).parent / "fixtures"
                            / "s1-soja-argentina-in-netherlands.pdl.yaml")


def _ticks(monkeypatch, pdl):
    monkeypatch.setattr(SupplyChainModel, "_event_registry", None, raising=False)
    monkeypatch.setattr(SupplyChainModel, "_pdl_path", str(pdl), raising=False)
    model = SupplyChainModel(cast(Any, SimpleNamespace()), SupplyChainScenario(1))
    model._setup()
    model.scenario.period_num = TICKS
    for _ in model.run_stepwise():
        yield model


@pytest.mark.parametrize("pdl", [DEFAULT_PDL, ARGENTINA_IN_NETHERLANDS])
def test_no_supplier_gives_away_more_than_it_had(monkeypatch, pdl):
    for t, model in enumerate(_ticks(monkeypatch, pdl)):
        assert model.overdrawn_suppliers() == [], f"tick {t}"


def test_shipped_chain_passes_on_everything_it_offers(monkeypatch):
    for t, model in enumerate(_ticks(monkeypatch, DEFAULT_PDL)):
        suppliers = {entry.archetype.name for entry in model._roster
                     if entry.archetype.role != ROLE_CONSUMER}
        booked = {source.list_name: (taken, source.quantity_available)
                  for source, taken in model._deliveries.values()}
        assert booked.keys() == suppliers, f"tick {t}"
        for name, (taken, available) in booked.items():
            assert taken == pytest.approx(available), f"tick {t} {name}"
