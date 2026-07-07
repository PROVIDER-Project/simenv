"""Main app bridge — scenario, period, metrics, playback, map node hints."""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot

from ..config import layout as L
from ..data.csv_source import MissingOutputError
from ..data.source import DataSource
from .chart_controller import ChartController
from .map_controller import MapController

_SCENARIO_NAMES = {0: "baseline", 1: "PDL shock"}

_GROUP_COLORS = {
    "BraFarmers": "#2E9E5B",
    "ArgFarmers": "#4CAE9E",
    "UsaFarmers": "#4A7FC4",
    "EuFarmers": "#9B6BAD",
    "Wholesalers": "#C4922E",
    "Processors": "#C46850",
    "FeedManufacturers": "#A85840",
    "FeedTraders": "#8F4838",
}

# Friendly labels for the ranked node bar-list (P3 data-chrome).
_GROUP_LABELS = {
    "BraFarmers": "BRA Farmers",
    "ArgFarmers": "ARG Farmers",
    "UsaFarmers": "USA Farmers",
    "EuFarmers": "EU Livestock",
    "Wholesalers": "Wholesalers",
    "Processors": "Processors",
    "FeedManufacturers": "Feed Mfrs",
    "FeedTraders": "Feed Traders",
}

# Coverage mini-bars: normalize corridor volume against a reference load and
# color each origin to match its farmer group.
_COVERAGE_REF = 1000.0
_COVERAGE_COLORS = {"BRA": "#2E9E5B", "ARG": "#4CAE9E", "USA": "#4A7FC4"}

# Outline SVG glyph per group (recolored per theme in QML). Farmers share a
# crop icon; origin is encoded by disc color, not by a separate icon.
_ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons" / "nodes"
_GROUP_ICONS = {
    "BraFarmers": "wheat",
    "ArgFarmers": "wheat",
    "UsaFarmers": "wheat",
    "EuFarmers": "barn",
    "Wholesalers": "warehouse",
    "Processors": "factory",
    "FeedManufacturers": "layers",
    "FeedTraders": "trade",
}
_ICON_URLS = {
    group: QUrl.fromLocalFile(str(_ICONS_DIR / f"{name}.svg")).toString()
    for group, name in _GROUP_ICONS.items()
}

_SPEEDS_MS = [240, 120, 60, 30]


def _scenario_label(scenario: int) -> str:
    name = _SCENARIO_NAMES.get(scenario)
    return f"Scenario {scenario} — {name}" if name else f"Scenario {scenario}"


class AppController(QObject):
    stateChanged = Signal()
    playingChanged = Signal()
    liveChanged = Signal()
    periodAppended = Signal()

    def __init__(
        self,
        source: DataSource,
        chart: ChartController,
        map_ctrl: MapController | None = None,
    ) -> None:
        super().__init__()
        self._source = source
        self._chart = chart
        self._map = map_ctrl
        self._scenarios: list[int] = []
        self._scenario_labels: list[str] = []
        self._scenario_index = 0
        self._periods: list[int] = []
        self._period_index = 0
        self._heatmap_visible = True
        self._playing = False
        self._speed_index = 1
        # Live spine: `_live` is true while a run is *generating* data (today the
        # subprocess runner; later a streaming DataSource). `_follow_live` makes
        # the playhead track the newest period while live.
        self._live = False
        self._follow_live = True
        self._status = ""
        self._soja_text = "—"
        self._feed_text = "—"
        self._drought_text = "—"
        self._transport_text = "—"
        self._drought_alpha = 0.0
        self._nodes: list[dict] = []
        self._node_bars: list[dict] = []
        self._coverage_bars: list[dict] = []
        self._transport_frac = 0.0
        self._ship_volumes = {"BRA": 0.0, "ARG": 0.0, "USA": 0.0}

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self.reload_data()

    # -- properties --------------------------------------------------------

    @Property(list, notify=stateChanged)
    def scenarioLabels(self) -> list[str]:
        return self._scenario_labels

    @Property(int, notify=stateChanged)
    def scenarioIndex(self) -> int:
        return self._scenario_index

    @Property(int, notify=stateChanged)
    def periodIndex(self) -> int:
        return self._period_index

    @Property(int, notify=stateChanged)
    def periodMax(self) -> int:
        return max(len(self._periods) - 1, 0)

    @Property(str, notify=stateChanged)
    def periodLabel(self) -> str:
        if not self._periods:
            return "period —"
        return f"period {self._periods[self._period_index]} / {self._periods[-1]}"

    @Property(bool, notify=stateChanged)
    def hasData(self) -> bool:
        return bool(self._scenarios)

    @Property(str, notify=stateChanged)
    def statusMessage(self) -> str:
        return self._status

    @Property(str, notify=stateChanged)
    def sojaText(self) -> str:
        return self._soja_text

    @Property(str, notify=stateChanged)
    def feedText(self) -> str:
        return self._feed_text

    @Property(str, notify=stateChanged)
    def droughtText(self) -> str:
        return self._drought_text

    @Property(str, notify=stateChanged)
    def transportText(self) -> str:
        return self._transport_text

    @Property(float, notify=stateChanged)
    def droughtAlpha(self) -> float:
        return self._drought_alpha

    @Property(bool, notify=stateChanged)
    def heatmapVisible(self) -> bool:
        return self._heatmap_visible

    @Property(list, notify=stateChanged)
    def nodes(self) -> list[dict]:
        return self._nodes

    @Property(list, notify=stateChanged)
    def nodeBars(self) -> list[dict]:
        return self._node_bars

    @Property(list, notify=stateChanged)
    def coverageBars(self) -> list[dict]:
        return self._coverage_bars

    @Property(float, notify=stateChanged)
    def transportFrac(self) -> float:
        return self._transport_frac

    @Property(bool, notify=playingChanged)
    def playing(self) -> bool:
        return self._playing

    @Property(int, notify=stateChanged)
    def speedIndex(self) -> int:
        return self._speed_index

    @Property(bool, notify=liveChanged)
    def live(self) -> bool:
        """True while a run is generating data (drives the header LIVE pulse)."""
        return self._live

    # -- slots ---------------------------------------------------------------

    @Slot()
    def reload_data(self) -> None:
        self._source.reload()
        try:
            self._scenarios = self._source.scenarios()
        except MissingOutputError:
            self._scenarios = []
        self._scenario_labels = [_scenario_label(s) for s in self._scenarios]
        if not self._scenarios:
            self._status = "No simulation output found. Run the simulation, then reload."
            self._periods = []
            self.stateChanged.emit()
            return
        self._status = ""
        prev = self._scenario_index
        self._scenario_index = min(prev, len(self._scenarios) - 1)
        self._load_scenario(self._scenario_index)

    @Slot(int)
    def setScenarioIndex(self, index: int) -> None:
        if index < 0 or index >= len(self._scenarios):
            return
        self.pause()
        self._scenario_index = index
        self._load_scenario(index)

    @Slot(int)
    def setPeriodIndex(self, index: int) -> None:
        if not self._periods:
            return
        index = max(0, min(index, len(self._periods) - 1))
        self._period_index = index
        self._refresh_period()
        self.stateChanged.emit()

    @Slot(bool)
    def setHeatmapVisible(self, visible: bool) -> None:
        self._heatmap_visible = visible
        self._apply_drought_alpha()
        self.stateChanged.emit()

    @Slot()
    def togglePlay(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    @Slot()
    def play(self) -> None:
        if not self._periods or len(self._periods) <= 1:
            return
        self._playing = True
        self._timer.setInterval(_SPEEDS_MS[self._speed_index])
        self._timer.start()
        self.playingChanged.emit()

    @Slot()
    def pause(self) -> None:
        if not self._playing:
            return
        self._playing = False
        self._timer.stop()
        self.playingChanged.emit()

    @Slot()
    def stepBack(self) -> None:
        self.pause()
        self.setPeriodIndex(self._period_index - 1)

    @Slot()
    def stepForward(self) -> None:
        self.pause()
        self.setPeriodIndex(self._period_index + 1)

    @Slot(int)
    def setSpeedIndex(self, index: int) -> None:
        if 0 <= index < len(_SPEEDS_MS):
            self._speed_index = index
            if self._playing:
                self._timer.setInterval(_SPEEDS_MS[index])
            self.stateChanged.emit()

    @Slot(bool)
    def setLive(self, live: bool) -> None:
        """Set the live flag. Wired to `runner.runningChanged` in the launcher;
        a future streaming DataSource sets the same flag on connect/disconnect."""
        if live == self._live:
            return
        self._live = live
        self.liveChanged.emit()

    @Slot()
    def append_period(self) -> None:
        """Streaming hook — dormant today, the drop-in point for live data.

        Contract for a future ``PostgresDataSource`` streaming a run in progress:
        call this once per newly-durable tick. We re-read the current scenario's
        period list from the source (which will have grown by one) and, while
        ``live`` and following, advance the playhead to the newest period so the
        view tracks the running sim. The ``TimelineDock`` slider stays in sync
        via its existing ``Connections`` on ``stateChanged``. The CSV replay
        source never calls this, so behaviour is unchanged until the swap.
        """
        if not self._scenarios:
            return
        scenario = self._scenarios[self._scenario_index]
        self._periods = self._source.periods(scenario)
        if self._follow_live and self._live and self._periods:
            self._period_index = len(self._periods) - 1
            self._refresh_period()
        self.periodAppended.emit()
        self.stateChanged.emit()

    # -- internals -----------------------------------------------------------

    def _load_scenario(self, index: int) -> None:
        scenario = self._scenarios[index]
        self._periods = self._source.periods(scenario)
        self._period_index = 0
        self._chart.setScenario(scenario)
        self._refresh_period()
        self.stateChanged.emit()

    def _refresh_period(self) -> None:
        if not self._periods:
            return
        scenario = self._scenarios[self._scenario_index]
        period = self._periods[self._period_index]
        env = self._source.environment_at(scenario, period)
        self._soja_text = f"{env.soja_price:,.1f}"
        self._feed_text = f"{env.feed_price:,.1f}"
        self._drought_text = f"{env.drought_severity:.2f}"
        self._transport_text = f"{env.transport_utilisation:.0%}"
        self._transport_frac = max(0.0, min(float(env.transport_utilisation), 1.0))
        self._apply_drought_alpha(env.drought_severity)
        self._update_nodes(scenario, period)
        flows = self._source.origin_flows(scenario, period)
        self._ship_volumes = {
            "BRA": flows.bra_volume,
            "ARG": flows.arg_volume,
            "USA": flows.usa_volume,
        }
        self._coverage_bars = [
            {"label": origin,
             "frac": min(vol / _COVERAGE_REF, 1.0) if vol > 0 else 0.0,
             "color": _COVERAGE_COLORS[origin]}
            for origin, vol in (("BRA", flows.bra_volume),
                                ("ARG", flows.arg_volume),
                                ("USA", flows.usa_volume))
        ]
        if self._map is not None:
            self._map.setShipVolumes(
                flows.bra_volume, flows.arg_volume, flows.usa_volume,
            )
        self._chart.setPeriodIndex(self._period_index)

    def _apply_drought_alpha(self, severity: float | None = None) -> None:
        if severity is None and self._periods:
            scenario = self._scenarios[self._scenario_index]
            period = self._periods[self._period_index]
            severity = self._source.environment_at(scenario, period).drought_severity
        elif severity is None:
            severity = 0.0
        if not self._heatmap_visible:
            self._drought_alpha = 0.0
        else:
            self._drought_alpha = min(severity * 2.5, 1.0)

    def _update_nodes(self, scenario: int, period: int) -> None:
        agg: dict[str, list] = {}
        for nt in self._source.node_throughput(scenario, period):
            a = agg.setdefault(nt.group, [0.0, True])
            a[0] += nt.quantity
            a[1] = a[1] and nt.active

        nodes: list[dict] = []
        for group, (ax, ay) in L.GROUP_ANCHORS.items():
            if group not in agg:
                continue
            qty, active = agg[group]
            # Pin-scale discs: a tight range so the map reads as pins, not
            # bubbles. Quantity nudges the radius; it never dominates the map.
            scale = min(math.sqrt(max(qty, 0)) / 50.0, 1.0)
            r = 0.0135 + 0.009 * scale
            nodes.append({
                "group": group,
                "cx": ax / L.CANVAS_W,
                "cy": ay / L.CANVAS_H,
                "color": _GROUP_COLORS.get(group, "#888888"),
                "icon": _ICON_URLS.get(group, ""),
                "active": bool(active),
                "opacity": 1.0 if active else 0.4,
                "r": r,
            })
        self._nodes = nodes

        # Ranked bar-list: normalize each group's throughput against the
        # current-period max so the longest bar reads as 1.0.
        max_qty = max((v[0] for v in agg.values()), default=0.0)
        bars: list[dict] = []
        for group, (qty, active) in agg.items():
            bars.append({
                "label": _GROUP_LABELS.get(group, group),
                "color": _GROUP_COLORS.get(group, "#888888"),
                "frac": (qty / max_qty) if max_qty > 0 else 0.0,
                "active": bool(active),
            })
        bars.sort(key=lambda b: b["frac"], reverse=True)
        self._node_bars = bars

    def _tick(self) -> None:
        if not self._periods:
            return
        nxt = self._period_index + 1
        if nxt > self.periodMax:
            nxt = 0
        self.setPeriodIndex(nxt)
