import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ProviderViz 1.0

GlassPanel {
    id: root
    implicitHeight: 220

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.padding
        spacing: Theme.spaceUnit

        Text {
            text: "RUN SIMULATION"
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: 10
            font.weight: Font.Medium
            font.letterSpacing: 1.1
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceUnit

            Text {
                text: "PDL"
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: 11
                font.letterSpacing: 0.5
                Layout.preferredWidth: 28
            }
            StyledComboBox {
                Layout.fillWidth: true
                model: runner.pdlLabels
                currentIndex: runner.pdlIndex
                onActivated: (index) => runner.setPdlIndex(index)
            }
            PillButton {
                primary: true
                text: runner.running ? "Running…" : "Run simulation"
                enabled: !runner.running
                onClicked: runner.runSimulation()
            }
            PillButton {
                text: "Reload output"
                onClicked: runner.reloadOutput()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 84
            radius: Theme.radiusInner
            color: Theme.isDark ? Qt.darker(Theme.surface, 1.12) : Theme.surface
            border.color: Theme.border
            border.width: 1

            ScrollView {
                anchors.fill: parent
                anchors.margins: 10
                clip: true
                Text {
                    width: parent.width
                    text: runner.logText.length ? runner.logText : "Simulation log…"
                    color: runner.logText.length ? Theme.text : Theme.textMuted
                    font.family: Theme.monoFamily
                    font.pixelSize: 11
                    lineHeight: 1.25
                    wrapMode: Text.Wrap
                }
            }
        }
    }
}
