"""
acceptance: shocks are keyed by the PDL (entity, impact_field) pair, passed
through verbatim — there is no translation layer.

Proves:
  1. shock_registry exposes only the aggregation rule + the drought anchor
     (no BINDING / param_names / drought_param translation table).
  2. A NEW shock can be driven purely from a PDL file — zero Python edits —
     because the (entity, field) key comes straight from the PDL. Uses
     rotterdam_port, absent from the shipped s1-soja.pdl.yaml.
  3. Aggregation is a function of the impact field (supply -> min, price -> max).
  4. One entity carrying BOTH supply and price impacts resolves each
     independently — no collision (the case an entity-only key would fail).
"""
import textwrap
from pathlib import Path

from provider_simenv import shock_registry as reg
from provider_simenv.pdl_loader import PDLLoader
from provider_simenv.event_tracker import EventTracker


# --- 1. registry is only rule + anchor, no translation table ---

def test_no_translation_table():
    assert not hasattr(reg, "BINDING")
    assert not hasattr(reg, "param_for")
    assert not hasattr(reg, "param_names")
    assert not hasattr(reg, "drought_param")


def test_registry_names_no_entity():
    """
    The registry holds the rule and the field, never a PDL entity id.
    """
    assert not hasattr(reg, "DROUGHT_KEY")
    assert reg.DROUGHT_IMPACT_FIELD == "supply"


def test_aggregate_rule_by_field():
    assert reg.aggregate("supply", [0.8, 0.5]) == 0.5   # worst-case supply
    assert reg.aggregate("price", [1.2, 1.5]) == 1.5    # worst-case price


# --- 2. a new shock, driven entirely from PDL (zero Python edits) ---

PDL_NEW_SHOCK = textwrap.dedent("""
    scenario:
      name: rotterdam_strike_test
    events:
      - id: rotterdam_strike
        trigger:
          target: rotterdam_port
        impact:
          supply: "-25%"
          duration: 30d
    cascades:
      - id: test_cascade
        timeline:
          - {at: 5d, event: rotterdam_strike}
""")


def _tracker_from_pdl(pdl_text: str, tmp_path: Path) -> EventTracker:
    path = tmp_path / "new_shock.pdl.yaml"
    path.write_text(pdl_text, encoding="utf-8")
    registry = PDLLoader(path).to_event_registry()
    return EventTracker(events=registry["events"], timeline=registry["timeline"])


def test_new_pdl_shock_with_zero_code(tmp_path):
    t = _tracker_from_pdl(PDL_NEW_SHOCK, tmp_path)
    key = ("rotterdam_port", "supply")

    # before onset (day 5): unshocked
    for d in range(5):
        t.step(d)
    assert t.get_shock_scale(*key) == 0.0
    assert t.get_param_value(*key) == 1.0

    # at onset: -25% supply -> 0.75
    t.step(5)
    assert t.get_shock_scale(*key) == 1.0
    assert t.get_param_value(*key) == 0.75

    # after duration (5 + 30): expired, back to unshocked
    t.step(35)
    assert t.get_shock_scale(*key) == 0.0
    assert t.get_param_value(*key) == 1.0


# --- 3. aggregation derived from impact field ---

def _ev(eid, *, entity, impacts):
    return {"id": eid, "entity": entity, "impacts": impacts,
            "duration": 0, "condition": ""}


def test_supply_aggregates_with_min():
    t = EventTracker(
        [_ev("a", entity="santos_port", impacts={"supply": 0.8}),
         _ev("b", entity="santos_port", impacts={"supply": 0.5})],
        [{"at_day": 0, "event_id": "a"}, {"at_day": 0, "event_id": "b"}],
    )
    t.step(0)
    assert t.get_param_value("santos_port", "supply") == 0.5   # worst-case supply


def test_price_aggregates_with_max():
    t = EventTracker(
        [_ev("a", entity="gas_supply", impacts={"price": 1.2}),
         _ev("b", entity="gas_supply", impacts={"price": 1.5})],
        [{"at_day": 0, "event_id": "a"}, {"at_day": 0, "event_id": "b"}],
    )
    t.step(0)
    assert t.get_param_value("gas_supply", "price") == 1.5     # worst-case price


# --- 4. one entity, both impacts, no collision (the B1-failure case) ---

def test_one_event_both_impacts_resolves_independently():
    # mirrors argentina_supply_increase: supply +10% AND price +15% on one entity.
    t = EventTracker(
        [_ev("arg_increase", entity="argentina_farms",
             impacts={"supply": 1.10, "price": 1.15})],
        [{"at_day": 0, "event_id": "arg_increase"}],
    )
    t.step(0)
    assert t.get_param_value("argentina_farms", "supply") == 1.10
    assert t.get_param_value("argentina_farms", "price") == 1.15
