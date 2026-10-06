"""Persistent job lifecycle, queue ordering, progress, and bounded logs."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..execution import PreparedRun, read_progress


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database = self.data_dir / "jobs.sqlite3"
        with self._connection() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    label TEXT,
                    cascade TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error TEXT,
                    progress TEXT NOT NULL
                )
            """)
            db.execute(
                "CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status)"
            )

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, run: PreparedRun) -> dict:
        rows = pd.read_csv(run.input_dir / "SimulatorScenarios_template.csv")
        period_num = int(rows.loc[rows["id"] == 0, "period_num"].iloc[0])
        progress = {
            "scenario_id": None,
            "step": 0,
            "scenario_total_steps": period_num,
            "completed_steps": 0,
            "total_steps": period_num * 2,
            "percent_complete": 0,
        }
        with self._connection() as db:
            db.execute(
                "INSERT INTO jobs (id,status,label,cascade,created_at,progress) "
                "VALUES (?, 'queued', ?, ?, ?, ?)",
                (run.id, run.label, run.cascade, now(), json.dumps(progress)),
            )
        job = self.get(run.id)
        assert job is not None
        return job

    def _refresh(self, job_id: str) -> None:
        snapshot = read_progress(
            self.data_dir / "jobs" / job_id / "progress.json"
        )
        if snapshot is not None:
            with self._connection() as db:
                db.execute(
                    "UPDATE jobs SET progress=? WHERE id=? AND status='running' "
                    "AND json_extract(progress, '$.completed_steps') <= ?",
                    (
                        json.dumps(snapshot),
                        job_id,
                        snapshot["completed_steps"],
                    ),
                )

    def get(self, job_id: str) -> dict | None:
        # Check membership before deriving paths from request input.
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        if row["status"] == "running":
            self._refresh(job_id)
            with self._connection() as db:
                row = db.execute(
                    "SELECT * FROM jobs WHERE id=?", (job_id,)
                ).fetchone()
        result = dict(row)
        result["progress"] = json.loads(result["progress"])
        return result

    def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        where = " WHERE status=?" if status is not None else ""
        params = (status,) if status is not None else ()
        with self._connection() as db:
            count = db.execute(
                "SELECT COUNT(*) FROM jobs" + where, params
            ).fetchone()[0]
            ids = db.execute(
                "SELECT id FROM jobs"
                + where
                + " ORDER BY rowid DESC LIMIT ? OFFSET ?",
                params + (limit, offset),
            ).fetchall()
        items = [
            job for row in ids if (job := self.get(row["id"])) is not None
        ]
        # A worker can finish between selecting IDs and refreshing progress.
        if status is not None:
            items = [job for job in items if job["status"] == status]
        return {"items": items, "total": count}

    def claim_next(self) -> dict | None:
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            job_id = row["id"]
            db.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE id=?",
                (now(), job_id),
            )
        return self.get(job_id)

    def finish(
        self,
        job_id: str,
        *,
        status: str,
        error: str | None = None,
    ) -> None:
        if status not in ("completed", "failed"):
            raise ValueError("Only completed or failed are terminal statuses")
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        progress = job["progress"]
        if status == "completed":
            progress.update(
                scenario_id=1,
                step=progress["scenario_total_steps"],
                completed_steps=progress["total_steps"],
                percent_complete=100,
            )
        with self._connection() as db:
            db.execute(
                "UPDATE jobs SET status=?,finished_at=?,error=?,progress=? WHERE id=?",
                (status, now(), error, json.dumps(progress), job_id),
            )

    def recover_interrupted(self) -> None:
        with self._connection() as db:
            ids = db.execute(
                "SELECT id FROM jobs WHERE status='running'"
            ).fetchall()
        for row in ids:
            self.finish(
                row["id"],
                status="failed",
                error="Simulation interrupted by service restart",
            )

    def read_logs(
        self, job_id: str, *, offset: int, limit: int
    ) -> dict | None:
        if self.get(job_id) is None:
            return None
        path = self.data_dir / "jobs" / job_id / "simulation.log"
        try:
            with path.open("rb") as log:
                log.seek(offset)
                data = log.read(min(limit, 65536))
        except FileNotFoundError:
            data = b""
        return {
            "text": data.decode("utf-8", errors="replace"),
            "offset": offset,
            "next_offset": offset + len(data),
        }
