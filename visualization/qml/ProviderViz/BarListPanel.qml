import QtQuick
import QtQuick.Layouts
import ProviderViz 1.0

/*! Ranked supply-chain node bar-list (CRM-map "Core/Growth markets" analogue).
    One row per group: colored dot + label + thin throughput bar (frac, relative
    to the busiest node this period). Inactive groups dim to 40%. */
GlassPanel {
    id: root

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.padding
        spacing: 5

        Text {
            text: "SUPPLY-CHAIN NODES"
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: 10
            font.weight: Font.Medium
            font.letterSpacing: 1.1
            Layout.bottomMargin: 2
        }

        Repeater {
            model: app.nodeBars
            delegate: ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                opacity: modelData.active ? 1.0 : 0.4

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Rectangle {
                        width: 7; height: 7; radius: 3.5
                        color: modelData.color
                    }
                    Text {
                        text: modelData.label
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: 11
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Text {
                        text: Math.round(modelData.frac * 100) + "%"
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 10
                        font.hintingPreference: Font.PreferNoHinting
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    height: 4
                    radius: 2
                    color: Theme.isDark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0.1, 0.09, 0.08, 0.07)

                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(modelData.frac, 1))
                        height: parent.height
                        radius: 2
                        color: modelData.color
                        Behavior on width { NumberAnimation { duration: 150; easing.type: Easing.OutQuad } }
                    }
                }
            }
        }

        Item { Layout.fillHeight: true }
    }
}
