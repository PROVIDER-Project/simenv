import json

from api_helpers import submit

from provider_simenv.api.store import JobStore
from provider_simenv.execution import write_progress


def test_persistence_pagination_and_fifo_claims(tmp_path):
    store = JobStore(tmp_path)
    _, first = submit(store, "first")
    _, second = submit(store, "second")
    reloaded = JobStore(tmp_path)
    assert reloaded.get(first["id"])["label"] == "first"
    page = reloaded.list_jobs(limit=1)
    assert page["total"] == 2
    assert [job["id"] for job in page["items"]] == [second["id"]]
    assert (
        reloaded.list_jobs(limit=1, offset=1)["items"][0]["id"] == first["id"]
    )
    assert reloaded.claim_next()["id"] == first["id"]
    assert reloaded.claim_next()["id"] == second["id"]
    assert reloaded.claim_next() is None


def test_running_only_excludes_other_states(tmp_path):
    store = JobStore(tmp_path)
    _, active = submit(store)
    _, queued = submit(store)
    _, completed = submit(store)
    _, failed = submit(store)
    store.claim_next()
    store.finish(completed["id"], status="completed")
    store.finish(failed["id"], status="failed", error="boom")
    page = store.list_jobs(status="running")
    assert page["total"] == 1
    assert [job["id"] for job in page["items"]] == [active["id"]]
    assert store.get(queued["id"])["status"] == "queued"
    assert store.get(failed["id"])["error"] == "boom"


def test_progress_does_not_regress_or_disappear(tmp_path):
    store = JobStore(tmp_path)
    run, job = submit(store)
    store.claim_next()
    snapshot = {
        "scenario_id": 0,
        "step": 1,
        "scenario_total_steps": 2,
        "completed_steps": 1,
        "total_steps": 4,
        "percent_complete": 25,
    }
    write_progress(run.progress_path, snapshot)
    assert store.get(job["id"])["progress"]["percent_complete"] == 25
    run.progress_path.write_text("{")
    assert store.get(job["id"])["progress"]["percent_complete"] == 25
    older = dict(snapshot, step=0, completed_steps=0, percent_complete=0)
    write_progress(run.progress_path, older)
    store.finish(job["id"], status="failed", error="simulation failed")
    final = store.get(job["id"])
    assert final["progress"]["percent_complete"] == 25
    assert final["started_at"] and final["finished_at"]


def test_recovery_fails_running_preserves_progress_and_queue(tmp_path):
    store = JobStore(tmp_path)
    run, active = submit(store)
    _, queued = submit(store)
    store.claim_next()
    write_progress(
        run.progress_path,
        {
            "scenario_id": 1,
            "step": 1,
            "scenario_total_steps": 2,
            "completed_steps": 3,
            "total_steps": 4,
            "percent_complete": 75,
        },
    )
    recovered = JobStore(tmp_path)
    recovered.recover_interrupted()
    assert recovered.get(active["id"])["status"] == "failed"
    assert recovered.get(active["id"])["progress"]["percent_complete"] == 75
    assert "interrupt" in recovered.get(active["id"])["error"].lower()
    assert recovered.claim_next()["id"] == queued["id"]


def test_logs_use_bounded_byte_offsets_and_missing_jobs(tmp_path):
    store = JobStore(tmp_path)
    run, job = submit(store)
    assert store.read_logs("missing", offset=0, limit=10) is None
    assert store.read_logs(job["id"], offset=0, limit=10)["text"] == ""
    (run.directory / "simulation.log").write_bytes(b"abcdef")
    chunk = store.read_logs(job["id"], offset=2, limit=2)
    assert chunk == {"text": "cd", "offset": 2, "next_offset": 4}
    assert store.read_logs(job["id"], offset=6, limit=2)["text"] == ""
    assert store.get("../jobs.sqlite3") is None
    assert (
        json.loads((run.directory / "context.json").read_text())["id"]
        == job["id"]
    )
