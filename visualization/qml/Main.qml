import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ProviderViz 1.0

ApplicationWindow {
    id: window
    width: 1280
    height: 820
    visible: true
    title: "PROVIDER — Supply Chain HQ Map"
    color: Theme.surface

    Binding { target: Theme; property: "mode"; value: theme.mode }

    // Theme-switch crossfade: a neutral wash of the new surface color that
    // fades out over 200ms so the flip settles instead of snapping (DESIGN.md
    // motion: 200ms ease-out, no bounce).
    Rectangle {
        id: themeFade
        anchors.fill: parent
        z: 9999
        color: Theme.surface
        opacity: 0
        visible: opacity > 0.001
        NumberAnimation {
            id: themeFadeAnim
            target: themeFade
            property: "opacity"
            from: 0.5
            to: 0.0
            duration: 200
            easing.type: Easing.OutQuad
        }
        Connections {
            target: theme
            function onModeChanged() { themeFadeAnim.restart() }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        NavRail {
            id: navRail
            objectName: "navRail"
            Layout.fillHeight: true
            Layout.preferredWidth: 56
        }

        // Content area — full-bleed map with floating chrome z-stacked over it.
        Item {
            id: content
            Layout.fillWidth: true
            Layout.fillHeight: true

            // -- full-bleed map (z:0) -----------------------------------------
            MapView {
                anchors.fill: parent
                z: 0
            }

            // -- ranked node bar-list (top-left, under header) ----------------
            BarListPanel {
                z: 10
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.leftMargin: 14
                anchors.topMargin: 14 + 62 + 12
                width: 232
                height: 280
            }

            // -- bottom card row: coverage · donut · KPI tiles ----------------
            RowLayout {
                id: bottomRow
                z: 10
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: timelineDock.top
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                anchors.bottomMargin: 12
                height: 118
                spacing: 12

                CoverageCard {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                }
                DonutCard {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                }
                KpiTiles {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                }
            }

            // -- floating header (top, over the map) --------------------------
            HeaderBar {
                id: header
                z: 20
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 14
                height: 62
            }

            // -- timeline dock (bottom) ---------------------------------------
            TimelineDock {
                id: timelineDock
                z: 20
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 14
                height: 60
            }

            // -- nav-rail view overlays (runner / chart) ----------------------
            // Dimmed scrim (tap to return to the map view) + a centered panel.
            // The panel wrap holds a MouseArea under its content so taps on empty
            // panel area are swallowed rather than closing the overlay.

            // Runner view — PDL select · Run simulation · streaming log.
            Item {
                z: 40
                anchors.fill: parent
                visible: navRail.currentView === 2

                Rectangle {
                    anchors.fill: parent
                    color: Theme.isDark ? Qt.rgba(0, 0, 0, 0.5) : Qt.rgba(0.1, 0.09, 0.08, 0.32)
                    TapHandler { onTapped: navRail.currentView = 0 }
                }
                Item {
                    anchors.centerIn: parent
                    width: 560
                    height: 320
                    MouseArea { anchors.fill: parent }
                    RunnerDock { anchors.fill: parent }
                }
            }

            // Chart view — price over time (reuses the existing chart card).
            Item {
                z: 40
                anchors.fill: parent
                visible: navRail.currentView === 1

                Rectangle {
                    anchors.fill: parent
                    color: Theme.isDark ? Qt.rgba(0, 0, 0, 0.5) : Qt.rgba(0.1, 0.09, 0.08, 0.32)
                    TapHandler { onTapped: navRail.currentView = 0 }
                }
                Item {
                    anchors.centerIn: parent
                    width: 620
                    height: 178
                    MouseArea { anchors.fill: parent }
                    PriceChartCard { anchors.fill: parent }
                }
            }

            // -- empty state --------------------------------------------------
            Text {
                anchors.centerIn: parent
                visible: !app.hasData
                text: app.statusMessage
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: 14
                z: 100
            }
        }
    }
}
