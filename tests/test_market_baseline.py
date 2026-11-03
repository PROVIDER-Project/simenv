"""A run without shocks matches the recorded baseline of the shipped PDL."""

import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from provider_simenv.model import DEFAULT_PDL, SupplyChainModel
from provider_simenv.scenario import SupplyChainScenario

FIXTURE = Path(__file__).parent / "fixtures" / "market_baseline_s1_soja.json"
TICKS = 30
METRICS = (
    "quantity_available", "unit_price", "input_received", "input_processed",
    "unused_input", "stock", "storage_utilization", "utilisation",
    "feed_received", "livestock_output", "active",
)


def _record(monkeypatch):
    monkeypatch.setattr(SupplyChainModel, "_event_registry", None, raising=False)
    monkeypatch.setattr(SupplyChainModel, "_pdl_path", str(DEFAULT_PDL), raising=False)
    model = SupplyChainModel(cast(Any, SimpleNamespace()), SupplyChainScenario(1))
    model._setup()
    model.scenario.period_num = TICKS
    ticks = []
    for _ in model.run_stepwise():
        tick = {}
        for entry in model._roster:
            name = entry.archetype.name
            for index, agent in enumerate(getattr(model, name).agents):
                tick[f"{name}/{index}"] = {
                    metric: float(getattr(agent, metric))
                    for metric in METRICS if hasattr(agent, metric)
                }
        ticks.append(tick)
    return ticks


def test_run_without_shocks_matches_recorded_baseline(monkeypatch):
    ticks = _record(monkeypatch)
    if os.environ.get("SIMENV_WRITE_MARKET_BASELINE"):
        FIXTURE.write_text(json.dumps(ticks, indent=1, sort_keys=True), encoding="utf-8")
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(ticks) == len(expected)
    for t, (tick, recorded) in enumerate(zip(ticks, expected)):
        assert tick.keys() == recorded.keys(), f"tick {t}"
        for agent, values in recorded.items():
            for metric, value in values.items():
                assert math.isclose(tick[agent][metric], value, rel_tol=1e-9, abs_tol=1e-9), (
                    f"tick {t} {agent} {metric}: {tick[agent][metric]} != {value}")
