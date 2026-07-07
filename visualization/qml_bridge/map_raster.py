"""Rasterize map polygons in Python — resolution scales with zoom for sharp coastlines."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygonF

from ..config import layout as L

_W = L.CANVAS_W
_H = L.CANVAS_H
_MAX_SCALE = 8

_PALETTES = {
    # Desaturated, reference-like neutrals: quiet light grey-neutral land with a
    # whisper coastline that barely separates from the fill (CRM-map v2).
    "light": {"land": "#D8D9D5", "coast": "#CCCDC9"},
    "dark": {"land": "#333E46", "coast": "#3C4850"},
}


def _clamp_dims(pixel_w: int, pixel_h: int) -> tuple[int, int]:
    rw = max(_W, min(int(pixel_w), _W * _MAX_SCALE))
    rh = max(_H, min(int(pixel_h), _H * _MAX_SCALE))
    return rw, rh


def _draw_rings(
    painter: QPainter,
    rings: list[list[tuple[float, float]]],
    *,
    fill: QColor,
    stroke: QColor | None = None,
    stroke_width: float = 0.5,
) -> None:
    painter.setBrush(QBrush(fill))
    if stroke is None:
        painter.setPen(Qt.PenStyle.NoPen)
    else:
        painter.setPen(QPen(stroke, stroke_width))
    for ring in rings:
        if len(ring) < 3:
            continue
        painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in ring]))


def render_land_image(
    mode: str,
    *,
    pixel_w: int = _W,
    pixel_h: int = _H,
) -> QImage:
    """Land + faint coastlines; raster at ``pixel_w`` × ``pixel_h`` for zoom sharpness."""
    rw, rh = _clamp_dims(pixel_w, pixel_h)
    pal = _PALETTES[mode]
    img = QImage(rw, rh, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    sx, sy = rw / _W, rh / _H
    painter.scale(sx, sy)
    land = QColor(pal["land"])
    land.setAlphaF(0.92)
    coast = QColor(pal["coast"])
    coast_alpha = 0.32 if max(sx, sy) >= 1.5 else 0.22
    coast.setAlphaF(coast_alpha)
    _draw_rings(
        painter,
        L.COUNTRY_POLYGONS,
        fill=land,
        stroke=coast,
        stroke_width=0.5,
    )
    painter.end()
    return img


def render_heat_mask(
    mode: str,
    *,
    pixel_w: int = _W,
    pixel_h: int = _H,
) -> QImage:
    """Drought-region fill on transparent — opacity driven in QML."""
    rw, rh = _clamp_dims(pixel_w, pixel_h)
    rings: list[list[tuple[float, float]]] = []
    for name in L.DROUGHT_REGIONS:
        rings.extend(L.COUNTRY_SHAPES.get(name, []))
    tint = QColor("#B44830" if mode == "light" else "#CD4028")
    tint.setAlpha(200)
    img = QImage(rw, rh, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(rw / _W, rh / _H)
    _draw_rings(painter, rings, fill=tint)
    painter.end()
    return img
