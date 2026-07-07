"""Theme persistence for QML — syncs with Theme.qml singleton."""
from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot

from ..app.themes import load_theme_key, save_theme_key, toggle_theme_key


class ThemeBridge(QObject):
    modeChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._mode = load_theme_key()

    @Property(str, notify=modeChanged)
    def mode(self) -> str:
        return self._mode

    @Slot()
    def toggle(self) -> None:
        self._mode = toggle_theme_key(self._mode)
        save_theme_key(self._mode)
        self.modeChanged.emit()
