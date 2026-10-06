"""HTTP submission and monitoring of isolated simulation jobs."""

from __future__ import annotations

import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from ..execution import InvalidSimulation, prepare_run
from .queue import SimulationQueue
from .store import JobStore


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    pdl: str = Field(min_length=1, description="PDL document as YAML text")
    roster: str | None = Field(
        default=None, description="Optional roster YAML"
    )
    cascade: str | None = Field(default=None, description="Cascade ID")
    label: str | None = None


class Progress(BaseModel):
    scenario_id: int | None
    step: int = Field(ge=0)
    scenario_total_steps: int = Field(ge=0)
    completed_steps: int = Field(ge=0)
    total_steps: int = Field(ge=0)
    percent_complete: float = Field(ge=0, le=100)


class Job(BaseModel):
    id: str = Field(
        description="Identifier shared by the API job and simulation run"
    )
    status: Literal["queued", "running", "completed", "failed"]
    label: str | None
    cascade: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    progress: Progress


class JobList(BaseModel):
    items: list[Job]
    total: int


class LogChunk(BaseModel):
    text: str
    offset: int
    next_offset: int


Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def create_app(
    data_dir: Path | None = None,
    *,
    queue_factory=SimulationQueue,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        root = data_dir or Path(
            os.environ.get("SIMENV_API_DATA_DIR", "./data/api")
        )
        store = JobStore(root)
        queue = queue_factory(store)
        application.state.store = store
        application.state.queue = queue
        queue.start()
        try:
            yield
        finally:
            # stop() can wait for worker termination; keep it off the event loop.
            from starlette.concurrency import run_in_threadpool

            await run_in_threadpool(queue.stop)

    application = FastAPI(
        title="PROVIDER Simulation API",
        version="0.1.0",
        lifespan=lifespan,
        description=(
            "Submit PDL documents and monitor queued or running simulations. "
            "The service executes one isolated simulation at a time."
        ),
    )

    @application.post("/simulations", status_code=202, response_model=Job)
    def submit_simulation(submission: Submission, response: Response):
        store = application.state.store
        try:
            run = prepare_run(
                store.data_dir / "jobs", **submission.model_dump()
            )
        except InvalidSimulation as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            job = store.add(run)
        except Exception:
            shutil.rmtree(run.directory)
            raise
        response.headers["Location"] = f"/simulations/{run.id}"
        return job

    @application.get("/simulations", response_model=JobList)
    def list_simulations(limit: Limit = 50, offset: Offset = 0):
        return application.state.store.list_jobs(limit=limit, offset=offset)

    @application.get("/simulations/running", response_model=JobList)
    def list_running_simulations(limit: Limit = 50, offset: Offset = 0):
        """List only jobs currently executing, excluding queued/finished jobs."""
        return application.state.store.list_jobs(
            status="running",
            limit=limit,
            offset=offset,
        )

    @application.get("/simulations/{job_id}", response_model=Job)
    def inspect_simulation(job_id: str):
        job = application.state.store.get(job_id)
        if job is None:
            raise HTTPException(
                status_code=404, detail="Simulation not found"
            )
        return job

    @application.get("/simulations/{job_id}/logs", response_model=LogChunk)
    def simulation_logs(
        job_id: str,
        offset: Offset = 0,
        limit: Annotated[int, Query(ge=1, le=65536)] = 16384,
    ):
        """Read a bounded log chunk; offsets are bytes, not character counts."""
        chunk = application.state.store.read_logs(
            job_id, offset=offset, limit=limit
        )
        if chunk is None:
            raise HTTPException(
                status_code=404, detail="Simulation not found"
            )
        return chunk

    @application.get("/health")
    def health():
        if not application.state.queue.healthy:
            raise HTTPException(
                status_code=503, detail="Queue controller is not running"
            )
        return {"status": "ok"}

    return application


app = create_app()
