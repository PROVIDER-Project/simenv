"""Bounded reads from the documented database views; never writes or exports."""
import math
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import text

from ..data_collector import ENVIRONMENT_PROPS
from ..export_bundle import _check_run_inputs
from ..scene import build_scene
from .models import (
    AgentState,
    FramePage,
    RecordedFrame,
    RunList,
    RunSummary,
    Scene,
    SceneSnapshot,
)


class PlaybackNotFound(Exception):
    pass


class PlaybackUnavailable(Exception):
    pass


class PlaybackIntegrityError(Exception):
    pass


class PlaybackStore:
    def __init__(self, engine, scenario_dir: Path | None = None):
        self.engine = engine
        self.scenario_dir = scenario_dir or Path(__file__).parents[1] / "scenarios"

    def _snapshot(self, run) -> SceneSnapshot:
        if run.status != "completed":
            raise PlaybackUnavailable("Only completed runs can be played")
        if run.scene is not None:
            try:
                return SceneSnapshot.model_validate(run.scene)
            except ValidationError as exc:
                raise PlaybackUnavailable("Unsupported or invalid scene snapshot") from exc
        for path in sorted(self.scenario_dir.glob("*.pdl.yaml")):
            try:
                _check_run_inputs(run, path)
            except RuntimeError:
                continue
            return SceneSnapshot.model_validate(build_scene(path))
        raise PlaybackUnavailable("Original scene unavailable; no matching scenario inputs")

    def _run(self, conn, run_id, scenario_id):
        run = conn.execute(text("SELECT * FROM sim_run WHERE run_id=:id"),
                           {"id": run_id}).one_or_none()
        if run is None or scenario_id not in run.scenario_ids:
            raise PlaybackNotFound("Run or scenario not found")
        return run

    def list_runs(self, limit: int, offset: int) -> RunList:
        with self.engine.connect() as conn:
            total = conn.execute(text("SELECT count(*) FROM sim_run")).scalar_one()
            rows = conn.execute(text(
                "SELECT * FROM sim_run ORDER BY started_at DESC, run_id DESC"
                " LIMIT :limit OFFSET :offset"
            ), {"limit": limit, "offset": offset}).all()
        items = []
        for row in rows:
            reason = None
            try:
                self._snapshot(row)
            except PlaybackUnavailable as exc:
                reason = str(exc)
            items.append(RunSummary(
                id=row.run_id, label=row.label, started_at=row.started_at,
                finished_at=row.finished_at, status=row.status,
                scenario_ids=row.scenario_ids, period_num=row.period_num,
                playable=reason is None, unavailable_reason=reason,
            ))
        return RunList(items=items, total=total)

    def get_scene(self, run_id: str, scenario_id: int) -> Scene:
        with self.engine.connect() as conn:
            run = self._run(conn, run_id, scenario_id)
        snapshot = self._snapshot(run)
        return Scene(run_id=run_id, scenario_id=scenario_id, min_period=0,
                     max_period=run.period_num - 1,
                     **snapshot.model_dump(exclude={"schema_version"}))

    def get_frames(self, run_id: str, scenario_id: int,
                   start: int, limit: int) -> FramePage:
        with self.engine.connect() as conn:
            run = self._run(conn, run_id, scenario_id)
            self._snapshot(run)
            end = min(start + limit, run.period_num)
            rows = conn.execute(text(
                "SELECT period, entity_id, agent_id, role, metric, value"
                " FROM sim_tick_readable WHERE run_id=:run"
                " AND id_scenario=:scenario AND period>=:start AND period<:end"
                " ORDER BY period, entity_id, agent_id, metric"
            ), {"run": run_id, "scenario": scenario_id, "start": start, "end": end}).all()
        periods: dict[int, dict[tuple, AgentState]] = {}
        for row in rows:
            if not math.isfinite(row.value):
                raise PlaybackIntegrityError("Non-finite measurement")
            agents = periods.setdefault(row.period, {})
            state = agents.setdefault((row.entity_id, row.agent_id), AgentState(
                entity_id=row.entity_id, agent_id=row.agent_id,
                role=row.role, values={},
            ))
            state.values[row.metric] = row.value
        frames = []
        for period in range(start, end):
            agents = periods.get(period, {})
            env = agents.get(("environment", 0))
            if env is None or not set(ENVIRONMENT_PROPS).issubset(env.values):
                raise PlaybackIntegrityError("Missing environment measurements")
            frames.append(RecordedFrame(period=period, agents=list(agents.values())))
        return FramePage(run_id=run_id, scenario_id=scenario_id, start=start,
                         next_start=end if end < run.period_num else None,
                         frames=frames)

    def check_health(self) -> None:
        with self.engine.connect() as conn:
            conn.execute(text("SELECT scene FROM sim_run LIMIT 0"))
            conn.execute(text("SELECT value FROM sim_tick_readable LIMIT 0"))
