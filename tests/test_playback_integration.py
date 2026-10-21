import shutil

import pandas as pd
from api_helpers import PDL, ROSTER, wait_for
from fastapi.testclient import TestClient
from sqlalchemy import text

from provider_simenv import execution
from provider_simenv.api.app import create_app as simulation_app
from provider_simenv.playback.app import create_app as playback_app
from provider_simenv.playback.store import PlaybackStore


def test_completed_simulation_plays_from_db_without_input_files(playback_db, tmp_path, monkeypatch):
    template = tmp_path / "template"
    template.mkdir()
    rows = pd.read_csv(execution.INPUT_DIR / "SimulatorScenarios_template.csv")
    rows["period_num"] = 105
    rows.to_csv(template / "SimulatorScenarios_template.csv", index=False)
    monkeypatch.setattr(execution, "INPUT_DIR", template)
    with playback_db.connect() as conn:
        schema = conn.execute(text("SHOW search_path")).scalar_one()
    url = playback_db.url.update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("PROVIDER_SIMENV_POSTGRES_URL", url.render_as_string(hide_password=False))
    with TestClient(simulation_app(tmp_path / "api")) as simulations:
        submitted = simulations.post("/simulations", json={"pdl": PDL, "roster": ROSTER, "label": "Playback integration"})
        assert submitted.status_code == 202
        identity = submitted.json()["id"]

        def terminal():
            job = simulations.get(f"/simulations/{identity}").json()
            return job if job["status"] in ("completed", "failed") else None

        job = wait_for(terminal, timeout=60)
        assert job["status"] == "completed", simulations.get(f"/simulations/{identity}/logs").json()
    shutil.rmtree(tmp_path / "api" / "jobs" / identity / "input")
    with TestClient(playback_app(store_factory=lambda: PlaybackStore(playback_db))) as playback:
        assert playback.get("/runs").json()["items"][0]["id"] == identity
        scene = playback.get(f"/runs/{identity}/scenarios/1/scene")
        assert scene.status_code == 200 and scene.json()["nodes"]
        received = {}
        for scenario in [0, 1]:
            for start in [0, 100]:
                response = playback.get(f"/runs/{identity}/scenarios/{scenario}/frames?start={start}&limit=100")
                assert response.status_code == 200, response.text
                for frame in response.json()["frames"]:
                    for agent in frame["agents"]:
                        for metric, value in agent["values"].items():
                            received[scenario, frame["period"], agent["entity_id"], agent["agent_id"], metric] = value
    with playback_db.connect() as conn:
        rows = conn.execute(text("SELECT id_scenario,period,entity_id,agent_id,metric,value FROM sim_tick_readable WHERE run_id=:id"), {"id": identity})
        stored = {(r.id_scenario, r.period, r.entity_id, r.agent_id, r.metric): r.value for r in rows}
    assert received == stored
    assert len({key[1] for key in received}) == 105
