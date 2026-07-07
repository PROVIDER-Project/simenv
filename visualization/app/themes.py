"""Theme tokens, QSS, and QSettings persistence for the visualizer.

Light mode is the default. Tokens match visualization/DESIGN.md.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor

_SETTINGS_ORG = "OFFIS"
_SETTINGS_APP = "PROVIDER-Visualizer"
_KEY_THEME = "theme"


@dataclass(frozen=True)
class MapPalette:
    ocean: str
    land: str
    land_border: str
    label: str
    port_export: str
    port_import: str
    port_label: str
    note: str
    node_ring: str

    def qcolor(self, key: str) -> QColor:
        return QColor(getattr(self, key))


@dataclass(frozen=True)
class ChartPalette:
    background: str
    axes_bg: str
    soja: str
    feed: str
    muted: str
    playhead: str
    grid: str
    spine: str


@dataclass(frozen=True)
class Theme:
    key: str
    display_name: str
    surface: str
    surface_raised: str
    border: str
    border_subtle: str
    text: str
    text_muted: str
    accent_soja: str
    accent_feed: str
    glass_fill: str
    glass_overlay: str
    glass_border: str
    glass_highlight: str
    glass_shadow: str
    map: MapPalette
    chart: ChartPalette

    def qss(self) -> str:
        """Application-wide Qt stylesheet."""
        t, m, s, b, br, sr = (
            self.text,
            self.text_muted,
            self.surface,
            self.border,
            self.border_subtle,
            self.surface_raised,
        )
        soja, feed = self.accent_soja, self.accent_feed
        return f"""
QMainWindow {{
    background: {s};
    color: {t};
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 13px;
}}
QWidget#appCanvas {{
    background: {s};
}}
QWidget {{
    background: transparent;
    color: {t};
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 13px;
}}
QLabel {{
    color: {m};
    background: transparent;
}}
QLabel#title {{
    color: {t};
    font-size: 15px;
    font-weight: 600;
}}
QLabel#status {{
    color: {m};
    font-size: 12px;
    font-variant-numeric: tabular-nums;
}}
QLabel#mutedCap {{
    color: {m};
    font-size: 11px;
}}
QLabel#periodLabel {{
    color: {m};
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    min-width: 108px;
}}
QPushButton#transportBtn {{
    min-width: 40px;
    max-width: 40px;
    min-height: 40px;
    max-height: 40px;
    padding: 0;
    font-size: 17px;
}}
QPushButton#transportPlay {{
    min-width: 72px;
    max-width: 72px;
    min-height: 40px;
    max-height: 40px;
    padding: 0;
    font-size: 14px;
    font-weight: 600;
}}
QComboBox {{
    background: {sr};
    border: 1px solid {b};
    border-radius: 6px;
    padding: 5px 10px;
    min-width: 120px;
    color: {t};
}}
QComboBox::drop-down {{
    border: 0;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {sr};
    color: {t};
    selection-background-color: {b};
    border: 1px solid {b};
}}
QCheckBox {{
    color: {m};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {b};
    background: {sr};
}}
QCheckBox::indicator:checked {{
    background: {soja};
    border-color: {soja};
}}
QPushButton {{
    background: {sr};
    border: 1px solid {b};
    border-radius: 6px;
    padding: 6px 12px;
    color: {t};
    min-height: 20px;
}}
QPushButton:hover {{
    border-color: {br};
}}
QPushButton:pressed {{
    background: {b};
}}
QPushButton#themeToggle {{
    min-width: 36px;
    max-width: 36px;
    padding: 6px 0;
    font-size: 15px;
}}
QPushButton:disabled {{
    color: {m};
    background: {s};
}}
QSlider::groove:horizontal {{
    height: 5px;
    background: {b};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {soja};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {t};
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
    border: 1px solid {b};
}}
QPlainTextEdit {{
    background: {sr};
    border: 1px solid {b};
    border-radius: 8px;
    color: {t};
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px;
    padding: 8px;
}}
QSplitter::handle {{
    background: {b};
    width: 1px;
}}
"""


LIGHT = Theme(
    key="light",
    display_name="Light",
    surface="#F4F2EE",
    surface_raised="#FAF9F7",
    border="#D5D0C8",
    border_subtle="#E8E4DE",
    text="#1A1816",
    text_muted="#6B6560",
    accent_soja="#B8720E",
    accent_feed="#A85A48",
    glass_fill="#FFFFFF",
    glass_overlay="rgba(255, 255, 255, 0.82)",
    glass_border="#D0CAC2",
    glass_highlight="rgba(255, 255, 255, 0.95)",
    glass_shadow="0 2px 12px rgba(26, 24, 22, 0.08)",
    map=MapPalette(
        ocean="#B8CED8",
        land="#DDD8CF",
        land_border="#C4BDB4",
        label="#4A4540",
        port_export="#9A7B2E",
        port_import="#4A7A9A",
        port_label="#5C5650",
        note="#8A847C",
        node_ring="#A8A29A",
    ),
    chart=ChartPalette(
        background="#F4F2EE",
        axes_bg="#FAF9F7",
        soja="#B8720E",
        feed="#A85A48",
        muted="#6B6560",
        playhead="#1A1816",
        grid="#E8E4DE",
        spine="#D5D0C8",
    ),
)

DARK = Theme(
    key="dark",
    display_name="Dark",
    surface="#14161A",
    surface_raised="#1C1F24",
    border="#2E3339",
    border_subtle="#252830",
    text="#E6E4E0",
    text_muted="#8A8680",
    accent_soja="#E0A84A",
    accent_feed="#D47862",
    glass_fill="#2A3139",
    glass_overlay="rgba(30, 36, 44, 0.82)",
    glass_border="#3E4854",
    glass_highlight="rgba(255, 255, 255, 0.14)",
    glass_shadow="0 4px 20px rgba(0, 0, 0, 0.35)",
    map=MapPalette(
        ocean="#1E2A32",
        land="#2C3840",
        land_border="#3D4F5A",
        label="#9AA5AD",
        port_export="#D4BC6A",
        port_import="#7EB8D4",
        port_label="#8A8680",
        note="#6B7280",
        node_ring="#0E1418",
    ),
    chart=ChartPalette(
        background="#14161A",
        axes_bg="#1C1F24",
        soja="#E0A84A",
        feed="#D47862",
        muted="#8A8680",
        playhead="#E6E4E0",
        grid="#252830",
        spine="#2E3339",
    ),
)

_THEMES: dict[str, Theme] = {LIGHT.key: LIGHT, DARK.key: DARK}


def theme_for_key(key: str) -> Theme:
    return _THEMES.get(key, LIGHT)


def load_theme_key() -> str:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    key = str(settings.value(_KEY_THEME, LIGHT.key))
    return key if key in _THEMES else LIGHT.key


def save_theme_key(key: str) -> None:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue(_KEY_THEME, key)


def toggle_theme_key(current: str) -> str:
    return DARK.key if current == LIGHT.key else LIGHT.key
