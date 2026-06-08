"""
Validates PDLLoader.to_event_registry() against the real s1-soja.pdl.yaml.
"""
from pathlib import Path

from pdl_loader import PDLLoader

PDL_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "provider_simenv" / "scenarios" / "s1-soja.pdl.yaml"
)


def test_event_registry_counts():
    reg = PDLLoader(PDL_PATH).to_event_registry()  # default cascade = soy_crisis_cascade
    events = reg["events"]
    assert len(events) == 18
    assert sum(1 for e in events if e["param"] is not None) == 8     # mapped
    assert sum(1 for e in events if e["condition"]) == 15            # conditional
    assert len(reg["timeline"]) == 13


def test_argentina_supply_increase_is_mapped():
    reg = PDLLoader(PDL_PATH).to_event_registry()
    arg = next(e for e in reg["events"] if e["id"] == "argentina_supply_increase")
    assert arg["param"] == "farm_capacity_arg"   # NOT unmapped (HTML brief is wrong)
    assert arg["value"] == 1.1                    # +10% -> 1.10