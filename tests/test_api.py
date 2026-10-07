import pytest
import yaml
from api_helpers import PDL, ROSTER
from fastapi.testclient import TestClient

from provider_simenv import execution
from provider_simenv.api.app import create_app
from provider_simenv.execution import write_progress


@pytest.mark.parametrize(
    "error_type", [KeyError, TypeError, AttributeError, IndexError]
)
def test_loader_bugs_are_not_reported_as_invalid_input(
    client, monkeypatch, error_type
):
    def fail(path):
        raise error_type("internal topology bug")

    monkeypatch.setattr(execution, "build_roster", fail)
    with pytest.raises(error_type, match="internal topology bug"):
        client.post("/simulations", json={"pdl": PDL, "roster": ROSTER})


class ManualQueue:
    def __init__(self, store):
        self.healthy = True

    def start(self):
        pass

    def stop(self):
        self.healthy = False


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, queue_factory=ManualQueue)
    with TestClient(app) as client:
        yield client


def submit(client, **kwargs):
    response = client.post(
        "/simulations", json=dict(pdl=PDL, roster=ROSTER, **kwargs)
    )
    assert response.status_code == 202, response.text
    return response


def test_submission_returns_reserved_id_and_location(client, tmp_path):
    response = submit(client, label="test", cascade="soy_crisis_cascade")
    job = response.json()
    assert job["status"] == "queued"
    assert job["progress"]["percent_complete"] == 0
    assert job["label"] == "test"
    assert response.headers["location"] == f"/simulations/{job['id']}"
    assert (
        tmp_path / "jobs" / job["id"] / "input/scenario.pdl.yaml"
    ).read_text() == PDL
    assert (tmp_path / "jobs" / job["id"] / "output" / job["id"]).is_dir()
    assert client.get(response.headers["location"]).json()["id"] == job["id"]


def test_running_list_has_only_running_jobs_and_live_progress(
    client, tmp_path
):
    active = submit(client).json()
    queued = submit(client).json()
    done = submit(client).json()
    failed = submit(client).json()
    store = client.app.state.store
    store.claim_next()
    store.finish(done["id"], status="completed")
    store.finish(failed["id"], status="failed", error="boom")
    write_progress(
        tmp_path / "jobs" / active["id"] / "progress.json",
        {
            "scenario_id": 0,
            "step": 1,
            "scenario_total_steps": 365,
            "completed_steps": 1,
            "total_steps": 730,
            "percent_complete": 1 / 730 * 100,
        },
    )
    response = client.get("/simulations/running")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [job["id"] for job in response.json()["items"]] == [active["id"]]
    assert (
        response.json()["items"][0]["progress"]["percent_complete"]
        == 1 / 730 * 100
    )
    assert (
        client.get(f"/simulations/{queued['id']}").json()["status"]
        == "queued"
    )
    page = client.get("/simulations?limit=1&offset=1").json()
    assert page["total"] == 4
    assert page["items"][0]["id"] == done["id"]


def test_logs_missing_jobs_docs_and_health(client, tmp_path):
    job = submit(client).json()
    assert client.get(f"/simulations/{job['id']}/logs").json()["text"] == ""
    (tmp_path / "jobs" / job["id"] / "simulation.log").write_text("abcdef")
    chunk = client.get(f"/simulations/{job['id']}/logs?offset=1&limit=3")
    assert chunk.json() == {"text": "bcd", "offset": 1, "next_offset": 4}
    assert client.get("/simulations/missing").status_code == 404
    assert client.get("/simulations/missing/logs").status_code == 404
    assert client.get("/docs").status_code == 200
    assert (
        "/simulations/running" in client.get("/openapi.json").json()["paths"]
    )
    assert client.get("/health").status_code == 200
    client.app.state.queue.healthy = False
    assert client.get("/health").status_code == 503


@pytest.mark.parametrize(
    "pdl",
    [
        "",
        "   ",
        "[one, two]",
        "scalar",
        "{",
        "entities: wrong",
        "entities: [wrong]",
        "entities: [{id: foo}]\nevents: [{trigger: wrong}]",
    ],
)
def test_invalid_documents_are_rejected_without_queueing(client, pdl):
    response = client.post("/simulations", json={"pdl": pdl})
    assert response.status_code == 422, response.text
    assert client.get("/simulations").json()["total"] == 0


@pytest.mark.parametrize(
    "section, value",
    [
        ("cascades", []),
        ("cascades", ["bad"]),
        ("events", [{"impact": "bad"}]),
        ("supply_chains", [{"stages": ["bad"]}]),
    ],
)
def test_invalid_nested_shapes_are_rejected(client, section, value):
    doc = yaml.safe_load(PDL)
    doc[section] = value
    response = client.post(
        "/simulations", json={"pdl": yaml.safe_dump(doc), "roster": ROSTER}
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "roster",
    [
        "scalar",
        "entities: [bad]",
        "archetypes: [bad]",
        "entities: [{id: brazil_farms, reason: collision}]",
        "archetypes: {brazil_farms: nonexistent}",
    ],
)
def test_invalid_roster_is_rejected(client, roster):
    response = client.post(
        "/simulations", json={"pdl": PDL, "roster": roster}
    )
    assert response.status_code == 422, response.text
    assert client.get("/simulations").json()["total"] == 0


def test_unknown_cascade_and_client_ids_are_rejected(client):
    for extra in (
        {"cascade": "missing"},
        {"id": "caller-id"},
        {"run_id": "caller-id"},
    ):
        response = client.post(
            "/simulations", json=dict(pdl=PDL, roster=ROSTER, **extra)
        )
        assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/simulations?limit=0",
        "/simulations?limit=101",
        "/simulations?offset=-1",
        "/simulations/running?limit=101",
        "/simulations/running?offset=-1",
        "/simulations/missing/logs?limit=65537",
        "/simulations/missing/logs?offset=-1",
    ],
)
def test_invalid_query_bounds(client, path):
    assert client.get(path).status_code == 422


def test_pdl_without_sidecar_uses_only_its_own_declarations(client):
    doc = {
        "entities": [
            {"id": "local_farm", "type": "region", "sector": "agriculture"}
        ],
        "cascades": [{"id": "empty", "timeline": []}],
    }
    response = client.post("/simulations", json={"pdl": yaml.safe_dump(doc)})
    assert response.status_code == 202, response.text


def test_storage_failure_is_not_reported_as_invalid_pdl(
    tmp_path, monkeypatch
):
    app = create_app(tmp_path, queue_factory=ManualQueue)
    with TestClient(app, raise_server_exceptions=False) as client:

        def fail(run):
            raise OSError("disk unavailable")

        monkeypatch.setattr(app.state.store, "add", fail)
        response = client.post(
            "/simulations", json={"pdl": PDL, "roster": ROSTER}
        )
        assert response.status_code == 500
        assert list((tmp_path / "jobs").iterdir()) == []


@pytest.mark.parametrize(
    "field, value",
    [
        ("id", ["bad"]),
        ("condition", ["bad"]),
        ("target", ["bad"]),
    ],
)
def test_malformed_event_fields_never_enter_queue(
    client, tmp_path, field, value
):
    doc = yaml.safe_load(PDL)
    if field == "id":
        doc["events"][0][field] = value
    else:
        doc["events"][0]["trigger"][field] = value
    response = client.post(
        "/simulations",
        json={
            "pdl": yaml.safe_dump(doc),
            "roster": ROSTER,
        },
    )
    assert response.status_code == 422, response.text
    assert client.get("/simulations").json()["total"] == 0
    assert not (tmp_path / "jobs").exists()


@pytest.mark.parametrize(
    "section, value",
    [
        ("edges", ["brazil_farms"]),
        ("edges", [["brazil_farms"]]),
        ("edges", [["brazil_farms", "santos_port", "paranagua_port"]]),
        ("dependencies", ["bad"]),
        ("exclude", ["bad"]),
    ],
)
def test_malformed_roster_shapes_never_enter_queue(client, section, value):
    doc = yaml.safe_load(ROSTER)
    doc[section] = value
    response = client.post(
        "/simulations",
        json={
            "pdl": PDL,
            "roster": yaml.safe_dump(doc),
        },
    )
    assert response.status_code == 422, response.text
    assert client.get("/simulations").json()["total"] == 0


@pytest.mark.parametrize(
    "mutation", ["missing_scenario", "oversized_percent"]
)
def test_corrupt_progress_cannot_break_monitoring(client, tmp_path, mutation):
    job = submit(client).json()
    client.app.state.store.claim_next()
    snapshot = {
        "scenario_id": 0,
        "step": 1,
        "scenario_total_steps": 365,
        "completed_steps": 1,
        "total_steps": 730,
        "percent_complete": 1 / 730 * 100,
    }
    if mutation == "missing_scenario":
        del snapshot["scenario_id"]
    else:
        snapshot["percent_complete"] = 10**400
    write_progress(tmp_path / "jobs" / job["id"] / "progress.json", snapshot)
    response = client.get(f"/simulations/{job['id']}")
    assert response.status_code == 200
    assert response.json()["progress"]["completed_steps"] == 0
    assert client.get("/simulations/running").status_code == 200
