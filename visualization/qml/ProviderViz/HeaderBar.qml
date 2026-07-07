import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ProviderViz 1.0

/*! Floating header over the full-bleed map: greeting/status at left, scenario
    segmented tabs in the centre, filter/reload pills at right. */
GlassPanel {
    id: root

    RowLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: root.padding
        anchors.rightMargin: root.padding
        spacing: 16

        // -- greeting + status ------------------------------------------------
        Column {
            spacing: 1
            Layout.alignment: Qt.AlignVCenter
            Text {
                text: "PROVIDER Supply Chain HQ"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 15
                font.weight: Font.DemiBold
                font.letterSpacing: 0.3
            }
            Text {
                text: app.hasData ? app.periodLabel : "no run loaded"
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: 11
                font.letterSpacing: 0.3
            }
        }

        LivePulse { Layout.alignment: Qt.AlignVCenter }

        Item { Layout.fillWidth: true }

        // -- scenario segmented tabs -----------------------------------------
        SegmentedTabs {
            Layout.alignment: Qt.AlignVCenter
            model: app.scenarioLabels
            currentIndex: app.scenarioIndex
            enabled: app.hasData
            onActivated: (index) => app.setScenarioIndex(index)
        }

        Item { Layout.fillWidth: true }

        // -- right-side pills -------------------------------------------------
        RowLayout {
            spacing: 8
            Layout.alignment: Qt.AlignVCenter

            PillButton {
                text: "Heatmap"
                primary: app.heatmapVisible
                enabled: app.hasData
                onClicked: app.setHeatmapVisible(!app.heatmapVisible)
            }
            PillButton {
                text: "Reload"
                enabled: !runner.running
                onClicked: runner.reloadOutput()
            }
            PillButton {
                text: "Export"
                enabled: false   // placeholder — wired in a later phase
            }
        }
    }
}
