"""Canonical entrypoint — launches the QML visualizer.

Run from the repo root with:

    python -m visualization.app.main

The legacy QtWidgets app (map_view/chart/hud/nodes/ships/timeline/runner and the
old MainWindow) was retired in the CRM-map redesign (branch 21, P5). This module
now delegates to the QML application in ``qml_app.py`` so there is one canonical
run command.
"""
from __future__ import annotations

from .qml_app import run_qml_app


def main() -> None:
    run_qml_app()


if __name__ == "__main__":
    main()
