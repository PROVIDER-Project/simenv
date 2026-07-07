import QtQuick
import QtQuick.Layouts
import ProviderViz 1.0

/*! KPI tiles (CRM-map "Policy Watches" analogue): a 2×2 grid of value + label
    tiles with one accent per tile. Values come straight from the app bridge. */
GlassPanel {
    id: root

    component Tile: Column {
        property string label: ""
        property string value: "—"
        property color accent: Theme.accentSoja
        spacing: 3
        Text {
            text: label.toUpperCase()
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: 9
            font.weight: Font.Medium
            font.letterSpacing: 1.0
        }
        Text {
            text: value
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 17
            font.weight: Font.DemiBold
            font.hintingPreference: Font.PreferNoHinting
        }
        Rectangle { width: 18; height: 2; radius: 1; color: accent; opacity: 0.75 }
    }

    GridLayout {
        anchors.fill: parent
        anchors.margins: root.padding
        columns: 2
        columnSpacing: 20
        rowSpacing: 8

        Tile { Layout.fillWidth: true; label: "soja"; value: app.sojaText; accent: Theme.accentSoja }
        Tile { Layout.fillWidth: true; label: "feed"; value: app.feedText; accent: Theme.accentFeed }
        Tile { Layout.fillWidth: true; label: "drought"; value: app.droughtText; accent: Theme.accentDrought }
        Tile { Layout.fillWidth: true; label: "transport"; value: app.transportText; accent: Theme.accentTransport }
    }
}
