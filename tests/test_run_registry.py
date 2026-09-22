import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from provider_simenv import run_registry


@pytest.fixture(autouse=True)
def stable_git_sha(monkeypatch):
    monkeypatch.setattr(run_registry, "git_sha", lambda: "abc123")


def record_run(
    output_root: Path,
    run_id: str,
    status: str | None = None,
) -> None:
    (output_root / run_id).mkdir()
    run_registry.start_run(
        str(output_root),
        run_registry.run_record(
            run_id,
            pdl=None,
            scenario_ids=[0, 1],
            period_num=365,
        ),
    )
    if status is not None:
        run_registry.finish_run(str(output_root), run_id, status=status)


def test_run_ids_sort_chronologically(monkeypatch):
    moments = iter([
        datetime(2026, 9, 13, 10, 45, 12, tzinfo=timezone.utc),
        datetime(2026, 9, 13, 10, 45, 13, tzinfo=timezone.utc),
    ])

    class ControlledDateTime:
        @classmethod
        def now(cls, tz=None):
            return next(moments)

    monkeypatch.setattr(run_registry, "datetime", ControlledDateTime)

    run_ids = [run_registry.new_run_id(), run_registry.new_run_id()]

    assert run_ids == sorted(run_ids)
    assert run_ids[0].startswith("20260913T104512Z-")
    assert run_ids[1].startswith("20260913T104513Z-")


def test_run_id_contains_no_windows_illegal_characters():
    run_id = run_registry.new_run_id()

    assert not any(char in run_id for char in '<>:"/\\|?*')
    assert all(ord(char) >= 32 for char in run_id)


def test_start_then_finish_round_trips(tmp_path):
    run_id = "20260913T100000Z-aaaaaaaa"

    run_registry.start_run(
        str(tmp_path),
        run_registry.run_record(
            run_id,
            pdl=None,
            scenario_ids=[0, 1],
            period_num=365,
            label="smoke",
        ),
    )
    run_registry.finish_run(str(tmp_path), run_id, status="completed")

    manifest = json.loads(
        (tmp_path / "runs.json").read_text(encoding="utf-8")
    )
    entry = manifest["runs"][0]
    assert entry["run_id"] == run_id
    assert entry["status"] == "completed"
    assert entry["finished_at"] is not None
    assert entry["scenario_ids"] == [0, 1]
    assert entry["period_num"] == 365
    assert entry["label"] == "smoke"


def test_resolve_returns_newest_completed_run(tmp_path):
    older_completed = "20260913T090000Z-aaaaaaaa"
    newer_completed = "20260913T100000Z-bbbbbbbb"
    failed = "20260913T110000Z-cccccccc"
    running = "20260913T120000Z-dddddddd"

    record_run(tmp_path, older_completed, "completed")
    record_run(tmp_path, newer_completed, "completed")
    record_run(tmp_path, failed, "failed")
    record_run(tmp_path, running)

    assert run_registry.resolve_run(str(tmp_path)) == newer_completed


def test_resolve_skips_deleted_run_directory(tmp_path, caplog):
    older = "20260913T100000Z-aaaaaaaa"
    newer = "20260913T110000Z-bbbbbbbb"
    record_run(tmp_path, older, "completed")
    record_run(tmp_path, newer, "completed")
    (tmp_path / newer).rmdir()
    caplog.set_level(logging.WARNING, logger=run_registry.__name__)

    assert run_registry.resolve_run(str(tmp_path)) == older
    assert f"run {newer} is indexed but its directory is gone - skipping" in caplog.text


def test_resolve_unknown_explicit_run_has_clear_error(tmp_path):
    with pytest.raises(RuntimeError, match="is not in"):
        run_registry.resolve_run(str(tmp_path), "unknown")


def test_resolve_explicit_run_with_deleted_directory_raises(tmp_path):
    run_id = "20260913T100000Z-aaaaaaaa"
    record_run(tmp_path, run_id, "completed")
    (tmp_path / run_id).rmdir()

    with pytest.raises(
        RuntimeError,
        match="is indexed but its directory is gone",
    ):
        run_registry.resolve_run(str(tmp_path), run_id)


def test_resolve_explicit_failed_run_returns_with_warning(tmp_path, caplog):
    run_id = "20260913T100000Z-aaaaaaaa"
    record_run(tmp_path, run_id, "failed")
    caplog.set_level(logging.WARNING, logger=run_registry.__name__)

    assert run_registry.resolve_run(str(tmp_path), run_id) == run_id
    assert f"run {run_id} has status failed" in caplog.text


@pytest.mark.parametrize("manifest_exists", [False, True])
def test_resolve_missing_or_empty_manifest_has_clear_error(
    tmp_path,
    manifest_exists,
):
    if manifest_exists:
        (tmp_path / "runs.json").write_text(
            json.dumps({"runs": []}),
            encoding="utf-8",
        )

    with pytest.raises(RuntimeError, match="no completed run"):
        run_registry.resolve_run(str(tmp_path))


@pytest.mark.parametrize(
    "contents",
    [
        "not json",
        json.dumps({"wrong": []}),
    ],
)
def test_start_run_repairs_corrupt_manifest(tmp_path, contents):
    manifest_path = tmp_path / "runs.json"
    manifest_path.write_text(contents, encoding="utf-8")

    run_registry.start_run(
        str(tmp_path),
        run_registry.run_record(
            "20260913T100000Z-aaaaaaaa",
            pdl=None,
            scenario_ids=[0, 1],
            period_num=365,
        ),
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["runs"][0]["status"] == "running"
    assert len(list(tmp_path.glob("runs.json.corrupt-*"))) == 1


@pytest.mark.parametrize(
    "contents",
    [
        "not json",
        json.dumps({"wrong": []}),
    ],
)
def test_finish_run_repairs_corrupt_manifest(tmp_path, contents, caplog):
    manifest_path = tmp_path / "runs.json"
    manifest_path.write_text(contents, encoding="utf-8")
    caplog.set_level(logging.WARNING, logger=run_registry.__name__)

    run_registry.finish_run(
        str(tmp_path),
        "20260913T100000Z-aaaaaaaa",
        status="completed",
    )

    assert not manifest_path.exists()
    assert len(list(tmp_path.glob("runs.json.corrupt-*"))) == 1
    assert "no runs.json entry for run" in caplog.text


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("not json", "is unreadable"),
        (json.dumps({"wrong": []}), "has no runs list"),
    ],
)
def test_resolve_raises_on_corrupt_manifest(tmp_path, contents, message):
    manifest_path = tmp_path / "runs.json"
    manifest_path.write_text(contents, encoding="utf-8")

    with pytest.raises(RuntimeError, match=message):
        run_registry.resolve_run(str(tmp_path))

    assert manifest_path.exists()
    assert list(tmp_path.glob("runs.json.corrupt-*")) == []
