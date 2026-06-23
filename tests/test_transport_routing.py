"""
_move_split routes by an origin ALLOW-LIST, not per-origin exclude flags.
Proves the Brazilian land legs (Santos/Paranagua) carry exactly the BRA share,
identical to the pre-refactor `total - arg_vol - usa_vol` subtraction,
and that the allow-list generalises to any origin combination with no routing
code change.
"""
from types import SimpleNamespace

import pytest

from provider_simenv.agents.transport import Transport


class FakeList(list):
    """Minimal stand-in for a Melodie AgentList (truthiness, len, iter, filter)."""
    def filter(self, fn):
        return FakeList(x for x in self if fn(x))


def _wholesaler(bra, arg, usa, price, active=True):
    return SimpleNamespace(
        active=active,
        quantity_available=bra + arg + usa,
        bra_volume=bra, arg_volume=arg, usa_volume=usa,
        unit_price=price,
    )


def _port(n_peers=1, capacity=10_000.0):
    """Build a stub `self` for the unbound Transport._move_split call."""
    env = SimpleNamespace(get_effective_value=lambda *key: 1.0)
    port = SimpleNamespace(
        active=True,
        capacity=capacity,
        fixed_costs=100.0,
        scenario=SimpleNamespace(margin_transport=0.1),
        model=SimpleNamespace(environment=env),
    )
    port._peer_list = lambda: FakeList([port] * n_peers)
    return port


# two wholesalers; BRA=300, ARG=40, USA=60, total=400
WHOLESALERS = FakeList([
    _wholesaler(bra=100, arg=30, usa=20, price=10.0),
    _wholesaler(bra=200, arg=10, usa=40, price=12.0),
])
TOTAL = 400.0
BRA, ARG, USA = 300.0, 40.0, 60.0
SHARE = 0.7


def test_bra_allowlist_matches_old_exclude_formula():
    """origins={'bra'} == pre-refactor (total - arg_vol - usa_vol)."""
    port = _port()
    Transport._move_split(
        port, WHOLESALERS, share=SHARE,
        shock_key=("santos_port", "supply"), origins={"bra"},
    )
    old_routable = TOTAL - ARG - USA          # the pre-change subtraction
    expected = old_routable * SHARE / 1       # n_self = 1
    assert old_routable == BRA                # algebraic identity
    assert port.quantity_available == pytest.approx(expected)


def test_origins_none_carries_full_volume():
    port = _port()
    Transport._move_split(port, WHOLESALERS, share=SHARE, origins=None)
    assert port.quantity_available == pytest.approx(TOTAL * SHARE)


def test_allowlist_generalises_to_arbitrary_origins():
    """A combination the old exclude-flags could express only as 'all but bra'."""
    port = _port()
    Transport._move_split(port, WHOLESALERS, share=SHARE, origins={"arg", "usa"})
    assert port.quantity_available == pytest.approx((ARG + USA) * SHARE)


def test_capacity_caps_routed_volume():
    """Routed volume is still capped at the port's effective capacity."""
    port = _port(capacity=50.0)
    Transport._move_split(port, WHOLESALERS, share=1.0, origins={"bra"})
    assert port.quantity_available == pytest.approx(50.0)
