"""Simulation-owned run preparation and execution for CLI and API workers."""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml
from Melodie import Config, Simulator

from .model import SupplyChainModel
from .pdl_loader import PDLLoader
from .run_registry import finish_run, new_run_id, start_run
from .scenario import SupplyChainScenario
from .topology import build_flow_adjacency, build_roster, execution_order

PACKAGE_DIR = Path(__file__).resolve().parent
INPUT_DIR = PACKAGE_DIR / "data/input"
OUTPUT_ROOT = PACKAGE_DIR / "data/output"


class InvalidSimulation(ValueError):
    """A submitted document cannot be interpreted by the simulation."""


@dataclass(frozen=True)
class PreparedRun:
    id: str
    directory: Path
    pdl_path: Path
    input_dir: Path
    output_root: Path
    progress_path: Path
    cascade: str | None
    label: str | None


def _mapping(value, name):
    if not isinstance(value, dict):
        raise InvalidSimulation(f"{name} must be a mapping")
    return value


def _documents(text: str, name: str) -> dict:
    try:
        doc = _mapping(yaml.safe_load(text), name)
        if name == "PDL":
            _mapping(doc.get("scenario", {}), "scenario")
            for section in (
                "entities",
                "events",
                "cascades",
                "supply_chains",
            ):
                entries = doc.get(section, [])
                if not isinstance(entries, list):
                    raise InvalidSimulation(f"{section} must be a list")
                for entry in entries:
                    _mapping(entry, f"{section} entry")
            for event in doc.get("events", []):
                _mapping(event.get("trigger", {}), "event trigger")
                _mapping(event.get("impact", {}), "event impact")
            if not doc.get("entities"):
                raise InvalidSimulation("PDL must declare entities")
        return doc
    except yaml.YAMLError as exc:
        raise InvalidSimulation(f"Invalid {name} YAML: {exc}") from exc


def _validate(pdl_path: Path, cascade: str | None) -> None:
    try:
        PDLLoader(pdl_path).to_event_registry(cascade)
        roster = build_roster(pdl_path)
        if not roster:
            raise InvalidSimulation("PDL has no modelled entities")
        execution_order(build_flow_adjacency(pdl_path))
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
    ) as exc:
        raise InvalidSimulation(f"Invalid simulation input: {exc}") from exc


def _reserve(root: Path) -> tuple[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    while True:
        identity = new_run_id()
        directory = root / identity
        try:
            directory.mkdir()
        except FileExistsError:
            continue
        return identity, directory


def prepare_run(
    jobs_root: Path,
    *,
    pdl: str,
    roster: str | None = None,
    cascade: str | None = None,
    label: str | None = None,
) -> PreparedRun:
    """Validate first, then reserve a simulation-owned ID and private inputs."""
    _documents(pdl, "PDL")
    if roster is not None:
        _documents(roster, "roster")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "scenario.pdl.yaml"
        path.write_text(pdl, encoding="utf-8")
        if roster is not None:
            path.with_name("scenario.roster.yaml").write_text(
                roster, encoding="utf-8"
            )
        _validate(path, cascade)
    identity, directory = _reserve(jobs_root.resolve())
    try:
        input_dir = directory / "input"
        input_dir.mkdir()
        pdl_path = input_dir / "scenario.pdl.yaml"
        pdl_path.write_text(pdl, encoding="utf-8")
        if roster is not None:
            (input_dir / "scenario.roster.yaml").write_text(
                roster, encoding="utf-8"
            )
        shutil.copy2(INPUT_DIR / "SimulatorScenarios_template.csv", input_dir)
        output_root = directory / "output"
        (output_root / identity).mkdir(parents=True)
        run = PreparedRun(
            identity,
            directory,
            pdl_path,
            input_dir,
            output_root,
            directory / "progress.json",
            cascade,
            label,
        )
        (directory / "context.json").write_text(
            json.dumps(
                {
                    key: str(value) if isinstance(value, Path) else value
                    for key, value in vars(run).items()
                }
            ),
            encoding="utf-8",
        )
        return run
    except Exception:
        shutil.rmtree(directory)
        raise


def load_prepared_run(context_path: Path) -> PreparedRun:
    values = json.loads(context_path.read_text(encoding="utf-8"))
    for key in (
        "directory",
        "pdl_path",
        "input_dir",
        "output_root",
        "progress_path",
    ):
        values[key] = Path(values[key])
    return PreparedRun(**values)


def write_progress(path: Path, snapshot: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot), encoding="utf-8")
    temporary.replace(path)


def read_progress(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        for key in (
            "step",
            "scenario_total_steps",
            "completed_steps",
            "total_steps",
        ):
            if type(data.get(key)) is not int or data[key] < 0:
                return None
        percent = data.get("percent_complete")
        if not isinstance(percent, (int, float)) or not math.isfinite(
            percent
        ):
            return None
        if not 0 <= percent <= 100:
            return None
        if data["completed_steps"] > data["total_steps"]:
            return None
        if data["step"] > data["scenario_total_steps"]:
            return None
        if (
            data.get("scenario_id") is not None
            and type(data["scenario_id"]) is not int
        ):
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None


def _execute(
    *,
    identity: str,
    input_dir: Path,
    output_root: Path,
    pdl: str | None,
    cascade: str | None,
    label: str | None,
    progress_path: Path | None = None,
) -> None:
    csv_path = input_dir / "SimulatorScenarios.csv"
    template = input_dir / "SimulatorScenarios_template.csv"
    if template.exists():
        shutil.copy2(template, csv_path)
    rows = pd.read_csv(csv_path)
    registry = None
    if pdl:
        registry = PDLLoader(pdl).to_event_registry(cascade)
        baseline = rows[rows["id"] == 0].copy()
        if len(baseline) != 1:
            raise ValueError("Template must contain exactly one baseline row")
        shock = baseline.copy()
        shock["id"] = 1
        rows = pd.concat([baseline, shock], ignore_index=True)
        rows.to_csv(csv_path, index=False)
    if not {"id", "period_num"}.issubset(rows.columns):
        raise ValueError("Scenario CSV needs id and period_num columns")
    periods = rows["period_num"]
    if periods.isna().any() or periods.nunique() != 1 or periods.iloc[0] <= 0:
        raise ValueError("Scenarios must share one positive period_num")
    period_num = int(periods.iloc[0])
    scenario_ids = [int(value) for value in rows["id"]]
    output = output_root / identity
    config = Config(
        project_name="provider-simenv",
        project_root=str(PACKAGE_DIR),
        input_folder=str(input_dir),
        output_folder=str(output),
    )
    simulator = Simulator(
        config=config,
        scenario_cls=SupplyChainScenario,
        model_cls=SupplyChainModel,
    )
    attributes = ("_event_registry", "_pdl_path", "_progress_callback")
    previous = {key: SupplyChainModel.__dict__.get(key) for key in attributes}
    present = {key for key in attributes if key in SupplyChainModel.__dict__}
    completed = 0

    def publish(scenario_id, step):
        nonlocal completed
        if step:
            completed += 1
        if progress_path is not None:
            total = len(scenario_ids) * period_num
            write_progress(
                progress_path,
                {
                    "scenario_id": scenario_id,
                    "step": step,
                    "scenario_total_steps": period_num,
                    "completed_steps": completed,
                    "total_steps": total,
                    "percent_complete": completed / total * 100,
                },
            )

    try:
        injections = {}
        if registry is not None:
            injections.update(_event_registry=registry, _pdl_path=pdl)
        if progress_path is not None:
            # staticmethod avoids binding the model instance to the callback.
            injections["_progress_callback"] = staticmethod(publish)
            publish(None, 0)
        for key, value in injections.items():
            setattr(SupplyChainModel, key, value)
        start_run(
            str(output_root),
            identity,
            pdl=pdl,
            scenario_ids=scenario_ids,
            period_num=period_num,
            label=label,
        )
        try:
            simulator.run()
        except Exception:
            finish_run(str(output_root), identity, status="failed")
            raise
        else:
            finish_run(str(output_root), identity, status="completed")
    finally:
        for key in attributes:
            if key in present:
                setattr(SupplyChainModel, key, previous[key])
            elif key in SupplyChainModel.__dict__:
                delattr(SupplyChainModel, key)


def execute_prepared_run(run: PreparedRun) -> None:
    _execute(
        identity=run.id,
        input_dir=run.input_dir,
        output_root=run.output_root,
        pdl=str(run.pdl_path),
        cascade=run.cascade,
        label=run.label,
        progress_path=run.progress_path,
    )


def execute_cli(
    *,
    pdl: str | None,
    cascade: str | None,
    label: str | None,
    postgres_url: str | None,
) -> None:
    if postgres_url:
        os.environ["PROVIDER_SIMENV_POSTGRES_URL"] = postgres_url
    identity, _ = _reserve(OUTPUT_ROOT)
    _execute(
        identity=identity,
        input_dir=INPUT_DIR,
        output_root=OUTPUT_ROOT,
        pdl=pdl,
        cascade=cascade,
        label=label,
    )
