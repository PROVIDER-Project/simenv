"""
Unit tests for EventTracker — the conditional-event engine (Issue #4).

EventTracker must be stepped once per simulation day starting at 0; an event's
activated_at is fixed on the first step where it is eligible, so these tests
always step sequentially from day 0.
"""
from event_tracker import EventTracker


def ev(eid, *, param=None, value=None, duration=0, condition="", impact_field="supply"):
    return {
        "id": eid, "param": param, "value": value,
        "duration": duration, "condition": condition, "impact_field": impact_field,
    }


def tl(at_day, event_id):
    return {"at_day": at_day, "event_id": event_id}


def step_through(tracker, last_day):
    """Step the tracker day 0..last_day inclusive, as the model does."""
    for d in range(last_day + 1):
        tracker.step(d)


# --- eligibility / unconditional activation ---

def test_unconditional_event_activates_on_its_cascade_day():
    t = EventTracker([ev("a", param="farm_capacity_bra", value=0.6)], [tl(3, "a")])
    step_through(t, 2)
    assert "a" not in t.get_active_event_ids()
    t.step(3)
    assert "a" in t.get_active_event_ids()
    assert t.get_param_value("farm_capacity_bra") == 0.6
    assert t.get_shock_scale("farm_capacity_bra") == 1.0


# --- conditional gating ---

def test_conditional_activates_when_dependency_already_active():
    events = [
        ev("drought", param="farm_capacity_bra", value=0.6),
        ev("export", param="port_capacity_santos", value=0.88, condition="drought.active"),
    ]
    t = EventTracker(events, [tl(0, "drought"), tl(5, "export")])
    step_through(t, 5)
    assert "drought" in t.get_active_event_ids()
    assert "export" in t.get_active_event_ids()  # drought active since day 0
    assert t.get_param_value("port_capacity_santos") == 0.88


def test_same_day_dependency_shifts_conditional_by_one_day():
    """Design decision (2026-06-02): a conditional whose dependency activates on
    the SAME cascade day fires one day later, because `.active` is false on the
    dependency's activation day."""
    events = [
        ev("a", param="farm_capacity_bra", value=0.6),
        ev("b", param="port_capacity_santos", value=0.8, condition="a.active"),
    ]
    t = EventTracker(events, [tl(0, "a"), tl(0, "b")])
    t.step(0)
    assert "a" in t.get_active_event_ids()
    assert "b" not in t.get_active_event_ids()   # NOT same day
    assert t.is_event_active("a") == 0           # 0 days on activation day
    t.step(1)
    assert "b" in t.get_active_event_ids()        # fires the next day
    assert t.is_event_active("a") == 1
    assert t.is_event_active("b") == 0


def test_duration_threshold_condition():
    events = [
        ev("a", param="farm_capacity_bra", value=0.5),
        ev("b", param="port_capacity_santos", value=0.5, condition="a.duration > 2d"),
    ]
    t = EventTracker(events, [tl(0, "a"), tl(0, "b")])
    step_through(t, 2)
    assert "b" not in t.get_active_event_ids()    # is_active(a)=2, 2 > 2 is False
    t.step(3)
    assert "b" in t.get_active_event_ids()         # 3 > 2


def test_and_condition_requires_both():
    events = [
        ev("a"), ev("c"),  # unmapped (param=None) — still usable as conditions
        ev("b", param="farm_capacity_bra", value=0.5,
           condition="a.active AND c.active"),
    ]
    t = EventTracker(events, [tl(0, "a"), tl(5, "c"), tl(0, "b")])
    step_through(t, 5)
    assert {"a", "c"} <= t.get_active_event_ids()
    assert "b" not in t.get_active_event_ids()     # c only just activated at day 5
    t.step(6)
    assert "b" in t.get_active_event_ids()


def test_or_condition_requires_either():
    events = [
        ev("a"),
        ev("b", param="farm_capacity_bra", value=0.5, condition="a.active OR z.active"),
    ]
    t = EventTracker(events, [tl(0, "a"), tl(0, "b")])
    t.step(0)
    assert "b" not in t.get_active_event_ids()     # a just activated, z never defined
    t.step(1)
    assert "b" in t.get_active_event_ids()          # a.active -> OR true


# --- duration / expiry ---

def test_event_expires_after_duration():
    t = EventTracker([ev("a", param="farm_capacity_bra", value=0.5, duration=5)], [tl(0, "a")])
    step_through(t, 4)
    assert "a" in t.get_active_event_ids()
    t.step(5)                                        # day >= activated_at + duration
    assert "a" not in t.get_active_event_ids()
    assert t.get_param_value("farm_capacity_bra") == 1.0


def test_zero_duration_is_permanent():
    t = EventTracker([ev("a", param="farm_capacity_bra", value=0.5, duration=0)], [tl(0, "a")])
    step_through(t, 500)
    assert "a" in t.get_active_event_ids()


def test_expired_event_does_not_reactivate():
    t = EventTracker([ev("a", param="farm_capacity_bra", value=0.5, duration=3)], [tl(0, "a")])
    for d in range(20):
        t.step(d)
        if d >= 3:
            assert "a" not in t.get_active_event_ids()


# --- aggregation ---

def test_capacity_params_aggregate_with_min():
    events = [
        ev("a", param="port_capacity_santos", value=0.8),
        ev("b", param="port_capacity_santos", value=0.6),
    ]
    t = EventTracker(events, [tl(0, "a"), tl(0, "b")])
    t.step(0)
    assert t.get_param_value("port_capacity_santos") == 0.6
    assert t.get_shock_scale("port_capacity_santos") == 1.0


def test_price_params_aggregate_with_max():
    events = [
        ev("a", param="energy_price_factor", value=1.5, impact_field="price"),
        ev("b", param="energy_price_factor", value=3.0, impact_field="price"),
    ]
    t = EventTracker(events, [tl(0, "a"), tl(0, "b")])
    t.step(0)
    assert t.get_param_value("energy_price_factor") == 3.0


# --- defaults / unmapped events ---

def test_unknown_param_defaults_to_baseline():
    t = EventTracker([], [])
    t.step(0)
    assert t.get_param_value("anything") == 1.0
    assert t.get_shock_scale("anything") == 0.0


def test_unmapped_event_tracked_for_conditions_only():
    events = [
        ev("trigger"),  # param=None -> produces no shock value
        ev("dependent", param="farm_capacity_bra", value=0.7, condition="trigger.active"),
    ]
    t = EventTracker(events, [tl(0, "trigger"), tl(0, "dependent")])
    t.step(0)
    assert "trigger" in t.get_active_event_ids()
    assert t.get_param_value("farm_capacity_bra") == 1.0   # trigger has no param
    t.step(1)
    assert "dependent" in t.get_active_event_ids()          # +1-day shift, then active
    assert t.get_param_value("farm_capacity_bra") == 0.7