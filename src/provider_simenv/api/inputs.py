"""Read preserved job inputs without starting or modifying an experiment."""

import csv
import hashlib
import io
import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from ..execution import _documents
from ..pdl_loader import PDLLoader

MAX_INPUT_BYTES = 8 * 1024 * 1024


class InputsUnavailable(Exception):
    pass


def _read(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise InputsUnavailable("Preserved input exceeds the 8 MiB read limit")
    return raw


def _document(raw: bytes, name: str) -> dict:
    value = _documents(raw.decode("utf-8"), name)
    json.dumps(value, allow_nan=False)  # Reject cycles, dates, sets and NaN.

    def validate(item):
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ValueError("Document keys must be strings")
            for child in item.values():
                validate(child)
        elif isinstance(item, list):
            for child in item:
                validate(child)

    validate(value)
    if not isinstance(value, dict):
        raise TypeError("Expected a document mapping")
    return value


def _parameters(path: Path, scenario: int, *, single=False) -> dict:
    rows = []
    for row in csv.DictReader(io.StringIO(_read(path).decode("utf-8"))):
        if len(rows) >= 1000:
            raise InputsUnavailable("Preserved scenario table is too large")
        rows.append(row)
    selected = [row for row in rows if Decimal(row["id"]) == scenario]
    if len(selected) != 1 or (single and len(rows) != 1):
        raise InputsUnavailable("Preserved scenario parameters are invalid")
    def number(raw):
        value = Decimal(raw)
        if not value.is_finite():
            raise ValueError("Nonfinite parameter")
        if value == value.to_integral_value():
            if abs(value) > 2**53 - 1:
                raise ValueError("Parameter exceeds exact JSON integer range")
            return int(value)
        return float(value)

    values = {key: number(value) for key, value in selected[0].items()
              if key != "id"}
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError("Nonfinite scenario parameters")
    return values


def read_inputs(directory: Path, job: dict, current_template: Path) -> dict:
    try:
        inputs = directory / "input"
        pdl_path = inputs / "scenario.pdl.yaml"
        pdl_raw = _read(pdl_path)
        roster_path = inputs / "scenario.roster.yaml"
        roster_raw = _read(roster_path) if roster_path.exists() else None
        parameters = _parameters(
            inputs / "SimulatorScenarios_template.csv", 0,
        )
        manifest_path = directory / "output/runs.json"
        entry = None
        if manifest_path.exists():
            manifest = json.loads(_read(manifest_path))
            entries = manifest["runs"]
            if not isinstance(entries, list):
                raise ValueError("Invalid execution manifest")
            matches = [row for row in entries if row["run_id"] == job["id"]]
            if len(matches) > 1:
                raise ValueError("Duplicate execution evidence")
            entry = matches[0] if matches else None
        if job["status"] == "completed":
            if entry is None:
                raise InputsUnavailable("Recorded input evidence is missing")
            executed = _parameters(
                inputs / "SimulatorScenarios.csv", 1, single=True,
            )
            if executed != parameters:
                raise InputsUnavailable(
                    "Executed parameters differ from the preserved template"
                )
        if entry is not None:
            hashes = {
                "pdl_sha256": hashlib.sha256(pdl_raw).hexdigest(),
                "roster_sha256": (
                    hashlib.sha256(roster_raw).hexdigest()
                    if roster_raw is not None else None
                ),
            }
            if any(entry[key] != value for key, value in hashes.items()):
                raise InputsUnavailable(
                    "Preserved documents differ from recorded input hashes"
                )
        pdl = _document(pdl_raw, "PDL")
        roster = (
            _document(roster_raw, "roster")
            if roster_raw is not None else None
        )
        cascade = PDLLoader(str(pdl_path)).to_event_registry(
            job["cascade"]
        )["cascade_id"]
        if not isinstance(cascade, str) or not cascade.strip():
            raise InputsUnavailable("Preserved cascade ID is invalid")
        return {
            "pdl": pdl, "roster": roster, "cascade": cascade,
            "parameters": parameters,
            "current_parameters": _parameters(current_template, 0),
            "evidence": "execution-hashes" if entry else "preserved",
        }
    except (OSError, ValueError, TypeError, KeyError, csv.Error,
            InvalidOperation, yaml.YAMLError) as exc:
        raise InputsUnavailable(
            "Preserved simulation inputs are unavailable or invalid"
        ) from exc
