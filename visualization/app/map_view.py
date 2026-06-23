"""MapView — the QGraphicsView/Scene that renders the geographic map.

Builds the static backdrop once (ocean, coastlines, ports, route corridors,
labels), then show_period(scenario, period) pulls fresh values from the
DataSource and updates node sizes/colors and flow widths. The view depends only
on the DataSource Protocol and the layout config — never on pandas/CSV.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from ..config import layout as L
from ..data.source import DataSource
from .hud import HudPanel
from .nodes import NodeItem
from .ships import ShipController

# Backdrop palette (modern flat-map, dark theme).
_OCEAN = QColor("#0b1f33")
_LAND = QColor("#23384c")
_LAND_BORDER = QColor("#33506b")
_PORT_EXPORT = QColor("#f0e68c")
_PORT_IMPORT = QColor("#9ad0ff")
_LABEL = QColor("#e6edf3")
_PORT_LABEL = QColor("#aeb9c2")
_NOTE = QColor("#7a8a96")

# Friendly display names for group labels.
_GROUP_LABELS = {
    "UsaFarmers": "USA farms",
    "BraFarmers": "BRA farms",
    "ArgFarmers": "ARG farms",
    "Wholesalers": "Wholesalers / market",
    "Processors": "Processors",
    "FeedManufacturers": "Feed mfrs",
    "FeedTraders": "Feed traders",
    "EuFarmers": "EU livestock",
}


class MapView(QGraphicsView):
    def __init__(self, source: DataSource) -> None:
        super().__init__()
        self._source = source
        self._scene = QGraphicsScene(0, 0, L.CANVAS_W, L.CANVAS_H)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(_OCEAN))
        self.setMinimumSize(700, 440)

        # Wheel zoom (fit .. 8x), anchored under the cursor; hand-drag to pan
        # once zoomed in. Scrollbars stay hidden for a clean look.
        self._zoom = 1.0
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # One representative node per group (group name -> item). The CSV still
        # holds N agents per group; the view aggregates them into a single node
        # (per the "1 node per component" decision).
        self._nodes: dict[str, NodeItem] = {}
        self._scenario: int | None = None

        self._build_backdrop()

        # Drought heatmap layer: source-region polygons tinted by drought.
        self._heat_items: list[QGraphicsPolygonItem] = []
        self._heat_visible = True
        self._last_drought = 0.0
        self._build_heatmap()

        # Route lines are intentionally NOT drawn — only the animated ships
        # convey the corridors (and they stay over open ocean).
        self._ships = ShipController(self._scene, L.ROUTES, self)

        # HUD is a screen-space overlay (child widget), not a scene item, so it
        # stays crisp and fixed in the corner regardless of map zoom/pan.
        self._hud = HudPanel(self)
        self._hud.move(12, 12)
        self._hud.show()

    # -- static backdrop ---------------------------------------------------

    def _build_backdrop(self) -> None:
        self._scene.setBackgroundBrush(QBrush(_OCEAN))
        land_pen = QPen(_LAND_BORDER, 0.4)
        land_brush = QBrush(_LAND)
        for ring in L.COUNTRY_POLYGONS:
            poly = QGraphicsPolygonItem(QPolygonF([QPointF(x, y) for x, y in ring]))
            poly.setBrush(land_brush)
            poly.setPen(land_pen)
            poly.setZValue(0)
            self._scene.addItem(poly)

        # Port waypoint markers (diamonds) + labels.
        for name, (x, y, role) in L.PORTS.items():
            color = _PORT_EXPORT if role == "export" else _PORT_IMPORT
            d = 5.0
            diamond = QGraphicsPolygonItem(
                QPolygonF([QPointF(x, y - d), QPointF(x + d, y),
                           QPointF(x, y + d), QPointF(x - d, y)])
            )
            diamond.setBrush(QBrush(color))
            diamond.setPen(QPen(QColor("#1b1b1b"), 1.0))
            diamond.setZValue(8)
            diamond.setToolTip(f"{name} (waypoint, {role})")
            self._scene.addItem(diamond)
            self._add_label(name, x + 7, y - 7, _PORT_LABEL, 7)

        # GEO honesty note, bottom-left.
        note = self._add_label(L.GEO_NOTE, 10, L.CANVAS_H - 20, _NOTE, 9)
        note.setZValue(30)

    def _build_heatmap(self) -> None:
        """Build (initially invisible) tint polygons over the soja-source regions."""
        for name in L.DROUGHT_REGIONS:
            for ring in L.COUNTRY_SHAPES.get(name, []):
                item = QGraphicsPolygonItem(QPolygonF([QPointF(x, y) for x, y in ring]))
                item.setPen(QPen(Qt.PenStyle.NoPen))
                item.setBrush(QBrush(QColor(0, 0, 0, 0)))
                item.setZValue(1)  # above land (0), below ships (7) / nodes (10)
                self._scene.addItem(item)
                self._heat_items.append(item)

    def _apply_heat(self) -> None:
        # drought_severity tops out ~0.4 in the data; scale so it reads clearly.
        alpha = 0 if not self._heat_visible else min(int(self._last_drought * 420), 190)
        brush = QBrush(QColor(205, 64, 40, alpha))
        for item in self._heat_items:
            item.setBrush(brush)

    def set_heatmap_visible(self, visible: bool) -> None:
        self._heat_visible = visible
        self._apply_heat()

    def _add_label(self, text: str, x: float, y: float,
                   color: QColor, size: int) -> QGraphicsSimpleTextItem:
        item = QGraphicsSimpleTextItem(text)
        font = item.font()
        font.setPointSize(size)
        item.setFont(font)
        item.setBrush(QBrush(color))
        item.setPos(x, y)
        item.setZValue(20)
        self._scene.addItem(item)
        return item

    # -- per-scenario nodes ------------------------------------------------

    def set_scenario(self, scenario: int) -> None:
        """(Re)build one representative node per group for this scenario."""
        if scenario == self._scenario:
            return
        for item in self._nodes.values():
            self._scene.removeItem(item)
        self._nodes.clear()

        first_period = self._source.periods(scenario)[0]
        groups = {nt.group for nt in self._source.node_throughput(scenario, first_period)}

        for group in sorted(groups):
            anchor = L.GROUP_ANCHORS.get(group)
            if anchor is None:
                continue
            item = NodeItem(group, 0, anchor[0], anchor[1])
            self._scene.addItem(item)
            self._nodes[group] = item
            label = _GROUP_LABELS.get(group, group)
            self._add_label(label, anchor[0] - 34, anchor[1] - 38, _LABEL, 8)

        self._scenario = scenario

    # -- per-period update -------------------------------------------------

    def show_period(self, scenario: int, period: int) -> None:
        """Update node states and flow widths to one (scenario, period).

        Each group's agents are aggregated into its single node: quantity = sum
        (the component's total throughput), price = mean of the agents that have
        one, active = any agent active.
        """
        self.set_scenario(scenario)

        agg: dict[str, list] = {}  # group -> [qty_sum, [prices], any_active]
        for nt in self._source.node_throughput(scenario, period):
            a = agg.setdefault(nt.group, [0.0, [], False])
            a[0] += nt.quantity
            if nt.unit_price is not None:
                a[1].append(nt.unit_price)
            a[2] = a[2] or nt.active

        for group, item in self._nodes.items():
            qty, prices, active = agg.get(group, (0.0, [], True))
            price = sum(prices) / len(prices) if prices else None
            item.set_state(qty, price, active)

        env = self._source.environment_at(scenario, period)
        self._last_drought = env.drought_severity
        self._apply_heat()

        flows = self._source.origin_flows(scenario, period)
        self._ships.set_volume("BRA", flows.bra_volume)
        self._ships.set_volume("ARG", flows.arg_volume)
        self._ships.set_volume("USA", flows.usa_volume)

        self._hud.set_state(scenario, env)

    # -- keep the whole map visible on resize ------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        # Refit to the full map (resets zoom to the fitted baseline).
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = 1.0
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._hud.move(12, 12)
        self._hud.raise_()

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt override)
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = 1.2 if delta > 0 else 1 / 1.2
        target = max(1.0, min(self._zoom * step, 8.0))
        factor = target / self._zoom
        if abs(factor - 1.0) < 1e-3:
            return
        self.scale(factor, factor)
        self._zoom = target
        # Allow click-drag panning only once zoomed past the fitted view.
        self.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag if self._zoom > 1.0
            else QGraphicsView.DragMode.NoDrag
        )
