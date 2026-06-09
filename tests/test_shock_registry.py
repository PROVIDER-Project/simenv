"""
acceptance: the shock-parameter registry is derived from the PDL, not hardcoded.

Proves:
  1. shock_registry is the single source for binding / aggregation / drought param.
  2. A NEW shock param can be driven purely from a PDL file — zero Python edits — as long
     as its (entity, impact) is already bound. Uses rotterdam_port, which is in BINDING but
     absent from the shipped s1-soja.pdl.yaml.
  3. Aggregation is a function of the impact field (supply -> min, price -> max).
  4. The duplicated capacity/price sets and the _PARAM_TIMING_FIELDS table are gone.
"""
import textwrap
from pathlib import Path

import shock_registry as reg
from pdl_loader import PDLLoader
from event_tracker import EventTracker


# --- 1. registry is the single source ---

def test_param_names_match_binding():
    assert reg.param_names() == set(reg.BINDING.values())


def test_drought_param_is_derived_not_hardcoded():
    assert reg.drought_param() == reg.BINDING[("brazil_farms", "supply")]
    assert reg.drought_param() == "farm_capacity_bra"


# --- 2. a new shock param, driven entirely from PDL (zero Python edits) ---

PDL_NEW_PARAM = textwrap.dedent("""
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
    path = tmp_path / "new_param.pdl.yaml"
    path.write_text(pdl_text, encoding="utf-8")
    registry = PDLLoader(path).to_event_registry()
    return EventTracker(events=registry["events"], timeline=registry["timeline"])


def test_new_pdl_param_shocks_with_zero_code(tmp_path):
    t = _tracker_from_pdl(PDL_NEW_PARAM, tmp_path)

    # before onset (day 5): unshocked
    for d in range(5):
        t.step(d)
    assert t.get_shock_scale("port_capacity_rotterdam") == 0.0
    assert t.get_param_value("port_capacity_rotterdam") == 1.0

    # at onset: -25% supply -> 0.75, aggregated with min (supply rule)
    t.step(5)
    assert t.get_shock_scale("port_capacity_rotterdam") == 1.0
    assert t.get_param_value("port_capacity_rotterdam") == 0.75

    # after duration (onset 5 + 30): expired, back to unshocked
    t.step(35)
    assert t.get_shock_scale("port_capacity_rotterdam") == 0.0
    assert t.get_param_value("port_capacity_rotterdam") == 1.0


# --- 3. aggregation derived from impact field ---

def _ev(eid, *, param, value, impact_field):
    return {"id": eid, "param": param, "value": value,
            "duration": 0, "condition": "", "impact_field": impact_field}


def test_supply_aggregates_with_min():
    t = EventTracker(
        [_ev("a", param="port_capacity_santos", value=0.8, impact_field="supply"),
         _ev("b", param="port_capacity_santos", value=0.5, impact_field="supply")],
        [{"at_day": 0, "event_id": "a"}, {"at_day": 0, "event_id": "b"}],
    )
    t.step(0)
    assert t.get_param_value("port_capacity_santos") == 0.5   # worst-case supply


def test_price_aggregates_with_max():
    t = EventTracker(
        [_ev("a", param="energy_price_factor", value=1.2, impact_field="price"),
         _ev("b", param="energy_price_factor", value=1.5, impact_field="price")],
        [{"at_day": 0, "event_id": "a"}, {"at_day": 0, "event_id": "b"}],
    )
    t.step(0)
    assert t.get_param_value("energy_price_factor") == 1.5   # worst-case price


# --- 4. the old hardcoded tables are gone ---

def test_duplicated_sets_removed():
    import pdl_loader
    import event_tracker
    assert not hasattr(pdl_loader, "_CAPACITY_PARAMS")
    assert not hasattr(pdl_loader, "_PRICE_PARAMS")
    assert not hasattr(pdl_loader, "_PDL_MAPPING")
    assert not hasattr(event_tracker, "_CAPACITY_PARAMS")
    assert not hasattr(event_tracker, "_PRICE_PARAMS")


def test_param_timing_fields_removed():
    import environment
    assert not hasattr(environment, "_PARAM_TIMING_FIELDS")