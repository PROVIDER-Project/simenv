"""Guard derived s1-soja topology against accidental drift (step 8b)."""

import sys
from pathlib import Path

from provider_simenv.topology import (
    build_flow_adjacency,
    build_roster,
    execution_order,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(_FIXTURES) not in sys.path:
    sys.path.insert(0, str(_FIXTURES))
from topology_snapshot_23 import EXECUTION_ORDER, FLOW_ADJACENCY, ROSTER

PDL_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "provider_simenv" / "scenarios" / "s1-soja.pdl.yaml"
)


def _freeze_params(params):
    if not params:
        return {}
    out = {}
    for k, v in params.items():
        if isinstance(v, dict):
            inner = {}
            for ik, iv in v.items():
                inner[ik] = tuple(iv) if isinstance(iv, (list, tuple)) else iv
            out[k] = inner
        else:
            out[k] = v
    return out


def _dump_roster(pdl_path):
    return [
        {
            "name": e.archetype.name,
            "agent_class": e.archetype.agent_class.__name__,
            "role": e.archetype.role,
            "count_attr": e.archetype.count_attr,
            "params": _freeze_params(e.archetype.params),
            "entity_ids": tuple(e.entity_ids),
        }
        for e in build_roster(pdl_path)
    ]


def _canonical_execution(adj):
    """Stable step order: dst keys sorted; src tuple order within each dst kept."""
    ordered = {k: tuple(v) for k, v in adj.items()}
    ordered = {k: ordered[k] for k in sorted(ordered)}
    return execution_order(ordered)


def test_s1_soja_topology_matches_snapshot():
    adj = build_flow_adjacency(PDL_PATH)
    assert _dump_roster(PDL_PATH) == ROSTER
    assert {k: tuple(v) for k, v in adj.items()} == FLOW_ADJACENCY
    assert _canonical_execution(adj) == EXECUTION_ORDER
