"""HudPanel — on-map heads-up panel for the current period's headline data.

A screen-space overlay QWidget (child of the map view), NOT a scene item: it
renders crisply at native resolution and stays fixed in the corner regardless of
map zoom/pan. The map view positions it and calls set_state each period.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel

from ..data.models import EnvState

_QSS = """
#hudPanel {
    background: rgba(13, 24, 35, 0.92);
    border: 1px solid #2a3b49;
    border-radius: 10px;
}
#hudPanel QLabel { background: transparent; }
#hudHeader, #hudSub, #hudCap { color: #9fb0bd; font-size: 11px; }
#hudCap { font-size: 10px; }
#sojaVal { color: #e7b15a; font-size: 22px; font-weight: 600; }
#feedVal { color: #e07a62; font-size: 22px; font-weight: 600; }
"""


class HudPanel(QFrame):
    """Translucent overlay: scenario/period + soja/feed prices + context."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("hudPanel")
        self.setStyleSheet(_QSS)
        self.setFixedWidth(236)

        self._header = QLabel("—")
        self._header.setObjectName("hudHeader")
        soja_cap = QLabel("soja price")
        soja_cap.setObjectName("hudCap")
        feed_cap = QLabel("feed price")
        feed_cap.setObjectName("hudCap")
        self._soja = QLabel("—")
        self._soja.setObjectName("sojaVal")
        self._feed = QLabel("—")
        self._feed.setObjectName("feedVal")
        self._sub = QLabel("")
        self._sub.setObjectName("hudSub")

        grid = QGridLayout()
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(2)
        grid.addWidget(self._header, 0, 0, 1, 2)
        grid.addWidget(soja_cap, 1, 0)
        grid.addWidget(feed_cap, 1, 1)
        grid.addWidget(self._soja, 2, 0)
        grid.addWidget(self._feed, 2, 1)
        grid.addWidget(self._sub, 3, 0, 1, 2)
        self.setLayout(grid)

    def set_state(self, scenario: int, env: EnvState) -> None:
        self._header.setText(f"Scenario {scenario}  ·  period {env.period}")
        self._soja.setText(f"{env.soja_price:,.1f}")
        self._feed.setText(f"{env.feed_price:,.1f}")
        self._sub.setText(
            f"shock {env.shock_scale:.2f}    drought {env.drought_severity:.2f}"
            f"    transport {env.transport_utilisation:.0%}"
        )
