"""Regression coverage for Rotterdam routing under the shipped and alternate PDLs."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from provider_simenv import topology
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


def test_day_45_drought_rotterdam_admits_cheapest_first_under_capacity(monkeypatch):
    # One agent per entity leaves the shipped capacity slack, so bind the import
    # lane below the offered volume to reach the rationing path at all.
    monkeypatch.setitem(topology._TRANSPORT_IMPORT["attrs"], "capacity", 100.0)
    model = _run(SHIPPED_PDL, "soy_crisis_cascade", 46, monkeypatch)

    lanes = [
        _sea_transport_from(model, source).agents[0]
        for source in ("santos_port", "argentina_farms", "us_gulf_ports")
    ]
    rotterdam = model.rotterdam_port.agents[0]
    admitted = [lane for lane in lanes if lane.quantity_available > 0.0]
    rejected = [lane for lane in lanes if lane.quantity_available == 0.0]

    assert admitted and rejected, "capacity did not bind; nothing was rationed"

    # Admission is a cheapest-first prefix by unit price, filling the lane exactly.
    assert max(lane.unit_price for lane in admitted) <= min(
        lane.unit_price for lane in rejected
    )
    assert sum(lane.quantity_available for lane in lanes) == pytest.approx(
        rotterdam.capacity
    )
    assert rotterdam.quantity_available == pytest.approx(rotterdam.capacity)


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
