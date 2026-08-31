"""Regression coverage for Rotterdam routing under the shipped drought cascade."""

from pathlib import Path
from types import SimpleNamespace

from provider_simenv.model import SupplyChainModel
from provider_simenv.pdl_loader import PDLLoader
from provider_simenv.scenario import SupplyChainScenario


PDL_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "provider_simenv"
    / "scenarios"
    / "s1-soja.pdl.yaml"
)


def test_day_45_drought_rotterdam_admits_only_us_supply(monkeypatch):
    registry = PDLLoader(PDL_PATH).to_event_registry("soy_crisis_cascade")
    monkeypatch.setattr(SupplyChainModel, "_pdl_path", str(PDL_PATH), raising=False)
    monkeypatch.setattr(SupplyChainModel, "_event_registry", registry, raising=False)

    scenario = SupplyChainScenario(1)
    scenario.period_num = 46
    model = SupplyChainModel(SimpleNamespace(), scenario)
    model._setup()
    model._init_event_tracker()

    for day in range(scenario.period_num):
        model._do_step(day)

    admitted_brazil = sum(
        lane.quantity_available for lane in model.sea_lane_santos.agents
    )
    admitted_argentina = sum(
        lane.quantity_available for lane in model.sea_lane_arg.agents
    )
    admitted_us = sum(
        lane.quantity_available for lane in model.sea_lane_usa.agents
    )
    rotterdam_total = sum(
        port.quantity_available for port in model.transport_eu_rtm.agents
    )

    assert admitted_us > 0.0
    assert admitted_brazil == 0.0
    assert admitted_argentina == 0.0
    assert rotterdam_total == admitted_us
