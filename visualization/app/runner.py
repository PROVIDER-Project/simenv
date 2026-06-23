"""RunControls — run the simulation as a subprocess and reload its output.

A self-contained widget: an optional PDL selector, a 'Run simulation' button
(launches `python -m provider_simenv.main [--pdl ...]` via QProcess, streaming
stdout/stderr into a log panel), and a 'Reload output' button. Emits
outputChanged() when fresh output is available (run finished cleanly, or reload
clicked) so the main window can reload the DataSource and repaint.

This never imports provider_simenv — it only invokes it as a subprocess, which
is the whole point of the self-contained boundary.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PDL_DIR = _REPO_ROOT / "src" / "provider_simenv" / "scenarios"


class RunControls(QWidget):
    outputChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._proc: QProcess | None = None

        self._pdl = QComboBox()
        self._pdl.addItem("baseline only (no PDL)", None)
        if _PDL_DIR.exists():
            for p in sorted(_PDL_DIR.glob("*.pdl.yaml")):
                self._pdl.addItem(p.name, str(p))

        self._run = QPushButton("Run simulation")
        self._reload = QPushButton("Reload output")
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(96)
        self._log.setPlaceholderText("Simulation log…")

        self._build_ui()
        self._run.clicked.connect(self._on_run)
        self._reload.clicked.connect(self.outputChanged.emit)

    def _build_ui(self) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(QLabel("PDL"))
        row.addWidget(self._pdl)
        row.addWidget(self._run)
        row.addWidget(self._reload)
        row.addStretch(1)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        root.addLayout(row)
        root.addWidget(self._log)
        self.setLayout(root)

    # -- run lifecycle -----------------------------------------------------

    def _append(self, text: str) -> None:
        self._log.appendPlainText(text.rstrip())

    def _on_run(self) -> None:
        if self._proc is not None:
            return  # a run is already in progress
        args = ["-m", "provider_simenv.main"]
        pdl = self._pdl.currentData()
        if pdl:
            args += ["--pdl", pdl]

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.setWorkingDirectory(str(_REPO_ROOT))
        proc.readyReadStandardOutput.connect(self._drain)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)

        self._proc = proc
        self._run.setEnabled(False)
        self._run.setText("Running…")
        self._log.clear()
        self._append(f"$ {Path(sys.executable).name} {' '.join(args)}")
        proc.start(sys.executable, args)

    def _drain(self) -> None:
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in data.splitlines():
            self._append(line)

    def _on_error(self, _error) -> None:
        if self._proc is not None:
            self._append(f"[process error] {self._proc.errorString()}")

    def _on_finished(self, code: int, _status) -> None:
        self._drain()
        self._append(f"[exit code {code}]")
        self._proc = None
        self._run.setEnabled(True)
        self._run.setText("Run simulation")
        if code == 0:
            self._append("Output updated — reloading map.")
            self.outputChanged.emit()
