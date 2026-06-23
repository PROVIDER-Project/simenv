"""Animated ship markers drifting along the export corridors.

A ShipController owns a small pool of arrow markers per corridor and advances
them along the route QPainterPath on a continuous timer. The number of visible
ships per corridor scales with that corridor's current volume (set each period
by the map view). Motion is decorative — it conveys "goods are moving", not a
literal ship count.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, QTimer
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsPolygonItem, QGraphicsScene

_SHIP_COLOR = QColor("#eaf1f7")
_SHIP_EDGE = QColor("#33506b")
_MAX_SHIPS = 7            # pool size per corridor
_REF_VOLUME = 1000.0      # volume mapping to ~ a full pool
_FRAME_MS = 33            # ~30 fps
_SPEED = 0.04             # path-fraction per second (slow drift)


def _build_path(points: list[tuple[float, float]]) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for x, y in points[1:]:
        path.lineTo(QPointF(x, y))
    return path


class ShipItem(QGraphicsPolygonItem):
    """A small arrow marker pointing along its direction of travel."""

    def __init__(self) -> None:
        poly = QPolygonF([
            QPointF(7, 0), QPointF(-5, -4), QPointF(-3, 0), QPointF(-5, 4),
        ])
        super().__init__(poly)
        self.setBrush(QBrush(_SHIP_COLOR))
        self.setPen(QPen(_SHIP_EDGE, 0.5))
        self.setZValue(7)
        self.setVisible(False)


class ShipController(QObject):
    """Manages ship pools for all corridors and animates them."""

    def __init__(self, scene: QGraphicsScene,
                 routes: dict[str, list[tuple[float, float]]],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._paths = {o: _build_path(pts) for o, pts in routes.items()}
        self._pools: dict[str, list[ShipItem]] = {}
        for origin in routes:
            pool = [ShipItem() for _ in range(_MAX_SHIPS)]
            for ship in pool:
                scene.addItem(ship)
            self._pools[origin] = pool
        self._counts = {o: 0 for o in routes}
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_volume(self, origin: str, volume: float) -> None:
        """Set how many ships are visible on a corridor, from its volume."""
        if origin not in self._counts:
            return
        if volume <= 0:
            self._counts[origin] = 0
        else:
            frac = min(volume / _REF_VOLUME, 1.0)
            self._counts[origin] = max(1, round(_MAX_SHIPS * frac))

    def _tick(self) -> None:
        self._phase = (self._phase + _SPEED * _FRAME_MS / 1000.0) % 1.0
        for origin, pool in self._pools.items():
            path = self._paths[origin]
            n = self._counts[origin]
            for i, ship in enumerate(pool):
                if i < n:
                    t = (self._phase + i / max(n, 1)) % 1.0
                    ship.setPos(path.pointAtPercent(t))
                    ship.setRotation(-path.angleAtPercent(t))
                    ship.setVisible(True)
                else:
                    ship.setVisible(False)
