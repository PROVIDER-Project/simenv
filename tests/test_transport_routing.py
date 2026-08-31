"""Regression coverage for Rotterdam routing under the shipped and alternate PDLs."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from provider_simenv.agents import ROLE_SEA_TRANSPORT
from provider_simenv.model import SupplyChainModel
from provider_simenv.pdl_loader import PDLLoader
from provider_simenv.scenario import SupplyChainScenario


SCENARIOS = Path(__file__).resolve().parents[1] / "src" / "provider_simenv" / "scenarios"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SHIPPED_PDL = SCENARIOS / "s1-soja.pdl.yaml"
ALTERNATE_PDL = FIXTURES / "s1-soja-argentina-in-netherlands.pdl.yaml"


def _run(pdl_path, cascade, period_num, monkeypatch):
    registry = PDLLoader(pdl_path).to_event_registry(cascade)
    monkeypatch.setattr(SupplyChainModel, "_pdl_path", str(pdl_path), raising=False)
    monkeypatch.setattr(SupplyChainModel, "_event_registry", registry, raising=False)

    scenario = SupplyChainScenario(1)
    scenario.period_num = period_num
    model = SupplyChainModel(SimpleNamespace(), scenario)
    model._setup()
    model._init_event_tracker()
    for day in range(period_num):
        model._do_step(day)
    return model


def _sea_transport_from(model, source_entity):
    """The single derived sea-transport list originating at source_entity."""
    prefix = f"sea_transport_{source_entity}__"
    names = [
        entry.archetype.name
        for entry in model._roster
        if entry.archetype.role == ROLE_SEA_TRANSPORT
        and entry.archetype.name.startswith(prefix)
    ]
    assert len(names) == 1, f"expected one sea transport from {source_entity!r}, got {names}"
    return getattr(model, names[0])


def test_day_45_drought_rotterdam_admits_only_us_supply(monkeypatch):
    model = _run(SHIPPED_PDL, "soy_crisis_cascade", 46, monkeypatch)

    santos = _sea_transport_from(model, "santos_port")
    argentina = _sea_transport_from(model, "argentina_farms")
    us = _sea_transport_from(model, "us_gulf_ports")

    admitted_brazil = sum(lane.quantity_available for lane in santos.agents)
    admitted_argentina = sum(lane.quantity_available for lane in argentina.agents)
    admitted_us = sum(lane.quantity_available for lane in us.agents)
    rotterdam_total = sum(port.quantity_available for port in model.rotterdam_port.agents)

    # After 30+ days of drought, Rotterdam buys cheapest-first: only US supply
    # is admitted; the Brazilian and Argentine lanes carry nothing.
    assert admitted_us > 0.0
    assert admitted_brazil == 0.0
    assert admitted_argentina == 0.0
    assert rotterdam_total == admitted_us

    # Lane utilisation reflects that admission.
    assert us.agents[0].utilisation == pytest.approx(0.50)
    assert argentina.agents[0].utilisation == 0.0
    assert santos.agents[0].utilisation == 0.0


def test_alternate_pdl_argentina_routes_without_sea_transport(monkeypatch):
    # Argentina sits in the Netherlands here, so its Rotterdam route is a land
    # link, not a sea crossing: no argentina sea transport is derived and the
    # run must still complete.
    model = _run(ALTERNATE_PDL, "soy_crisis_cascade", 46, monkeypatch)

    sea_names = {
        entry.archetype.name
        for entry in model._roster
        if entry.archetype.role == ROLE_SEA_TRANSPORT
    }
    assert not any(name.startswith("sea_transport_argentina_farms__") for name in sea_names)

    # Argentina still reaches Rotterdam, now as a direct non-sea source.
    assert "argentina_wholesaler" in model._flow_adjacency["rotterdam_port"]
