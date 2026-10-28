"""Lossless playback wire models; raw measurements stay numeric and per-agent."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class SceneSnapshot(Model):
    schema_version: Literal[1]
    pdl: str
    honesty_note: str
    nodes: list[dict]
    edges: list[dict]


class RunSummary(Model):
    id: str
    label: str | None
    started_at: datetime
    finished_at: datetime | None
    status: str
    scenario_ids: list[int]
    period_num: int
    playable: bool
    unavailable_reason: str | None


class RunList(Model):
    items: list[RunSummary]
    total: int


class Scene(Model):
    run_id: str
    scenario_id: int
    min_period: int
    max_period: int
    pdl: str
    honesty_note: str
    nodes: list[dict]
    edges: list[dict]


class AgentState(Model):
    entity_id: str
    agent_id: int
    role: str
    values: dict[str, float]


class RecordedFrame(Model):
    period: int
    agents: list[AgentState]


class FramePage(Model):
    run_id: str
    scenario_id: int
    start: int
    next_start: int | None
    frames: list[RecordedFrame]
