"""Guard derived s1-soja topology against accidental drift (step 8b)."""

import logging
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from provider_simenv.model import SupplyChainModel
from provider_simenv.scenario import SupplyChainScenario
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


_SECOND_MILL = (
    "  - id: de_oil_mills\n"
    "    type: manufacturer\n"
    '    name: "DE oil mills"\n'
    "    sector: processing\n"
    "    location: Germany\n"
    "    vulnerability: 0.5\n"
    "\n"
)
_HAMBURG_STAGE = "      - [hamburg_port, eu_oil_mills]\n"


def _shipped_pdl_with_second_mill(tmp_path, hamburg_stages):
    text = PDL_PATH.read_text(encoding="utf-8")
    anchor = "  - id: feed_mills\n"
    assert anchor in text
    assert text.count(_HAMBURG_STAGE) == 1
    text = text.replace(anchor, _SECOND_MILL + anchor, 1)
    text = text.replace(_HAMBURG_STAGE, hamburg_stages, 1)
    pdl = tmp_path / PDL_PATH.name
    pdl.write_text(text, encoding="utf-8")
    shutil.copy(PDL_PATH.with_name("s1-soja.roster.yaml"), tmp_path)
    return pdl


def test_second_mill_on_its_own_source_gets_its_own_list(tmp_path):
    pdl = _shipped_pdl_with_second_mill(
        tmp_path, "      - [hamburg_port, de_oil_mills]\n"
    )
    mills = [e for e in build_roster(pdl) if e.archetype.role == "processor"]
    assert [(e.archetype.name, e.entity_ids) for e in mills] == [
        ("eu_oil_mills", ("eu_oil_mills",)),
        ("de_oil_mills", ("de_oil_mills",)),
    ]
    adj = build_flow_adjacency(pdl)
    assert adj["eu_oil_mills"] == ("rotterdam_port",)
    assert adj["de_oil_mills"] == ("hamburg_port",)


def test_mills_sharing_a_source_are_rejected(tmp_path):
    pdl = _shipped_pdl_with_second_mill(
        tmp_path, _HAMBURG_STAGE + "      - [hamburg_port, de_oil_mills]\n"
    )
    with pytest.raises(ValueError, match="hamburg_port"):
        build_flow_adjacency(pdl)


def test_pdl_without_sidecar_builds_with_a_warning(tmp_path, caplog):
    pdl = tmp_path / "local.pdl.yaml"
    pdl.write_text(
        "entities:\n  - id: local_farm\n    type: region\n    sector: agriculture\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="provider_simenv.topology"):
        roster = build_roster(pdl)
    assert [e.archetype.name for e in roster] == ["local_farm"]
    assert "no roster sidecar" in caplog.text


def test_entity_id_colliding_with_a_model_attribute_is_rejected(tmp_path, monkeypatch):
    pdl = tmp_path / "collide.pdl.yaml"
    pdl.write_text(
        "entities:\n  - id: environment\n    type: region\n    sector: agriculture\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(SupplyChainModel, "_pdl_path", str(pdl), raising=False)
    model = SupplyChainModel(SimpleNamespace(), SupplyChainScenario(1))
    with pytest.raises(ValueError, match="'environment'"):
        model._setup()


def test_entity_id_with_reserved_underscore_prefix_is_rejected(tmp_path):
    pdl = tmp_path / "reserved.pdl.yaml"
    pdl.write_text(
        "entities:\n  - id: _flow_adjacency\n    type: region\n    sector: agriculture\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="'_flow_adjacency' starts with '_'"):
        build_roster(pdl)
