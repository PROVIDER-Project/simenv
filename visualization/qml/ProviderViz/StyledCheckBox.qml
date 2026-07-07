import QtQuick
import QtQuick.Controls
import ProviderViz 1.0

/*! Bespoke checkbox — rounded box with a drawn accent tick. */
CheckBox {
    id: control
    font.family: Theme.fontFamily
    font.pixelSize: 12
    spacing: 8

    indicator: Rectangle {
        implicitWidth: 18
        implicitHeight: 18
        x: control.leftPadding
        y: control.topPadding + (control.availableHeight - height) / 2
        radius: 5
        color: control.checked ? Theme.accentSoja : Theme.controlFill
        border.color: control.checked ? Qt.darker(Theme.accentSoja, 1.1)
                                       : (control.hovered ? Theme.textMuted : Theme.controlBorder)
        border.width: 1
        Behavior on color { ColorAnimation { duration: 100 } }

        Canvas {
            anchors.centerIn: parent
            width: 12; height: 12
            visible: control.checked
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                ctx.strokeStyle = "#FFFFFF"
                ctx.lineWidth = 1.8
                ctx.lineCap = "round"
                ctx.lineJoin = "round"
                ctx.beginPath()
                ctx.moveTo(2.5, 6.5); ctx.lineTo(5, 9); ctx.lineTo(9.5, 3)
                ctx.stroke()
            }
            onVisibleChanged: if (visible) requestPaint()
            Component.onCompleted: requestPaint()
        }
    }

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.enabled ? Theme.text : Theme.textMuted
        opacity: control.enabled ? 1.0 : 0.55
        verticalAlignment: Text.AlignVCenter
        leftPadding: control.indicator.width + control.spacing
    }
}
