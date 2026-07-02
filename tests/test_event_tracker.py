"""
Unit tests for EventTracker — the conditional-event engine (Issue #4).

EventTracker must be stepped once per simulation day starting at 0; an event's
activated_at is fixed on the first step where it is eligible, so these tests
always step sequentially from day 0.

Shocks are keyed by the PDL (entity, impact_field) pair; events with no
supply/price impact (impacts={}) are still tracked for use as conditions.
"""
from provider_simenv.event_tracker import EventTracker


def ev(eid, *, entity=None, impacts=None, duration=0, condition=""):
    return {
        "id": eid, "entity": entity, "impacts": impacts or {},
        "duration": duration, "condition": condition,
    }


def tl(at_day, event_id):
    return {"at_day": at_day, "event_id": event_id}


def step_through(tracker, last_day):
    """Step the tracker day 0..last_day inclusive, as the model does."""
    for d in range(last_day + 1):
        tracker.step(d)


# --- eligibility / unconditional activation ---

def test_unconditional_event_activates_on_its_cascade_day():
    t = EventTracker([ev("a", entity="brazil_farms", impacts={"supply": 0.6})], [tl(3, "a")])
    step_through(t, 2)
    assert "a" not in t.get_active_event_ids()
    t.step(3)
    assert "a" in t.get_active_event_ids()
    assert t.get_param_value("brazil_farms", "supply") == 0.6
    assert t.get_shock_scale("brazil_farms", "supply") == 1.0


# --- conditional gating ---

def test_conditional_activates_when_dependency_already_active():
    events = [
        ev("drought", entity="brazil_farms", impacts={"supply": 0.6}),
        ev("export", entity="santos_port", impacts={"supply": 0.88}, condition="drought.active"),
    ]
    t = EventTracker(events, [tl(0, "drought"), tl(5, "export")])
    step_through(t, 5)
    assert "drought" in t.get_active_event_ids()
    assert "export" in t.get_active_event_ids()  # drought active since day 0
    assert t.get_param_value("santos_port", "supply") == 0.88


def test_same_day_dependency_shifts_conditional_by_one_day():
    """Design decision (2026-06-02): a conditional whose dependency activates on
    the SAME cascade day fires one day later, because `.active` is false on the
    dependency's activation day."""
    events = [
        ev("a", entity="brazil_farms", impacts={"supply": 0.6}),
        ev("b", entity="santos_port", impacts={"supply": 0.8}, condition="a.active"),
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
        ev("a", entity="brazil_farms", impacts={"supply": 0.5}),
        ev("b", entity="santos_port", impacts={"supply": 0.5}, condition="a.duration > 2d"),
    ]
    t = EventTracker(events, [tl(0, "a"), tl(0, "b")])
    step_through(t, 2)
    assert "b" not in t.get_active_event_ids()    # is_active(a)=2, 2 > 2 is False
    t.step(3)
    assert "b" in t.get_active_event_ids()         # 3 > 2


def test_and_condition_requires_both():
    events = [
        ev("a"), ev("c"),  # no impact (entity=None) — still usable as conditions
        ev("b", entity="brazil_farms", impacts={"supply": 0.5},
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
        ev("b", entity="brazil_farms", impacts={"supply": 0.5}, condition="a.active OR z.active"),
    ]
    t = EventTracker(events, [tl(0, "a"), tl(0, "b")])
    t.step(0)
    assert "b" not in t.get_active_event_ids()     # a just activated, z never defined
    t.step(1)
    assert "b" in t.get_active_event_ids()          # a.active -> OR true


# --- duration / expiry ---

def test_event_expires_after_duration():
    t = EventTracker([ev("a", entity="brazil_farms", impacts={"supply": 0.5}, duration=5)], [tl(0, "a")])
    step_through(t, 4)
    assert "a" in t.get_active_event_ids()
    t.step(5)                                        # day >= activated_at + duration
    assert "a" not in t.get_active_event_ids()
    assert t.get_param_value("brazil_farms", "supply") == 1.0


def test_zero_duration_is_permanent():
    t = EventTracker([ev("a", entity="brazil_farms", impacts={"supply": 0.5}, duration=0)], [tl(0, "a")])
    step_through(t, 500)
    assert "a" in t.get_active_event_ids()


def test_expired_event_does_not_reactivate():
    t = EventTracker([ev("a", entity="brazil_farms", impacts={"supply": 0.5}, duration=3)], [tl(0, "a")])
    for d in range(20):
        t.step(d)
        if d >= 3:
            assert "a" not in t.get_active_event_ids()


# --- aggregation ---

def test_supply_aggregates_with_min():
    events = [
        ev("a", entity="santos_port", impacts={"supply": 0.8}),
        ev("b", entity="santos_port", impacts={"supply": 0.6}),
    ]
    t = EventTracker(events, [tl(0, "a"), tl(0, "b")])
    t.step(0)
    assert t.get_param_value("santos_port", "supply") == 0.6
    assert t.get_shock_scale("santos_port", "supply") == 1.0


def test_price_aggregates_with_max():
    events = [
        ev("a", entity="gas_supply", impacts={"price": 1.5}),
        ev("b", entity="gas_supply", impacts={"price": 3.0}),
    ]
    t = EventTracker(events, [tl(0, "a"), tl(0, "b")])
    t.step(0)
    assert t.get_param_value("gas_supply", "price") == 3.0


# --- defaults / impact-less events ---

def test_unknown_key_defaults_to_baseline():
    t = EventTracker([], [])
    t.step(0)
    assert t.get_param_value("anything", "supply") == 1.0
    assert t.get_shock_scale("anything", "supply") == 0.0


def test_impactless_event_tracked_for_conditions_only():
    events = [
        ev("trigger"),  # impacts={} -> produces no shock value
        ev("dependent", entity="brazil_farms", impacts={"supply": 0.7}, condition="trigger.active"),
    ]
    t = EventTracker(events, [tl(0, "trigger"), tl(0, "dependent")])
    t.step(0)
    assert "trigger" in t.get_active_event_ids()
    assert t.get_param_value("brazil_farms", "supply") == 1.0   # trigger has no impact
    t.step(1)
    assert "dependent" in t.get_active_event_ids()          # +1-day shift, then active
    assert t.get_param_value("brazil_farms", "supply") == 0.7