"""Simulation subprocess runner for QML."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, Property, QProcess, Signal, Slot

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PDL_DIR = _REPO_ROOT / "src" / "provider_simenv" / "scenarios"


class RunnerController(QObject):
    logChanged = Signal()
    runningChanged = Signal()
    outputReloaded = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._proc: QProcess | None = None
        self._log = ""
        self._running = False
        self._pdl_labels: list[str] = ["baseline only"]
        self._pdl_paths: list[str | None] = [None]
        self._pdl_index = 0
        self._load_pdl()

    def _load_pdl(self) -> None:
        if _PDL_DIR.exists():
            for p in sorted(_PDL_DIR.glob("*.pdl.yaml")):
                self._pdl_labels.append(p.name)
                self._pdl_paths.append(str(p))

    @Property(str, notify=logChanged)
    def logText(self) -> str:
        return self._log

    @Property(bool, notify=runningChanged)
    def running(self) -> bool:
        return self._running

    @Property(list, notify=logChanged)
    def pdlLabels(self) -> list[str]:
        return self._pdl_labels

    @Property(int, notify=logChanged)
    def pdlIndex(self) -> int:
        return self._pdl_index

    @Slot(int)
    def setPdlIndex(self, index: int) -> None:
        if 0 <= index < len(self._pdl_labels):
            self._pdl_index = index

    def _append(self, text: str) -> None:
        self._log += text.rstrip() + "\n"
        self.logChanged.emit()

    @Slot()
    def runSimulation(self) -> None:
        if self._proc is not None:
            return
        args = ["-m", "provider_simenv.main"]
        pdl = self._pdl_paths[self._pdl_index]
        if pdl:
            args += ["--pdl", pdl]

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.setWorkingDirectory(str(_REPO_ROOT))
        proc.readyReadStandardOutput.connect(self._drain)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)

        self._proc = proc
        self._running = True
        self.runningChanged.emit()
        self._log = ""
        self._append(f"$ {Path(sys.executable).name} {' '.join(args)}")
        proc.start(sys.executable, args)

    @Slot()
    def reloadOutput(self) -> None:
        self.outputReloaded.emit()

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
        self._running = False
        self.runningChanged.emit()
        if code == 0:
            self._append("Output updated — reloading map.")
            self.outputReloaded.emit()
