"""Serial subprocess execution and service lifecycle cleanup."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading

from .store import JobStore

logger = logging.getLogger(__name__)


class SimulationQueue:
    def __init__(self, store: JobStore, *, launcher=subprocess.Popen):
        self.store = store
        self.launcher = launcher
        self._stop = threading.Event()
        self._thread = None

    @property
    def healthy(self) -> bool:
        return (
            not self._stop.is_set()
            and self._thread is not None
            and self._thread.is_alive()
        )

    def start(self) -> None:
        self.store.recover_interrupted()
        self._thread = threading.Thread(
            target=self._run, name="simulation-queue", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=15)
            if self._thread.is_alive():
                raise RuntimeError("Simulation controller did not stop")

    @staticmethod
    def _terminate(process) -> None:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _execute(self, job: dict) -> None:
        directory = self.store.data_dir / "jobs" / job["id"]
        process = None
        try:
            with (directory / "simulation.log").open("ab") as log:
                process = self.launcher(
                    [
                        sys.executable,
                        "-m",
                        "provider_simenv.worker",
                        str(directory / "context.json"),
                    ],
                    cwd=directory,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=dict(os.environ, PYTHONUNBUFFERED="1"),
                )
                while process.poll() is None and not self._stop.wait(0.1):
                    self.store.get(job["id"])
                if self._stop.is_set():
                    self._terminate(process)
                    self.store.finish(
                        job["id"],
                        status="failed",
                        error="Simulation interrupted by service shutdown",
                    )
                else:
                    code = process.wait()
                    self.store.finish(
                        job["id"],
                        status="completed" if code == 0 else "failed",
                        error=None
                        if code == 0
                        else (
                            f"Simulation worker exited with code {code}; "
                            f"see /simulations/{job['id']}/logs"
                        ),
                    )
        except Exception as exc:
            if process is not None:
                self._terminate(process)
            logger.exception("Worker failed for %s", job["id"])
            self.store.finish(job["id"], status="failed", error=str(exc))

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                job = self.store.claim_next()
                if job is None:
                    self._stop.wait(0.1)
                elif self._stop.is_set():
                    self.store.finish(
                        job["id"],
                        status="failed",
                        error="Simulation interrupted by service shutdown",
                    )
                else:
                    self._execute(job)
        except Exception:
            logger.exception(
                "Simulation queue controller stopped unexpectedly"
            )
