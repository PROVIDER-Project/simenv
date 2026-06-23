"""Custom QGraphicsItems for the schematic map: nodes and flow corridors.

These items know nothing about data sources or CSVs — the map view feeds them
plain numbers (quantity, volume, active) pulled from the DataSource. Visual
encoding only lives here.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
)

# Per-group base color (category encoding). Quantity modulates radius, not hue.
GROUP_COLORS: dict[str, QColor] = {
    "BraFarmers": QColor("#2e9e5b"),
    "ArgFarmers": QColor("#4cae9e"),
    "UsaFarmers": QColor("#3b7dd8"),
    "EuFarmers": QColor("#b86fc6"),
    "Wholesalers": QColor("#e0a13b"),
    "Processors": QColor("#d9694f"),
    "FeedManufacturers": QColor("#c0563f"),
    "FeedTraders": QColor("#a8452f"),
}
_DEFAULT_COLOR = QColor("#888888")
_INACTIVE_COLOR = QColor("#5a5a5a")

# Node radius scaling: area ~ quantity, so radius ~ sqrt(quantity), clamped.
# Tuned for aggregated per-group totals (sums of all agents in a component),
# which range ~600..2300 in the current data.
_R_MIN = 8.0
_R_MAX = 30.0
_R_SCALE = 0.6          # radius per sqrt(quantity)

# Flow line width scaling against a reference volume.
_W_MIN = 1.0
_W_MAX = 14.0
FLOW_REF_VOLUME = 1000.0  # ~ baseline BRA volume; widths are relative to this


def radius_for_quantity(quantity: float) -> float:
    r = _R_SCALE * math.sqrt(max(quantity, 0.0))
    return max(_R_MIN, min(_R_MAX, r))


def width_for_volume(volume: float, ref: float = FLOW_REF_VOLUME) -> float:
    if ref <= 0:
        return _W_MIN
    w = _W_MAX * (volume / ref)
    return max(_W_MIN, min(_W_MAX, w))


class NodeItem(QGraphicsEllipseItem):
    """One agent on the map. Radius encodes quantity; gray when inactive."""

    def __init__(self, group: str, node_id: int, x: float, y: float) -> None:
        super().__init__()
        self._group = group
        self._node_id = node_id
        self._cx = x
        self._cy = y
        self._base_color = GROUP_COLORS.get(group, _DEFAULT_COLOR)
        self.setPen(QPen(QColor("#0e1b26"), 1.0))
        self.setZValue(10)

        # Soft drop shadow lifts the node off the map for a sense of volume.
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(1.5, 2.5)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.setGraphicsEffect(shadow)

        self.set_state(quantity=0.0, unit_price=None, active=True)

    def set_state(self, quantity: float, unit_price: float | None, active: bool) -> None:
        """Update radius/color/tooltip from this period's values."""
        r = radius_for_quantity(quantity)
        # Re-center the ellipse on (cx, cy) as the radius changes.
        self.setRect(self._cx - r, self._cy - r, 2 * r, 2 * r)
        color = self._base_color if active else _INACTIVE_COLOR
        # Radial gradient (highlight -> base -> dark rim) reads as a 3D sphere.
        grad = QRadialGradient(self._cx - r * 0.35, self._cy - r * 0.4, r * 1.5)
        grad.setColorAt(0.0, color.lighter(165))
        grad.setColorAt(0.45, color)
        grad.setColorAt(1.0, color.darker(175))
        self.setBrush(QBrush(grad))
        self.setOpacity(1.0 if active else 0.45)
        price_txt = "—" if unit_price is None else f"{unit_price:,.1f}"
        self.setToolTip(
            f"{self._group} #{self._node_id}\n"
            f"quantity: {quantity:,.1f}\n"
            f"price: {price_txt}\n"
            f"active: {active}"
        )


class FlowItem(QGraphicsPathItem):
    """A corridor (BRA/ARG/USA -> EU). Pen width/opacity encode volume."""

    def __init__(self, origin: str, points: list[tuple[float, float]]) -> None:
        super().__init__()
        self._origin = origin
        path = QPainterPath(QPointF(*points[0]))
        for x, y in points[1:]:
            path.lineTo(QPointF(x, y))
        self.setPath(path)
        self.setZValue(5)
        self.set_magnitude(0.0)

    def set_magnitude(self, volume: float, ref: float = FLOW_REF_VOLUME) -> None:
        w = width_for_volume(volume, ref)
        color = QColor("#cfd8e3")
        # Heavier flow -> more opaque line.
        color.setAlphaF(0.25 + 0.65 * min(volume / ref, 1.0) if ref > 0 else 0.5)
        pen = QPen(color, w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)
        self.setToolTip(f"{self._origin} → EU corridor\nvolume: {volume:,.1f}")
