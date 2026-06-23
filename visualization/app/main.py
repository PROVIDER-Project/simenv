"""Application entrypoint and main window.

Wires a CsvDataSource into the MapView and provides a scenario selector and a
period seek slider. Timeline playback and the price HUD are added in later
phases; this is the Phase-1 interactive shell.

Run from the repo root with:

    python -m visualization.app.main
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..data.csv_source import CsvDataSource, MissingOutputError
from ..data.source import DataSource
from .chart import PriceChart
from .map_view import MapView
from .runner import RunControls
from .timeline import TimelineBar

# Human-friendly scenario names. id 0 is always the baseline; id 1 is the PDL
# shock scenario in the current data. Unknown ids fall back to a generic label.
_SCENARIO_NAMES = {0: "baseline", 1: "PDL shock"}


def _scenario_label(scenario: int) -> str:
    name = _SCENARIO_NAMES.get(scenario)
    return f"Scenario {scenario} — {name}" if name else f"Scenario {scenario}"


_STYLE = """
QMainWindow, QWidget { background: #0b1620; color: #e6edf3; }
QLabel { color: #c7d1da; font-size: 13px; }
QLabel#title { color: #e6edf3; font-size: 15px; font-weight: 600; }
QComboBox {
    background: #16242f; border: 1px solid #2a3b49; border-radius: 6px;
    padding: 5px 10px; min-width: 200px; color: #e6edf3;
}
QComboBox::drop-down { border: 0; width: 22px; }
QComboBox QAbstractItemView {
    background: #16242f; color: #e6edf3; selection-background-color: #24435f;
    border: 1px solid #2a3b49;
}
QSlider::groove:horizontal { height: 5px; background: #24323d; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #4c9be0; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #e6edf3; width: 14px; margin: -6px 0; border-radius: 7px;
}
"""


class MainWindow(QMainWindow):
    def __init__(self, source: DataSource) -> None:
        super().__init__()
        self._source = source
        self.setWindowTitle("PROVIDER — Supply Chain HQ Map")

        self._map = MapView(source)
        self._chart = PriceChart(source)
        self._scenario = QComboBox()
        self._heatmap = QCheckBox("Drought heatmap")
        self._heatmap.setChecked(True)
        self._timeline = TimelineBar()
        self._runner = RunControls()
        self._status = QLabel()
        self._status.setObjectName("status")

        self._periods: list[int] = []

        self._build_ui()
        self._populate_scenarios()

        # React to user input.
        self._scenario.currentIndexChanged.connect(self._on_scenario_changed)
        self._timeline.indexChanged.connect(self._refresh)
        self._runner.outputChanged.connect(self._on_output_changed)
        self._heatmap.toggled.connect(self._map.set_heatmap_visible)

        # Initial render (if data is available).
        if self._scenario.count() > 0:
            self._on_scenario_changed()

    # -- layout ------------------------------------------------------------

    def _build_ui(self) -> None:
        title = QLabel("PROVIDER — Supply Chain HQ Map")
        title.setObjectName("title")

        scenario_row = QHBoxLayout()
        scenario_row.setSpacing(10)
        scenario_row.addWidget(QLabel("Scenario"))
        scenario_row.addWidget(self._scenario)
        scenario_row.addSpacing(16)
        scenario_row.addWidget(self._heatmap)
        scenario_row.addStretch(1)

        root = QVBoxLayout()
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        content = QSplitter(Qt.Orientation.Horizontal)
        content.addWidget(self._map)
        content.addWidget(self._chart)
        content.setStretchFactor(0, 1)
        content.setStretchFactor(1, 0)
        content.setSizes([960, 320])

        root.addWidget(title)
        root.addLayout(scenario_row)
        root.addWidget(content, stretch=1)
        root.addWidget(self._timeline)
        root.addWidget(self._status)
        root.addWidget(self._runner)

        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

    # -- data wiring -------------------------------------------------------

    def _populate_scenarios(self) -> None:
        try:
            scenarios = self._source.scenarios()
        except MissingOutputError:
            scenarios = []
        if not scenarios:
            self._status.setText(
                "No simulation output found. Run the simulation, then reload."
            )
            return
        for s in scenarios:
            self._scenario.addItem(_scenario_label(s), s)

    def _current_scenario(self) -> int:
        return int(self._scenario.currentData())

    def _on_scenario_changed(self) -> None:
        scenario = self._current_scenario()
        self._periods = self._source.periods(scenario)
        self._chart.set_scenario(scenario)
        # set_periods resets to index 0 and emits indexChanged -> _refresh(0).
        self._timeline.set_periods(self._periods)

    def _on_output_changed(self) -> None:
        """Reload the data source after a sim run / reload and repaint."""
        prev = self._scenario.currentData()
        self._source.reload()
        self._scenario.blockSignals(True)
        self._scenario.clear()
        self._populate_scenarios()
        if prev is not None:
            idx = self._scenario.findData(prev)
            if idx >= 0:
                self._scenario.setCurrentIndex(idx)
        self._scenario.blockSignals(False)
        if self._scenario.count() > 0:
            self._on_scenario_changed()

    def _refresh(self, index: int) -> None:
        scenario = self._current_scenario()
        period = self._periods[index]
        self._map.show_period(scenario, period)
        self._chart.update_period(period)
        env = self._source.environment_at(scenario, period)
        self._status.setText(
            f"soja {env.soja_price:,.1f}   ·   feed {env.feed_price:,.1f}   ·   "
            f"shock {env.shock_scale:.2f}   ·   drought {env.drought_severity:.2f}   ·   "
            f"transport util {env.transport_utilisation:.0%}"
        )


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(_STYLE)
    source = CsvDataSource()
    win = MainWindow(source)
    win.resize(1280, 820)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
