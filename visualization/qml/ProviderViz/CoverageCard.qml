import QtQuick
import QtQuick.Layouts
import ProviderViz 1.0

/*! Corridor coverage (CRM-map "Markets coverage" analogue): three vertical
    mini-bars for the BRA / ARG / USA export volumes, normalized 0–1. */
GlassPanel {
    id: root

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.padding
        spacing: 6

        Text {
            text: "CORRIDOR COVERAGE"
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: 10
            font.weight: Font.Medium
            font.letterSpacing: 1.1
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 18

            Repeater {
                model: app.coverageBars
                delegate: ColumnLayout {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    spacing: 5

                    // Vertical track + fill (grows from the bottom).
                    Item {
                        Layout.fillHeight: true
                        Layout.fillWidth: true

                        Rectangle {
                            id: track
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            width: 10
                            radius: 5
                            color: Theme.isDark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0.1, 0.09, 0.08, 0.07)

                            Rectangle {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                height: parent.height * Math.max(0, Math.min(modelData.frac, 1))
                                radius: 5
                                color: modelData.color
                                Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.OutQuad } }
                            }
                        }
                    }

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: modelData.label
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: 11
                        font.weight: Font.Medium
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: Math.round(modelData.frac * 100) + "%"
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 10
                        font.hintingPreference: Font.PreferNoHinting
                    }
                }
            }
        }
    }
}
