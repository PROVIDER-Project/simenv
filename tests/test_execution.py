import json
from pathlib import Path

import pandas as pd
import pytest

from provider_simenv import execution

SCENARIOS = Path(__file__).parents[1] / "src/provider_simenv/scenarios"


@pytest.fixture
def prepared(tmp_path):
    run = execution.prepare_run(
        tmp_path / "jobs",
        pdl=(SCENARIOS / "s1-soja.pdl.yaml").read_text(),
        roster=(SCENARIOS / "s1-soja.roster.yaml").read_text(),
    )
    template = run.input_dir / "SimulatorScenarios_template.csv"
    rows = pd.read_csv(template)
    rows["period_num"] = 2
    rows.to_csv(template, index=False)
    return run


def test_prepared_id_matches_registry_and_output(prepared):
    loaded = execution.load_prepared_run(prepared.directory / "context.json")
    assert loaded == prepared
    execution.execute_prepared_run(loaded)
    manifest = json.loads((loaded.output_root / "runs.json").read_text())
    assert manifest["runs"][0]["run_id"] == prepared.id
    assert manifest["runs"][0]["status"] == "completed"
    results = loaded.output_root / prepared.id
    assert (results / "Result_Simulator_Environment.csv").exists()


def test_collision_regenerates_without_overwrite(tmp_path, monkeypatch):
    jobs = tmp_path / "jobs"
    existing = jobs / "collision"
    existing.mkdir(parents=True)
    (existing / "sentinel").write_text("keep")
    ids = iter(["collision", "fresh"])
    monkeypatch.setattr(execution, "new_run_id", lambda: next(ids))
    run = execution.prepare_run(
        jobs,
        pdl=(SCENARIOS / "s1-soja.pdl.yaml").read_text(),
        roster=(SCENARIOS / "s1-soja.roster.yaml").read_text(),
    )
    assert run.id == "fresh"
    assert (existing / "sentinel").read_text() == "keep"
    assert (run.output_root / "fresh").is_dir()


def test_private_inputs_do_not_change_bundled_csv(prepared):
    bundled = execution.INPUT_DIR / "SimulatorScenarios.csv"
    original = bundled.read_bytes()
    execution.execute_prepared_run(prepared)
    assert bundled.read_bytes() == original
    private = pd.read_csv(prepared.input_dir / "SimulatorScenarios.csv")
    assert private["id"].tolist() == [0, 1]
    assert private["period_num"].tolist() == [2, 2]


def test_progress_across_scenarios(prepared, monkeypatch):
    snapshots = []
    write = execution.write_progress

    def observe(path, snapshot):
        write(path, snapshot)
        snapshots.append(execution.read_progress(path))

    monkeypatch.setattr(execution, "write_progress", observe)
    execution.execute_prepared_run(prepared)
    assert [s["completed_steps"] for s in snapshots] == [0, 1, 2, 3, 4]
    assert [s["percent_complete"] for s in snapshots] == [0, 25, 50, 75, 100]
    assert snapshots[-1]["scenario_id"] == 1
    assert snapshots[-1]["step"] == 2
    assert snapshots[-1]["total_steps"] == 4


@pytest.mark.parametrize("content", [None, "{", "[]", '{"step": -1}'])
def test_invalid_progress_is_ignored(tmp_path, content):
    path = tmp_path / "progress.json"
    if content is not None:
        path.write_text(content)
    assert execution.read_progress(path) is None


def test_cli_defaults_preserved(tmp_path, monkeypatch):
    template = execution.INPUT_DIR / "SimulatorScenarios_template.csv"
    private = tmp_path / "input"
    private.mkdir()
    (private / template.name).write_bytes(template.read_bytes())
    monkeypatch.setattr(execution, "INPUT_DIR", private)
    monkeypatch.setattr(execution, "OUTPUT_ROOT", tmp_path / "output")

    class NoWorkSimulator:
        def __init__(self, **kwargs):
            pass

        def run(self):
            pass

    monkeypatch.setattr(execution, "Simulator", NoWorkSimulator)
    execution.execute_cli(
        pdl=None, cascade=None, label=None, postgres_url=None
    )
    assert pd.read_csv(private / "SimulatorScenarios.csv")["id"].tolist() == [
        0,
        1,
        2,
    ]
    manifest = json.loads((tmp_path / "output/runs.json").read_text())
    assert manifest["runs"][0]["scenario_ids"] == [0, 1, 2]
    assert manifest["runs"][0]["pdl"] is None
