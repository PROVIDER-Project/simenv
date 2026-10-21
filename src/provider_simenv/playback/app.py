"""Browser-accessible playback API, independently deployed from execution."""
import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from ..db_config import PostgresDBConfig
from .models import FramePage, RunList, Scene
from .store import (
    PlaybackIntegrityError,
    PlaybackNotFound,
    PlaybackStore,
    PlaybackUnavailable,
)

logger = logging.getLogger(__name__)


def create_app(*, store_factory=None, allowed_origins=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        engine = None
        if store_factory:
            store = store_factory()
        else:
            engine = create_engine(PostgresDBConfig().sqlalchemy_url(), pool_pre_ping=True)
            store = PlaybackStore(engine)
        application.state.store = store
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    application = FastAPI(title="PROVIDER Playback API", lifespan=lifespan)
    origins = allowed_origins if allowed_origins is not None else [
        value.strip() for value in os.getenv("SIMENV_PLAYBACK_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    ]
    application.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"])

    @application.exception_handler(PlaybackNotFound)
    async def missing(request: Request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(PlaybackUnavailable)
    async def unavailable(request: Request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @application.exception_handler(PlaybackIntegrityError)
    async def corrupt(request: Request, exc):
        logger.error("Playback integrity error for %s: %s", request.url.path, exc)
        return JSONResponse(status_code=500, content={"detail": "Recorded data is incomplete or invalid"})

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc):
        # Driver exceptions can include credentials and query parameters.
        logger.error("Playback database unavailable for %s (%s)", request.url.path, type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Playback database unavailable"})

    @application.get("/runs", response_model=RunList)
    def runs(limit: Annotated[int, Query(ge=1, le=100)] = 50,
             offset: Annotated[int, Query(ge=0)] = 0):
        return application.state.store.list_runs(limit, offset)

    @application.get("/runs/{run_id}/scenarios/{scenario_id}/scene", response_model=Scene)
    def scene(run_id: str, scenario_id: int):
        return application.state.store.get_scene(run_id, scenario_id)

    @application.get("/runs/{run_id}/scenarios/{scenario_id}/frames", response_model=FramePage)
    def frames(run_id: str, scenario_id: int,
               start: Annotated[int, Query(ge=0)] = 0,
               limit: Annotated[int, Query(ge=1, le=500)] = 100):
        return application.state.store.get_frames(run_id, scenario_id, start, limit)

    @application.get("/health")
    def health():
        application.state.store.check_health()
        return {"status": "ok"}

    return application


app = create_app()
