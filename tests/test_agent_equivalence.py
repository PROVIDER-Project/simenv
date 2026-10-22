"""Per-agent numeric traces captured before extraction at commit 288e133."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from provider_simenv import topology
from provider_simenv.model import SupplyChainModel
from provider_simenv.pdl_loader import PDLLoader
from provider_simenv.scenario import SupplyChainScenario

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(__file__).parent / "fixtures" / "agent_reference.json"
CASES = ("baseline", "crisis", "alternate", "sizes", "limited", "starvation")
FIELDS = (
    "role", "active", "quantity_available", "unit_price", "fixed_costs",
    "days_without_input", "bankruptcy_threshold_days", "base_yield",
    "margin", "feed_received", "livestock_output", "size_sigma",
    "size_factor", "markup", "stock", "storage_capacity",
    "storage_utilization", "input_received", "conversion_ratio",
    "capacity", "utilisation", "utilisation_threshold", "transit_steps",
)


def capture_trace(case, monkeypatch):
    pdl = ROOT / "src/provider_simenv/scenarios/s1-soja.pdl.yaml"
    if case == "alternate":
        pdl = Path(__file__).parent / "fixtures/s1-soja-argentina-in-netherlands.pdl.yaml"
    registry = PDLLoader(pdl).to_event_registry("soy_crisis_cascade")
    if case in ("baseline", "sizes", "starvation"):
        registry = None
    monkeypatch.setattr(SupplyChainModel, "_pdl_path", str(pdl), raising=False)
    monkeypatch.setattr(SupplyChainModel, "_event_registry", registry, raising=False)
    if case == "limited":
        monkeypatch.setitem(topology._TRANSPORT_IMPORT["attrs"], "capacity", 100.0)
    scenario = SupplyChainScenario(1)
    scenario.period_num = 46
    if case == "sizes":
        scenario.size_sigma_brazil_farms = 0.4
        scenario.farm_size_sigma_eu = 0.4
    model = SupplyChainModel(cast(Any, SimpleNamespace()), scenario)
    model._setup()
    model._init_event_tracker()
    if case == "starvation":
        for entry in model._roster:
            if entry.archetype.role == "feed_trader":
                for agent in getattr(model, entry.archetype.name):
                    agent.active = False

    def snapshot():
        return {
            entry.archetype.name: [
                {key: getattr(agent, key) for key in FIELDS if hasattr(agent, key)}
                for agent in getattr(model, entry.archetype.name)
            ]
            for entry in model._roster
        }

    trace = {"initial": snapshot()}
    for day in range(46):
        model._do_step(day)
        if day in (0, 1, 19, 20, 21, 44, 45):
            trace[str(day)] = snapshot()
    return trace


@pytest.mark.parametrize("case", CASES)
def test_reference_trace(case, monkeypatch):
    expected = json.loads(REFERENCE.read_text())["cases"][case]
    # Exact comparison catches changes in seeded draws and arithmetic order.
    assert capture_trace(case, monkeypatch) == expected


if __name__ == "__main__":
    # Deliberate one-time reference generation; never run after extraction.
    cases = {}
    for name in CASES:
        with pytest.MonkeyPatch.context() as patch:
            cases[name] = capture_trace(name, patch)
    REFERENCE.write_text(json.dumps({"commit": "288e133", "cases": cases}, indent=2) + "\n")
