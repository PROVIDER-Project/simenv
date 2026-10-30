import json
import sqlite3

from api_helpers import claim_job, require_job, submit

from provider_simenv.api.store import JobStore
from provider_simenv.execution import write_progress


def test_persistence_pagination_and_fifo_claims(tmp_path):
    store = JobStore(tmp_path)
    _, first = submit(store, "first")
    _, second = submit(store, "second")
    reloaded = JobStore(tmp_path)
    assert require_job(reloaded, first["id"])["label"] == "first"
    page = reloaded.list_jobs(limit=1)
    assert page["total"] == 2
    assert [job["id"] for job in page["items"]] == [second["id"]]
    assert (
        reloaded.list_jobs(limit=1, offset=1)["items"][0]["id"] == first["id"]
    )
    assert claim_job(reloaded)["id"] == first["id"]
    assert claim_job(reloaded)["id"] == second["id"]
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
    assert require_job(store, queued["id"])["status"] == "queued"
    assert require_job(store, failed["id"])["error"] == "boom"


def test_restart_normalizes_legacy_queued_totals_and_accepts_progress(tmp_path):
    store = JobStore(tmp_path)
    run, queued = submit(store, periods=2)
    _, completed = submit(store, periods=2)
    store.finish(completed["id"], status="completed")
    # Reproduce persisted totals from the baseline-plus-PDL worker.
    with sqlite3.connect(store.database) as db:
        db.execute(
            "UPDATE jobs SET progress=json_set(progress, '$.total_steps', 4)"
        )

    restarted = JobStore(tmp_path)
    assert require_job(restarted, queued["id"])["progress"]["total_steps"] == 2
    assert (
        require_job(restarted, completed["id"])["progress"]["total_steps"]
        == 4
    )
    assert claim_job(restarted)["id"] == queued["id"]
    snapshot = {
        "scenario_id": 1,
        "step": 1,
        "scenario_total_steps": 2,
        "completed_steps": 1,
        "total_steps": 2,
        "percent_complete": 50,
    }
    write_progress(run.progress_path, snapshot)
    assert require_job(restarted, queued["id"])["progress"] == snapshot
    restarted.finish(queued["id"], status="completed")
    final = require_job(restarted, queued["id"])["progress"]
    assert final["completed_steps"] == final["step"] == 2
    assert final["percent_complete"] == 100


def test_progress_does_not_regress_or_disappear(tmp_path):
    store = JobStore(tmp_path)
    run, job = submit(store, periods=2)
    assert job["progress"]["total_steps"] == 2
    store.claim_next()
    snapshot = {
        "scenario_id": 1,
        "step": 1,
        "scenario_total_steps": 2,
        "completed_steps": 1,
        "total_steps": 2,
        "percent_complete": 50,
    }
    write_progress(run.progress_path, snapshot)
    assert require_job(store, job["id"])["progress"]["percent_complete"] == 50
    run.progress_path.write_text("{")
    assert require_job(store, job["id"])["progress"]["percent_complete"] == 50
    older = dict(snapshot, step=0, completed_steps=0, percent_complete=0)
    write_progress(run.progress_path, older)
    store.finish(job["id"], status="failed", error="simulation failed")
    final = require_job(store, job["id"])
    assert final["progress"]["percent_complete"] == 50
    assert final["started_at"] and final["finished_at"]


def test_recovery_fails_running_preserves_progress_and_queue(tmp_path):
    store = JobStore(tmp_path)
    run, active = submit(store, periods=2)
    _, queued = submit(store)
    store.claim_next()
    write_progress(
        run.progress_path,
        {
            "scenario_id": 1,
            "step": 1,
            "scenario_total_steps": 2,
            "completed_steps": 1,
            "total_steps": 2,
            "percent_complete": 50,
        },
    )
    recovered = JobStore(tmp_path)
    recovered.recover_interrupted()
    assert require_job(recovered, active["id"])["status"] == "failed"
    assert (
        require_job(recovered, active["id"])["progress"]["percent_complete"]
        == 50
    )
    assert (
        "interrupt" in require_job(recovered, active["id"])["error"].lower()
    )
    assert claim_job(recovered)["id"] == queued["id"]


def test_logs_use_bounded_byte_offsets_and_missing_jobs(tmp_path):
    store = JobStore(tmp_path)
    run, job = submit(store)
    assert store.read_logs("missing", offset=0, limit=10) is None
    initial = store.read_logs(job["id"], offset=0, limit=10)
    assert initial is not None and initial["text"] == ""
    (run.directory / "simulation.log").write_bytes(b"abcdef")
    chunk = store.read_logs(job["id"], offset=2, limit=2)
    assert chunk == {"text": "cd", "offset": 2, "next_offset": 4}
    end = store.read_logs(job["id"], offset=6, limit=2)
    assert end is not None and end["text"] == ""
    assert store.get("../jobs.sqlite3") is None
    assert (
        json.loads((run.directory / "context.json").read_text())["id"]
        == job["id"]
    )


def test_inconsistent_percentage_cannot_regress_persisted_progress(tmp_path):
    store = JobStore(tmp_path)
    run, job = submit(store)
    store.claim_next()
    snapshot = {
        "scenario_id": 1,
        "step": 100,
        "scenario_total_steps": 365,
        "completed_steps": 100,
        "total_steps": 365,
        "percent_complete": 100 / 365 * 100,
    }
    write_progress(run.progress_path, snapshot)
    before = require_job(store, job["id"])["progress"]
    write_progress(run.progress_path, dict(snapshot, percent_complete=0))
    assert require_job(store, job["id"])["progress"] == before
    store.finish(job["id"], status="failed", error="stopped")
    assert require_job(store, job["id"])["progress"] == before


def test_worker_cannot_change_job_totals(tmp_path):
    store = JobStore(tmp_path)
    run, job = submit(store)
    store.claim_next()
    write_progress(
        run.progress_path,
        {
            "scenario_id": 1,
            "step": 1,
            "scenario_total_steps": 365,
            "completed_steps": 1,
            "total_steps": 365,
            "percent_complete": 1 / 365 * 100,
        },
    )
    before = require_job(store, job["id"])["progress"]
    write_progress(
        run.progress_path,
        {
            "scenario_id": 1,
            "step": 1,
            "scenario_total_steps": 730,
            "completed_steps": 1,
            "total_steps": 730,
            "percent_complete": 1 / 730 * 100,
        },
    )
    assert require_job(store, job["id"])["progress"] == before
