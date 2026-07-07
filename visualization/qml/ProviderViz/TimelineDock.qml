import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ProviderViz 1.0

GlassPanel {
    id: root
    RowLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: root.padding
        anchors.rightMargin: root.padding
        spacing: Theme.spaceUnit

        PillButton {
            implicitWidth: 64
            implicitHeight: 40
            primary: app.playing
            text: app.playing ? "⏸" : "▶"
            font.pixelSize: 14
            enabled: app.hasData
            onClicked: app.togglePlay()
        }
        PillButton {
            implicitWidth: 40
            implicitHeight: 40
            leftPadding: 0; rightPadding: 0
            text: "‹"
            font.pixelSize: 16
            enabled: app.hasData
            onClicked: app.stepBack()
        }
        PillButton {
            implicitWidth: 40
            implicitHeight: 40
            leftPadding: 0; rightPadding: 0
            text: "›"
            font.pixelSize: 16
            enabled: app.hasData
            onClicked: app.stepForward()
        }

        StyledSlider {
            id: periodSlider
            Layout.fillWidth: true
            from: 0
            to: app.periodMax
            value: app.periodIndex
            enabled: app.hasData && app.periodMax > 0
            onMoved: app.setPeriodIndex(Math.round(value))
        }

        Text {
            text: app.periodLabel
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: 12
            font.hintingPreference: Font.PreferNoHinting
            horizontalAlignment: Text.AlignRight
            Layout.minimumWidth: 116
        }

        Text {
            text: "speed"
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: 11
        }
        StyledComboBox {
            implicitWidth: 76
            model: ["0.5×", "1×", "2×", "4×"]
            currentIndex: app.speedIndex
            enabled: app.hasData
            onActivated: (index) => app.setSpeedIndex(index)
        }
    }

    Connections {
        target: app
        function onStateChanged() {
            if (periodSlider.value !== app.periodIndex)
                periodSlider.value = app.periodIndex
        }
    }
}
