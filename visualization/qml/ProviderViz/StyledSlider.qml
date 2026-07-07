import QtQuick
import QtQuick.Controls
import ProviderViz 1.0

/*! Bespoke slider — thin track, accent fill, soft handle. */
Slider {
    id: control
    implicitHeight: 28

    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.availableWidth
        height: 4
        radius: 2
        color: Theme.controlBorder

        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: 2
            color: control.enabled ? Theme.accentSoja : Theme.textMuted
            opacity: control.enabled ? 0.9 : 0.5
        }
    }

    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        implicitWidth: 16
        implicitHeight: 16
        radius: 8
        color: Theme.glassFill
        border.color: control.pressed ? Theme.accentSoja : Theme.controlBorder
        border.width: control.pressed ? 2 : 1
        visible: control.enabled

        Rectangle {
            anchors.centerIn: parent
            width: 6; height: 6; radius: 3
            color: Theme.accentSoja
            opacity: 0.9
        }
    }
}
