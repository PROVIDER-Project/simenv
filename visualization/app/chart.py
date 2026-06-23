"""PriceChart — soja/feed price over time for the selected scenario.

A small matplotlib canvas (dark-themed to match the app). Plots the full price
series for the scenario once, then moves a vertical playhead as the timeline
advances. Reads only through the DataSource, like the rest of the view.
"""
from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..data.source import DataSource

_BG = "#0b1620"
_AXES_BG = "#0e1f2e"
_SOJA = "#e0a13b"
_FEED = "#d9694f"
_MUTED = "#9fb0bd"
_PLAYHEAD = "#e6edf3"


class PriceChart(QWidget):
    def __init__(self, source: DataSource) -> None:
        super().__init__()
        self._source = source
        self._periods: list[int] = []

        self._fig = Figure(figsize=(3.0, 2.6), facecolor=_BG)
        self._canvas = FigureCanvas(self._fig)
        self._ax = self._fig.add_subplot(111)
        self._ax2 = self._ax.twinx()
        self._playhead = None

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)
        self.setLayout(layout)
        self.setMinimumWidth(300)
        self.setMaximumWidth(380)

    def set_scenario(self, scenario: int) -> None:
        self._periods = self._source.periods(scenario)
        envs = [self._source.environment_at(scenario, p) for p in self._periods]
        soja = [e.soja_price for e in envs]
        feed = [e.feed_price for e in envs]

        self._ax.clear()
        self._ax2.clear()
        self._style()

        self._ax.plot(self._periods, soja, color=_SOJA, linewidth=1.4, label="soja")
        self._ax2.plot(self._periods, feed, color=_FEED, linewidth=1.4, label="feed")
        self._ax.set_ylabel("soja price", color=_SOJA, fontsize=8)
        self._ax2.set_ylabel("feed price", color=_FEED, fontsize=8)
        self._ax.set_xlabel("period", color=_MUTED, fontsize=8)

        start = self._periods[0] if self._periods else 0
        self._playhead = self._ax.axvline(start, color=_PLAYHEAD, linewidth=1.0, alpha=0.7)

        self._fig.tight_layout()
        self._canvas.draw_idle()

    def update_period(self, period: int) -> None:
        if self._playhead is not None:
            self._playhead.set_xdata([period, period])
            self._canvas.draw_idle()

    def _style(self) -> None:
        for ax in (self._ax, self._ax2):
            ax.set_facecolor(_AXES_BG)
            ax.tick_params(colors=_MUTED, labelsize=7)
            for spine in ax.spines.values():
                spine.set_color("#2a3b49")
        self._ax.grid(True, color="#1b2a38", linewidth=0.5)
