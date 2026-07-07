import QtQuick
import QtQuick.Controls
import ProviderViz 1.0

/*! Bespoke button — quiet pill by default, accent fill when primary. */
Button {
    id: control
    property bool primary: false
    implicitHeight: 36
    leftPadding: 14
    rightPadding: 14
    font.family: Theme.fontFamily
    font.pixelSize: 12
    font.weight: Font.Medium

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.primary ? "#FFFFFF"
                               : (control.enabled ? Theme.text : Theme.textMuted)
        opacity: control.enabled ? 1.0 : 0.55
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Rectangle {
        radius: Theme.radiusControl
        color: control.primary
            ? (control.down ? Qt.darker(Theme.accentSoja, 1.14)
                            : (control.hovered ? Qt.lighter(Theme.accentSoja, 1.05) : Theme.accentSoja))
            : (control.down || control.hovered ? Theme.controlFillHover : Theme.controlFill)
        border.color: control.primary ? Qt.darker(Theme.accentSoja, 1.12) : Theme.controlBorder
        border.width: 1
        opacity: control.enabled ? 1.0 : 0.6

        Behavior on color { ColorAnimation { duration: 100 } }
    }
}
