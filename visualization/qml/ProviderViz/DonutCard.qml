import QtQuick
import QtQuick.Layouts
import QtCharts
import ProviderViz 1.0

/*! Transport-utilisation ring (CRM-map "Safeguards 67%" analogue). Qt Charts
    PieSeries with a hole: one accent arc = app.transportFrac, remainder a muted
    track. Centered % value over a small-caps label. */
GlassPanel {
    id: root

    readonly property color trackColor: Theme.isDark ? Qt.rgba(1, 1, 1, 0.10)
                                                     : Qt.rgba(0.1, 0.09, 0.08, 0.08)

    Text {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: root.padding
        text: "TRANSPORT UTILISATION"
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: 10
        font.weight: Font.Medium
        font.letterSpacing: 1.1
        z: 2
    }

    ChartView {
        id: chart
        anchors.fill: parent
        anchors.topMargin: root.padding + 12
        legend.visible: false
        antialiasing: true
        backgroundColor: "transparent"
        backgroundRoundness: 0
        plotAreaColor: "transparent"
        margins.top: 0
        margins.bottom: 0
        margins.left: 0
        margins.right: 0
        animationOptions: ChartView.SeriesAnimations

        PieSeries {
            id: pie
            size: 0.92
            holeSize: 0.72

            PieSlice {
                value: Math.max(0.0001, app.transportFrac)
                color: Theme.accentSoja
                borderColor: Theme.accentSoja
                borderWidth: 0
                labelVisible: false
            }
            PieSlice {
                value: Math.max(0.0001, 1 - app.transportFrac)
                color: root.trackColor
                borderColor: root.trackColor
                borderWidth: 0
                labelVisible: false
            }
        }
    }

    // Centered readout over the ring hole.
    Column {
        anchors.centerIn: chart
        spacing: 1
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Math.round(app.transportFrac * 100) + "%"
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 20
            font.weight: Font.DemiBold
            font.hintingPreference: Font.PreferNoHinting
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "TRANSPORT"
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: 8
            font.weight: Font.Medium
            font.letterSpacing: 1.0
        }
    }
}
