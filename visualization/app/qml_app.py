"""Launch the QML visualizer with Python bridges."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine
from PySide6.QtQuickControls2 import QQuickStyle
# Qt Charts (the transport-utilisation donut) depends on QtWidgets, so the app
# must be a QApplication rather than a bare QGuiApplication.
from PySide6.QtWidgets import QApplication

from ..data.csv_source import CsvDataSource
from ..qml_bridge.app_controller import AppController
from ..qml_bridge.chart_controller import ChartController
from ..qml_bridge.map_controller import MapController
from ..qml_bridge.map_image_provider import MapImageProvider
from ..qml_bridge.runner_controller import RunnerController
from ..qml_bridge.theme_bridge import ThemeBridge

_QML_ROOT = Path(__file__).resolve().parent.parent / "qml"


def run_qml_app() -> None:
    # The Basic style is fully customizable; the native Windows style rejects
    # control background/contentItem overrides. Must be set before the engine.
    QQuickStyle.setStyle("Basic")
    app = QApplication(sys.argv)
    source = CsvDataSource()
    theme = ThemeBridge()
    chart = ChartController(source)
    map_ctrl = MapController()
    app_ctrl = AppController(source, chart, map_ctrl)
    runner = RunnerController()

    runner.outputReloaded.connect(app_ctrl.reload_data)
    # Live spine: a run generating data lights the header LIVE pulse. A future
    # streaming DataSource drives the same flag (and calls app_ctrl.append_period).
    runner.runningChanged.connect(lambda: app_ctrl.setLive(runner.running))

    engine = QQmlApplicationEngine()
    engine.addImageProvider("providermap", MapImageProvider())
    for bridge in (theme, app_ctrl, chart, runner, map_ctrl):
        bridge.setParent(engine)
        QQmlEngine.setObjectOwnership(bridge, QQmlEngine.CppOwnership)

    engine.addImportPath(str(_QML_ROOT))
    ctx = engine.rootContext()
    ctx.setContextProperty("theme", theme)
    ctx.setContextProperty("app", app_ctrl)
    ctx.setContextProperty("chart", chart)
    ctx.setContextProperty("runner", runner)
    ctx.setContextProperty("map", map_ctrl)

    def _on_warning(warning) -> None:
        print(warning, file=sys.stderr)

    engine.warnings.connect(_on_warning)
    engine.load(QUrl.fromLocalFile(str(_QML_ROOT / "Main.qml")))
    if not engine.rootObjects():
        print("Failed to load Main.qml", file=sys.stderr)
        sys.exit(1)
    sys.exit(app.exec())
