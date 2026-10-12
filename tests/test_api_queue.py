import subprocess
import sys
import threading

import pytest
from api_helpers import require_job, submit, wait_for

from provider_simenv.api.queue import SimulationQueue
from provider_simenv.api.store import JobStore


def test_inactivity_timeout_reaps_worker_and_continues_queue(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SIMENV_API_JOB_TIMEOUT", "0.5")
    store = JobStore(tmp_path)
    _, first = submit(store)
    _, second = submit(store)
    processes = []

    def launcher(args, **kwargs):
        script = "import time; time.sleep(60)" if not processes else "pass"
        process = subprocess.Popen([sys.executable, "-c", script], **kwargs)
        processes.append(process)
        return process

    queue = SimulationQueue(store, launcher=launcher)
    queue.start()
    try:
        wait_for(
            lambda: require_job(store, second["id"])["status"] == "completed",
            timeout=3,
        )
        failed = require_job(store, first["id"])
        assert failed["status"] == "failed"
        assert "timed out" in failed["error"]
        assert "progress" in failed["error"]
        assert processes[0].poll() is not None
        assert queue.healthy
    finally:
        queue.stop()


@pytest.mark.parametrize(
    "mode", ["advancing", "unchanged", "invalid", "regressing"]
)
def test_only_advancing_progress_resets_timeout(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("SIMENV_API_JOB_TIMEOUT", "0.6")
    store = JobStore(tmp_path)
    _, job = submit(store, periods=10)
    # Publish atomically, as the real worker does. With advancement this
    # takes longer than the timeout; identical rewrites must still time out.
    script = (
        "import json,pathlib,time; "
        "path=pathlib.Path('progress.json'); "
        "temporary=path.with_suffix('.tmp'); "
        'exec("for step in range(1, 9):\\n'
        f" mode = {mode!r}\\n"
        " completed = step if mode == 'advancing' else 1\\n"
        " if mode == 'regressing': completed = 2 if step == 1 else 1\\n"
        " snapshot = dict(scenario_id=0, step=completed, "
        "scenario_total_steps=10, completed_steps=completed, "
        "total_steps=20, percent_complete=completed * 5)\\n"
        " if mode == 'invalid' and step > 1: snapshot['percent_complete'] = 99\\n"
        " temporary.write_text(json.dumps(snapshot))\\n"
        " temporary.replace(path)\\n"
        ' time.sleep(0.2)")'
    )
    processes = []

    def launcher(args, **kwargs):
        process = subprocess.Popen([sys.executable, "-c", script], **kwargs)
        processes.append(process)
        return process

    queue = SimulationQueue(store, launcher=launcher)
    queue.start()
    try:
        wait_for(
            lambda: (
                require_job(store, job["id"])["status"]
                in ("completed", "failed")
            ),
            timeout=4,
        )
        finished = require_job(store, job["id"])
        assert finished["status"] == (
            "completed" if mode == "advancing" else "failed"
        )
        if mode != "advancing":
            assert "timed out" in finished["error"]
            assert finished["progress"]["completed_steps"] == (
                2 if mode == "regressing" else 1
            )
        assert processes[0].poll() is not None
    finally:
        queue.stop()


@pytest.mark.parametrize(
    "value", ["0", "-1", "nan", "inf", "-inf", "invalid", ""]
)
def test_invalid_inactivity_timeout_rejected(tmp_path, monkeypatch, value):
    monkeypatch.setenv("SIMENV_API_JOB_TIMEOUT", value)
    with pytest.raises(ValueError, match="SIMENV_API_JOB_TIMEOUT"):
        SimulationQueue(JobStore(tmp_path))


def test_serial_workers_capture_logs_and_exit_status(tmp_path):
    store = JobStore(tmp_path)
    first_run, first = submit(store)
    second_run, second = submit(store)
    release = tmp_path / "release"
    calls = 0

    def launcher(args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            script = (
                "import time,pathlib; print('first',flush=True); "
                f"p=pathlib.Path({str(release)!r}); "
                "exec('while not p.exists(): time.sleep(0.01)')"
            )
        else:
            script = (
                "import sys; print('failure detail',flush=True); sys.exit(7)"
            )
        return subprocess.Popen([sys.executable, "-c", script], **kwargs)

    queue = SimulationQueue(store, launcher=launcher)
    queue.start()
    try:
        wait_for(
            lambda: (
                (first_run.directory / "simulation.log").exists()
                and "first"
                in (first_run.directory / "simulation.log").read_text()
            )
        )
        assert require_job(store, first["id"])["status"] == "running"
        assert require_job(store, second["id"])["status"] == "queued"
        release.touch()
        wait_for(
            lambda: require_job(store, second["id"])["status"] == "failed"
        )
        assert require_job(store, first["id"])["status"] == "completed"
        assert (
            require_job(store, first["id"])["progress"]["percent_complete"]
            == 100
        )
        assert "7" in require_job(store, second["id"])["error"]
        assert (
            "failure detail"
            in (second_run.directory / "simulation.log").read_text()
        )
        assert queue.healthy
    finally:
        queue.stop()


def test_launch_failure_does_not_stall_next_job(tmp_path):
    store = JobStore(tmp_path)
    _, first = submit(store)
    _, second = submit(store)
    calls = 0

    def launcher(args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("worker unavailable")
        return subprocess.Popen([sys.executable, "-c", "pass"], **kwargs)

    queue = SimulationQueue(store, launcher=launcher)
    queue.start()
    try:
        wait_for(
            lambda: require_job(store, second["id"])["status"] == "completed"
        )
        assert require_job(store, first["id"])["status"] == "failed"
        assert (
            "worker unavailable" in require_job(store, first["id"])["error"]
        )
    finally:
        queue.stop()


def test_shutdown_during_launch_reaps_worker_and_keeps_queue(tmp_path):
    store = JobStore(tmp_path)
    _, first = submit(store)
    _, second = submit(store)
    launching = threading.Event()
    release = threading.Event()
    processes = []

    def launcher(args, **kwargs):
        launching.set()
        assert release.wait(5)
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"], **kwargs
        )
        processes.append(process)
        return process

    queue = SimulationQueue(store, launcher=launcher)
    queue.start()
    assert launching.wait(5)
    stopping = threading.Thread(target=queue.stop)
    stopping.start()
    wait_for(lambda: not queue.healthy)
    release.set()
    stopping.join(10)
    assert not stopping.is_alive()
    assert processes[0].poll() is not None
    assert require_job(store, first["id"])["status"] == "failed"
    assert require_job(store, second["id"])["status"] == "queued"


def test_restart_resumes_queued_jobs(tmp_path):
    store = JobStore(tmp_path)
    _, first = submit(store)
    _, second = submit(store)
    store.claim_next()
    queue = SimulationQueue(
        JobStore(tmp_path),
        launcher=lambda args, **kwargs: subprocess.Popen(
            [sys.executable, "-c", "pass"], **kwargs
        ),
    )
    queue.start()
    try:
        wait_for(
            lambda: require_job(store, second["id"])["status"] == "completed"
        )
        assert require_job(store, first["id"])["status"] == "failed"
    finally:
        queue.stop()


def test_shutdown_kills_worker_that_ignores_termination(tmp_path):
    store = JobStore(tmp_path)
    run, job = submit(store)
    processes = []

    def launcher(args, **kwargs):
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                    "print('ready',flush=True); time.sleep(60)"
                ),
            ],
            **kwargs,
        )
        processes.append(process)
        return process

    queue = SimulationQueue(store, launcher=launcher)
    queue.start()
    try:
        wait_for(
            lambda: (
                (run.directory / "simulation.log").exists()
                and "ready" in (run.directory / "simulation.log").read_text()
            )
        )
    finally:
        queue.stop()
    assert processes[0].poll() is not None
    assert require_job(store, job["id"])["status"] == "failed"


def test_unexpected_controller_error_reports_unhealthy(tmp_path, monkeypatch):
    store = JobStore(tmp_path)

    def fail():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(store, "claim_next", fail)
    queue = SimulationQueue(store)
    queue.start()
    wait_for(lambda: not queue.healthy)
    queue.stop()
