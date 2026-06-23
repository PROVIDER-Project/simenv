"""TimelineBar — playback controls for stepping through periods.

A self-contained widget: play/pause, step back/forward, a seek slider, and a
speed selector. It owns a QTimer and emits indexChanged(int) whenever the
current period index changes (whether from the timer, the slider, or a step).
The main window connects indexChanged to refresh the map/HUD.

The slider is the single source of truth for the current index — the timer and
step buttons just move the slider, so every change funnels through one signal.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)

# Playback speed -> timer interval (ms per period). 1x ~ 8 periods/second.
_SPEEDS = [("0.5×", 240), ("1×", 120), ("2×", 60), ("4×", 30)]
_DEFAULT_SPEED_INDEX = 1


class TimelineBar(QWidget):
    indexChanged = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._index = 0
        self._last_period = 0
        self._periods: list[int] = []

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._play = QPushButton("▶ Play")
        self._play.setCheckable(True)
        self._step_back = QPushButton("‹")
        self._step_fwd = QPushButton("›")
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setEnabled(False)
        self._label = QLabel("period —")
        self._speed = QComboBox()
        for name, _ in _SPEEDS:
            self._speed.addItem(name)
        self._speed.setCurrentIndex(_DEFAULT_SPEED_INDEX)

        self._build_ui()

        self._play.toggled.connect(self._on_play_toggled)
        self._step_back.clicked.connect(lambda: self._step(-1))
        self._step_fwd.clicked.connect(lambda: self._step(+1))
        self._slider.valueChanged.connect(self._on_slider)
        self._speed.currentIndexChanged.connect(self._apply_speed)

    def _build_ui(self) -> None:
        for btn in (self._play, self._step_back, self._step_fwd):
            btn.setFixedHeight(30)
        self._step_back.setFixedWidth(34)
        self._step_fwd.setFixedWidth(34)
        self._play.setFixedWidth(90)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self._play)
        row.addWidget(self._step_back)
        row.addWidget(self._step_fwd)
        row.addWidget(self._slider, stretch=1)
        row.addWidget(self._label)
        row.addWidget(QLabel("speed"))
        row.addWidget(self._speed)
        self.setLayout(row)

    # -- public API --------------------------------------------------------

    def set_periods(self, periods: list[int]) -> None:
        """Configure the slider for a new scenario's period list and reset to 0."""
        self.pause()
        self._periods = periods
        enabled = len(periods) > 1
        self._slider.blockSignals(True)
        self._slider.setMinimum(0)
        self._slider.setMaximum(max(len(periods) - 1, 0))
        self._slider.setValue(0)
        self._slider.setEnabled(enabled)
        self._slider.blockSignals(False)
        self._last_period = periods[-1] if periods else 0
        self._index = 0
        self._update_label()
        self.indexChanged.emit(0)

    def pause(self) -> None:
        if self._play.isChecked():
            self._play.setChecked(False)  # triggers _on_play_toggled

    # -- internals ---------------------------------------------------------

    def _on_play_toggled(self, playing: bool) -> None:
        self._play.setText("⏸ Pause" if playing else "▶ Play")
        if playing:
            self._apply_speed()
            self._timer.start()
        else:
            self._timer.stop()

    def _apply_speed(self) -> None:
        _, interval = _SPEEDS[self._speed.currentIndex()]
        self._timer.setInterval(interval)

    def _tick(self) -> None:
        if not self._periods:
            return
        nxt = self._index + 1
        if nxt > self._slider.maximum():
            nxt = 0  # loop
        self._slider.setValue(nxt)  # funnels through _on_slider

    def _step(self, delta: int) -> None:
        self.pause()
        self._slider.setValue(
            max(0, min(self._slider.maximum(), self._index + delta))
        )

    def _on_slider(self, value: int) -> None:
        self._index = value
        self._update_label()
        self.indexChanged.emit(value)

    def _update_label(self) -> None:
        if not self._periods:
            self._label.setText("period —")
            return
        self._label.setText(f"period {self._periods[self._index]} / {self._last_period}")
