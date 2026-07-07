"""In-memory map tiles for QML Image — re-rasterizes at requested zoom resolution."""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from ..config import layout as L
from .map_raster import render_heat_mask, render_land_image

_W = L.CANVAS_W
_H = L.CANVAS_H
_MAX_CACHE = 20


class MapImageProvider(QQuickImageProvider):
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._cache: dict[str, QImage] = {}
        # Warm 1× tiles so first frame is instant.
        for mode in ("light", "dark"):
            self._store(f"land/{mode}@{_W}x{_H}", render_land_image(mode))
            self._store(f"heat/{mode}@{_W}x{_H}", render_heat_mask(mode))

    def _store(self, key: str, image: QImage) -> QImage:
        if len(self._cache) >= _MAX_CACHE:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = image
        return image

    def _dims(self, requested_size: QSize) -> tuple[int, int]:
        if requested_size.isValid() and requested_size.width() > 0:
            rw = int(requested_size.width())
            rh = int(requested_size.height()) if requested_size.height() > 0 else int(
                rw * _H / _W,
            )
            return rw, rh
        return _W, _H

    def requestImage(self, id: str, size, requested_size) -> QImage:  # noqa: N802
        rw, rh = self._dims(requested_size)
        key = f"{id}@{rw}x{rh}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        if id == "land/light":
            return self._store(key, render_land_image("light", pixel_w=rw, pixel_h=rh))
        if id == "land/dark":
            return self._store(key, render_land_image("dark", pixel_w=rw, pixel_h=rh))
        if id == "heat/light":
            return self._store(key, render_heat_mask("light", pixel_w=rw, pixel_h=rh))
        if id == "heat/dark":
            return self._store(key, render_heat_mask("dark", pixel_w=rw, pixel_h=rh))
        return QImage()
