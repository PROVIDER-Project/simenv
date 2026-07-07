"""Map geometry + ship animation for QML MapView."""
from __future__ import annotations

import math

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from ..config import layout as L

_MAX_SHIPS = 6
_REF_VOLUME = 1000.0
_FRAME_MS = 33
_SPEED = 0.035
_W = L.CANVAS_W
_H = L.CANVAS_H


def _norm(x: float, y: float) -> dict[str, float]:
    return {"x": x / _W, "y": y / _H}


def _point_at_percent(
    points: list[tuple[float, float]], t: float,
) -> tuple[float, float, float]:
    if len(points) < 2:
        p = points[0] if points else (0.0, 0.0)
        return p[0], p[1], 0.0
    seg_lens: list[float] = []
    total = 0.0
    for i in range(len(points) - 1):
        dx = points[i + 1][0] - points[i][0]
        dy = points[i + 1][1] - points[i][1]
        ln = math.hypot(dx, dy)
        seg_lens.append(ln)
        total += ln
    if total <= 0:
        return points[0][0], points[0][1], 0.0
    dist = t * total
    for i, ln in enumerate(seg_lens):
        if dist <= ln or i == len(seg_lens) - 1:
            f = dist / ln if ln > 0 else 0.0
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            x = x0 + f * (x1 - x0)
            y = y0 + f * (y1 - y0)
            angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
            return x, y, angle
        dist -= ln
    p = points[-1]
    return p[0], p[1], 0.0


class MapController(QObject):
    shipsChanged = Signal()
    zoomChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._country_labels = [
            {
                "display": str(e["display"]),
                "x": float(e["x"]) / _W,
                "y": float(e["y"]) / _H,
                "tier": int(e["tier"]),
                "area": float(e["area"]),
            }
            for e in L.COUNTRY_LABELS
        ]
        self._ports = [
            {"name": name, "role": role, **_norm(x, y)}
            for name, (x, y, role) in L.PORTS.items()
        ]
        self._route_xy = {
            origin: [(x / _W, y / _H) for x, y in pts]
            for origin, pts in L.ROUTES.items()
        }

        self._zoom = 1.0
        self._visible_labels: list[dict] = []
        self._ship_counts = {o: 0 for o in self._route_xy}
        self._ships: list[dict] = []
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._tick_ships)
        self._timer.start()

        self._rebuild_visible_labels()

    # -- properties (small payloads only) ----------------------------------

    @Property(float, constant=True)
    def canvasW(self) -> float:
        return float(_W)

    @Property(float, constant=True)
    def canvasH(self) -> float:
        return float(_H)

    @Property(float, constant=True)
    def aspectRatio(self) -> float:
        return _H / _W

    @Property(str, constant=True)
    def geoNote(self) -> str:
        return L.GEO_NOTE

    @Property(str, constant=True)
    def landImageLight(self) -> str:
        return "image://providermap/land/light"

    @Property(str, constant=True)
    def landImageDark(self) -> str:
        return "image://providermap/land/dark"

    @Property(str, constant=True)
    def heatMaskLight(self) -> str:
        return "image://providermap/heat/light"

    @Property(str, constant=True)
    def heatMaskDark(self) -> str:
        return "image://providermap/heat/dark"

    @Property(list, constant=True)
    def ports(self) -> list:
        return self._ports

    @Property(list, notify=shipsChanged)
    def ships(self) -> list:
        return self._ships

    @Property(list, constant=True)
    def routePaths(self) -> list:
        """Static corridor polylines (normalized 0..1) for the QML flow layer.
        Constant so the Shape geometry is built once — load/opacity is driven
        separately by `corridorLoads` (which changes only on period change)."""
        return [
            {"origin": origin, "points": [{"x": x, "y": y} for x, y in pts]}
            for origin, pts in self._route_xy.items()
        ]

    @Property("QVariantMap", notify=shipsChanged)
    def corridorLoads(self) -> dict:
        """origin -> current ship count. Drives corridor opacity / flow density."""
        return {origin: self._ship_counts.get(origin, 0) for origin in self._route_xy}

    @Property(list, notify=zoomChanged)
    def visibleLabels(self) -> list:
        return self._visible_labels

    @Property(float, notify=zoomChanged)
    def zoom(self) -> float:
        return self._zoom

    # -- slots -------------------------------------------------------------

    @Slot(float)
    def setZoom(self, zoom: float) -> None:
        zoom = max(1.0, min(zoom, 8.0))
        if abs(zoom - self._zoom) < 1e-3:
            return
        self._zoom = zoom
        self._rebuild_visible_labels()
        self.zoomChanged.emit()

    @Slot(float, float, float)
    def setShipVolumes(self, bra: float, arg: float, usa: float) -> None:
        for origin, vol in (("BRA", bra), ("ARG", arg), ("USA", usa)):
            if vol <= 0:
                self._ship_counts[origin] = 0
            else:
                frac = min(vol / _REF_VOLUME, 1.0)
                self._ship_counts[origin] = max(1, round(_MAX_SHIPS * frac))
        self._tick_ships()

    # -- internals ---------------------------------------------------------

    def _max_tier(self) -> int:
        if self._zoom < 1.3:
            return 1
        if self._zoom < 2.0:
            return 2
        return 3

    def _max_labels(self) -> int:
        # Whisper density: only a handful of anchor countries at the fitted
        # view; reveal more as the researcher zooms into a region.
        if self._zoom < 1.3:
            return 16
        if self._zoom < 2.0:
            return 40
        return 10_000

    @staticmethod
    def _label_bounds(cx: float, cy: float, text: str) -> tuple[float, float, float, float]:
        w = max(28.0, len(text) * 5.5) / _W
        h = 12.0 / _H
        return (cx - w / 2, cy - h / 2, w, h)

    @staticmethod
    def _bounds_overlap(
        a: tuple[float, float, float, float],
        b: tuple[float, float, float, float],
        *,
        pad: float = 3.0,
    ) -> bool:
        pad_x = pad / _W
        pad_y = pad / _H
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return (
            ax < bx + bw + pad_x and ax + aw + pad_x > bx
            and ay < by + bh + pad_y and ay + ah + pad_y > by
        )

    def _rebuild_visible_labels(self) -> None:
        max_tier = self._max_tier()
        candidates = [
            e for e in self._country_labels if int(e["tier"]) <= max_tier
        ]
        candidates.sort(key=lambda e: (int(e["tier"]), -float(e["area"])))

        max_labels = self._max_labels()
        placed: list[tuple[float, float, float, float]] = []
        visible: list[dict] = []
        for entry in candidates:
            if len(visible) >= max_labels:
                break
            text = str(entry["display"])
            bounds = self._label_bounds(float(entry["x"]), float(entry["y"]), text)
            if any(self._bounds_overlap(bounds, other) for other in placed):
                continue
            visible.append(entry)
            placed.append(bounds)
        self._visible_labels = visible

    def _tick_ships(self) -> None:
        self._phase = (self._phase + _SPEED * _FRAME_MS / 1000.0) % 1.0
        ships: list[dict] = []
        for origin, pool_n in self._ship_counts.items():
            pts = self._route_xy.get(origin, [])
            if not pts:
                continue
            for i in range(_MAX_SHIPS):
                if i < pool_n:
                    t = (self._phase + i / max(pool_n, 1)) % 1.0
                    nx, ny, angle = _point_at_percent(pts, t)
                    ships.append({
                        "nx": nx, "ny": ny,
                        "angle": angle, "visible": True,
                    })
                else:
                    ships.append({"nx": 0.0, "ny": 0.0, "angle": 0.0, "visible": False})
        self._ships = ships
        self.shipsChanged.emit()
