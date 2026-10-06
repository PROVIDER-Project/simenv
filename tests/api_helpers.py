"""Shared API test inputs and condition-based lifecycle waiting."""

import time
from pathlib import Path

from provider_simenv.execution import prepare_run

SCENARIOS = Path(__file__).parents[1] / "src/provider_simenv/scenarios"
PDL = (SCENARIOS / "s1-soja.pdl.yaml").read_text()
ROSTER = (SCENARIOS / "s1-soja.roster.yaml").read_text()


def submit(store, label=None):
    run = prepare_run(
        store.data_dir / "jobs", pdl=PDL, roster=ROSTER, label=label
    )
    return run, store.add(run)


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    raise AssertionError("Condition was not reached before timeout")
