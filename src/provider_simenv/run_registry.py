"""
Per-run output directory registry

Gives every simulation run its own directory under the output root, so no run
appends to another run's CSVs, and indexes those directories in runs.json
beside them.

Layout:
    data/output/
        runs.json
        20260913T104512Z-a3f9c1e2/
            Result_Simulator_Environment.csv
            ...

Run lifecycle:
    1. new_run_id() -> a UTC timestamp plus a short uuid4. The timestamp
       prefix sorts chronologically as plain text, so run order survives a
       stale or missing runs.json.
    2. start_run() -> append the entry with status "running", before the
       simulation starts, so a run that dies still leaves a trace.
    3. finish_run() -> re-read runs.json from disk and patch that entry to
       "completed" or "failed" with a finished_at.
    4. resolve_run() -> the newest completed run, or a named one.

runs.json sits beside the run directories rather than inside them, so deleting
a run directory does not take the index with it. The two can drift: an entry
whose directory is gone is skipped with a warning, and a directory with no
entry stays readable by naming it explicitly.

Writes repair, reads raise. An unreadable runs.json is set aside by start_run
and finish_run as runs.json.corrupt-<stamp>, which then carry on with a fresh
index rather than letting bookkeeping block a simulation or discard one that
already succeeded. resolve_run raises instead, so a corrupt index never passes
for "no runs" and hands back the wrong directory.

git_sha records what HEAD pointed at, not proof that the working tree matched
it; pdl_sha256 is the exact provenance of the input the run actually used.

Concurrency:
    runs.json is not locked. Two simulations started at once race on it and
    the loser's entry is lost. Single maintainer, single machine - accepted
    rather than solved.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MANIFEST_NAME = "runs.json"


def new_run_id() -> str:
    """
    Builds a run id of the form 20260913T104512Z-a3f9c1e2.

    No colons: this string is a directory name and Windows forbids them.
    """
    return f"{_stamp()}-{uuid.uuid4().hex[:8]}"


def run_dir(output_root: str, run_id: str) -> str:
    return os.path.join(output_root, run_id)


def run_record(
    run_id: str,
    *,
    pdl: str | None,
    scenario_ids: list[int],
    period_num: int,
    label: str | None = None,
    started_at: datetime | None = None,
) -> dict:
    """
    The record describing one run, written to runs.json and to sim_run.

    Built in one place so the two stores cannot drift: the PDL basename, its
    hash and the git sha are derived here and nowhere else. started_at
    defaults to now; main.py passes one so both stores record the same instant.
    """
    return {
        "run_id": run_id,
        "started_at": started_at.isoformat() if started_at else _now(),
        "finished_at": None,
        "status": "running",
        "pdl": os.path.basename(pdl) if pdl else None,
        "pdl_sha256": _file_sha256(pdl) if pdl else None,
        "scenario_ids": [int(i) for i in scenario_ids],
        "period_num": int(period_num),
        "git_sha": git_sha(),
        "label": label,
    }


def start_run(output_root: str, record: dict) -> None:
    """
    Appends record to runs.json.

    Creates the output root if it is missing; the run directory itself is
    left to Config, which makes it on the way to writing the CSVs.

    The record comes from run_record(), which main.py also hands to the tick
    writer for sim_run, so the two stores describe the run identically.
    """
    manifest = _read_manifest(output_root, repair=True)
    manifest["runs"].append(record)
    _write_manifest(output_root, manifest)


def finish_run(output_root: str, run_id: str, *, status: str) -> None:
    """
    Patches run_id's entry to status and stamps finished_at.

    Re-reads runs.json first, so an entry another process appended while the
    simulation was running is not dropped. A repaired index has no entry to
    patch: the run's output is left where it is and named in the warning,
    rather than recorded from the nothing this function knows about it.
    """
    manifest = _read_manifest(output_root, repair=True)
    for entry in manifest["runs"]:
        if entry.get("run_id") == run_id:
            entry["status"] = status
            entry["finished_at"] = _now()
            _write_manifest(output_root, manifest)
            return
    logger.warning(
        "no %s entry for run %s - its output is in %s",
        MANIFEST_NAME, run_id, run_dir(output_root, run_id),
    )


def resolve_run(output_root: str, run_id: str | None = None) -> str:
    """
    Returns the run id to read from: run_id when given, otherwise the newest
    completed run. Entries whose directory has been deleted are skipped.
    """
    entries = _read_manifest(output_root)["runs"]

    if run_id is not None:
        entry = next(
            (e for e in entries if e.get("run_id") == run_id), None
        )
        if entry is None:
            raise RuntimeError(
                f"run {run_id} is not in {_manifest_path(output_root)} - "
                "name its directory with --input to read it anyway"
            )
        if not os.path.isdir(run_dir(output_root, run_id)):
            raise RuntimeError(
                f"run {run_id} is indexed but its directory is gone"
            )
        if entry.get("status") != "completed":
            logger.warning(
                "run %s has status %s", run_id, entry.get("status")
            )
        return run_id

    completed = [
        e for e in entries
        if e.get("status") == "completed" and e.get("run_id")
    ]
    if not completed:
        raise RuntimeError(
            f"no completed run in {_manifest_path(output_root)} - run the "
            "simulation first, or name a directory with --input"
        )
    newest = sorted(completed, key=lambda e: e["run_id"], reverse=True)
    for entry in newest:
        if os.path.isdir(run_dir(output_root, entry["run_id"])):
            return entry["run_id"]
        logger.warning(
            "run %s is indexed but its directory is gone - skipping",
            entry["run_id"],
        )
    raise RuntimeError(
        f"every completed run in {_manifest_path(output_root)} has lost its "
        "directory - run the simulation again, or use --input"
    )


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manifest_path(output_root: str) -> str:
    return os.path.join(output_root, MANIFEST_NAME)


def _read_manifest(output_root: str, *, repair: bool = False) -> dict:
    path = _manifest_path(output_root)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {"runs": []}
    except (OSError, json.JSONDecodeError) as exc:
        if repair:
            _set_aside(path, str(exc))
            return {"runs": []}
        raise RuntimeError(
            f"{path} is unreadable: {exc} - move it aside to start a fresh "
            "index"
        ) from exc
    runs = data.get("runs") if isinstance(data, dict) else None
    if not isinstance(runs, list):
        if repair:
            _set_aside(path, "no runs list")
            return {"runs": []}
        raise RuntimeError(
            f"{path} has no runs list - move it aside to start a fresh index"
        )
    return {"runs": runs}


def _set_aside(path: str, reason: str) -> None:
    target = f"{path}.corrupt-{_stamp()}"
    try:
        os.replace(path, target)
    except OSError as exc:
        logger.warning("could not set %s aside: %s", MANIFEST_NAME, exc)
        return
    logger.warning(
        "%s was unreadable (%s) - set aside as %s, starting a fresh index",
        MANIFEST_NAME, reason, os.path.basename(target),
    )


def _write_manifest(output_root: str, manifest: dict) -> None:
    os.makedirs(output_root, exist_ok=True)
    path = _manifest_path(output_root)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _file_sha256(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError as exc:
        logger.warning("could not hash %s: %s", path, exc)
        return None


def git_sha() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=here, capture_output=True, text=True, timeout=5,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read git sha: %s", exc)
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None
