"""Chart series + playhead for the bottom price card."""
from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot

from ..data.source import DataSource


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi <= lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


class ChartController(QObject):
    chartChanged = Signal()

    def __init__(self, source: DataSource) -> None:
        super().__init__()
        self._source = source
        self._scenario = 0
        self._periods: list[int] = []
        self._soja_norm: list[float] = []
        self._feed_norm: list[float] = []
        self._playhead_fraction = 0.0

    @Property(list, notify=chartChanged)
    def sojaNorm(self) -> list[float]:
        return self._soja_norm

    @Property(list, notify=chartChanged)
    def feedNorm(self) -> list[float]:
        return self._feed_norm

    @Property(float, notify=chartChanged)
    def playheadFraction(self) -> float:
        return self._playhead_fraction

    @Property(bool, notify=chartChanged)
    def hasData(self) -> bool:
        return len(self._periods) > 0

    @Slot(int)
    def setScenario(self, scenario: int) -> None:
        self._scenario = scenario
        try:
            self._periods = self._source.periods(scenario)
            envs = [self._source.environment_at(scenario, p) for p in self._periods]
            soja = [e.soja_price for e in envs]
            feed = [e.feed_price for e in envs]
            self._soja_norm = _normalize(soja)
            self._feed_norm = _normalize(feed)
        except Exception:
            self._periods = []
            self._soja_norm = []
            self._feed_norm = []
        self._playhead_fraction = 0.0
        self.chartChanged.emit()

    @Slot(int)
    def setPeriodIndex(self, index: int) -> None:
        n = len(self._periods)
        if n <= 1:
            self._playhead_fraction = 0.0
        else:
            self._playhead_fraction = max(0.0, min(1.0, index / (n - 1)))
        self.chartChanged.emit()
