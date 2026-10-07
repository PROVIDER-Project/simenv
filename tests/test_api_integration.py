import json

import pandas as pd
from api_helpers import PDL, ROSTER, wait_for
from fastapi.testclient import TestClient

from provider_simenv import execution
from provider_simenv.api.app import create_app


def test_real_api_simulation_has_one_id_progress_and_csv(
    tmp_path, monkeypatch
):
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    rows = pd.read_csv(
        execution.INPUT_DIR / "SimulatorScenarios_template.csv"
    )
    rows["period_num"] = 2
    rows.to_csv(template_dir / "SimulatorScenarios_template.csv", index=False)
    monkeypatch.setattr(execution, "INPUT_DIR", template_dir)
    data_dir = tmp_path / "api"
    with TestClient(create_app(data_dir)) as client:
        response = client.post(
            "/simulations", json={"pdl": PDL, "roster": ROSTER}
        )
        assert response.status_code == 202, response.text
        identity = response.json()["id"]

        def terminal():
            job = client.get(f"/simulations/{identity}").json()
            return job if job["status"] in ("completed", "failed") else None

        job = wait_for(terminal, timeout=45)
        logs = client.get(f"/simulations/{identity}/logs").json()["text"]
        assert job["status"] == "completed", logs
        assert job["progress"] == {
            "scenario_id": 1,
            "step": 2,
            "scenario_total_steps": 2,
            "completed_steps": 4,
            "total_steps": 4,
            "percent_complete": 100,
        }
        output = data_dir / "jobs" / identity / "output"
        manifest = json.loads((output / "runs.json").read_text())
        assert manifest["runs"][0]["run_id"] == identity
        assert manifest["runs"][0]["status"] == "completed"
        environment = pd.read_csv(
            output / identity / "Result_Simulator_Environment.csv"
        )
        assert len(environment) == 4
        assert logs
        assert client.get("/simulations/running").json() == {
            "items": [],
            "total": 0,
        }

    with TestClient(create_app(data_dir)) as restarted:
        persisted = restarted.get(f"/simulations/{identity}").json()
        assert persisted["status"] == "completed"
        assert persisted["progress"]["percent_complete"] == 100
