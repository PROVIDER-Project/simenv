"""The exporter refuses a run whose PDL or roster sidecar changed since it ran."""

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from provider_simenv import export_bundle, run_registry
from provider_simenv.topology import build_flow_adjacency

SCENARIOS = Path(__file__).resolve().parents[1] / "src" / "provider_simenv" / "scenarios"
PDL_NAME = "s1-soja.pdl.yaml"
ROSTER_NAME = "s1-soja.roster.yaml"
DAIRY_EDGE = b"  - [eu_feed_trader, dairy_farms]"


@pytest.fixture(autouse=True)
def stable_git_sha(monkeypatch):
    monkeypatch.setattr(run_registry, "git_sha", lambda: "abc123")


@pytest.fixture
def pdl(tmp_path):
    shutil.copy(SCENARIOS / PDL_NAME, tmp_path)
    shutil.copy(SCENARIOS / ROSTER_NAME, tmp_path)
    return tmp_path / PDL_NAME


def recorded_run(pdl: Path) -> SimpleNamespace:
    return SimpleNamespace(**run_registry.run_record(
        "20261020T090000Z-aaaaaaaa",
        pdl=str(pdl),
        scenario_ids=[0, 1],
        period_num=365,
    ))


def test_unchanged_inputs_pass(pdl):
    export_bundle._check_run_inputs(recorded_run(pdl), pdl)


def test_edited_roster_with_unchanged_pdl_is_rejected(pdl):
    run = recorded_run(pdl)
    roster = pdl.with_name(ROSTER_NAME)
    adjacency = build_flow_adjacency(pdl)
    text = roster.read_bytes()
    assert DAIRY_EDGE in text
    roster.write_bytes(text.replace(DAIRY_EDGE, b"", 1))

    assert recorded_run(pdl).pdl_sha256 == run.pdl_sha256
    assert build_flow_adjacency(pdl) != adjacency
    with pytest.raises(RuntimeError, match="different s1-soja.roster.yaml"):
        export_bundle._check_run_inputs(run, pdl)


def test_removed_roster_is_rejected(pdl):
    run = recorded_run(pdl)
    pdl.with_name(ROSTER_NAME).unlink()

    with pytest.raises(RuntimeError, match="is missing"):
        export_bundle._check_run_inputs(run, pdl)


def test_roster_added_after_a_run_without_one_is_rejected(pdl):
    roster = pdl.with_name(ROSTER_NAME)
    content = roster.read_bytes()
    roster.unlink()
    run = recorded_run(pdl)
    roster.write_bytes(content)

    with pytest.raises(RuntimeError, match="without a roster sidecar"):
        export_bundle._check_run_inputs(run, pdl)


def test_changed_pdl_is_rejected(pdl):
    run = recorded_run(pdl)
    pdl.write_bytes(pdl.read_bytes() + b"\n")

    with pytest.raises(RuntimeError, match="is not the PDL"):
        export_bundle._check_run_inputs(run, pdl)
