"""
Validates PDLLoader.to_event_registry() against the real s1-soja.pdl.yaml.

Events carry the PDL `target` entity and an `impacts` dict keyed by impact
field — no translation to model param names. `demand` impacts are
parsed-but-skipped (nothing consumes them yet).
"""
from pathlib import Path

from provider_simenv.pdl_loader import PDLLoader

PDL_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "provider_simenv" / "scenarios" / "s1-soja.pdl.yaml"
)


def test_event_registry_counts():
    reg = PDLLoader(PDL_PATH).to_event_registry()  # default cascade = soy_crisis_cascade
    events = reg["events"]
    assert len(events) == 18
    assert sum(1 for e in events if e["impacts"]) == 16     # carry a supply/price impact
    assert sum(1 for e in events if e["condition"]) == 15   # conditional
    assert len(reg["timeline"]) == 13


def test_argentina_supply_increase_carries_both_impacts():
    reg = PDLLoader(PDL_PATH).to_event_registry()
    arg = next(e for e in reg["events"] if e["id"] == "argentina_supply_increase")
    assert arg["entity"] == "argentina_farms"
    # supply +10% AND price +15% — both carried, no collision
    assert arg["impacts"] == {"supply": 1.1, "price": 1.15}


def test_demand_only_event_has_empty_impacts():
    reg = PDLLoader(PDL_PATH).to_event_registry()
    sub = next(e for e in reg["events"] if e["id"] == "consumer_substitution")
    assert sub["entity"] == "food_retail"
    assert sub["impacts"] == {}   # demand -8% is parsed-but-skipped


def test_demand_and_price_event_keeps_only_price():
    reg = PDLLoader(PDL_PATH).to_event_registry()
    fert = next(e for e in reg["events"] if e["id"] == "fertilizer_demand_spike")
    assert fert["entity"] == "fertilizer_supply"
    assert fert["impacts"] == {"price": 1.8}   # demand +40% skipped, price +80% kept