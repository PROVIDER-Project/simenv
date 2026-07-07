import QtQuick
import QtQuick.Controls
import ProviderViz 1.0

/*! Bespoke ComboBox — restrained pill with a drawn chevron and frosted popup. */
ComboBox {
    id: control
    implicitHeight: 36
    font.family: Theme.fontFamily
    font.pixelSize: 12

    contentItem: Text {
        leftPadding: 12
        rightPadding: 8
        text: control.displayText
        font: control.font
        color: control.enabled ? Theme.text : Theme.textMuted
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: Canvas {
        id: chevron
        x: control.width - width - 12
        y: control.topPadding + (control.availableHeight - height) / 2
        width: 12
        height: 8
        Connections { target: Theme; function onModeChanged() { chevron.requestPaint() } }
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.strokeStyle = Theme.textMuted
            ctx.lineWidth = 1.4
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            ctx.beginPath()
            ctx.moveTo(1, 1); ctx.lineTo(6, 6); ctx.lineTo(11, 1)
            ctx.stroke()
        }
        Component.onCompleted: requestPaint()
    }

    background: Rectangle {
        implicitWidth: 160
        radius: Theme.radiusControl
        color: control.down || control.hovered ? Theme.controlFillHover : Theme.controlFill
        border.color: control.activeFocus ? Theme.accentSoja : Theme.controlBorder
        border.width: 1
        opacity: control.enabled ? 1.0 : 0.6
        Behavior on color { ColorAnimation { duration: 100 } }
    }

    delegate: ItemDelegate {
        width: control.width
        height: 32
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: modelData
            font.family: Theme.fontFamily
            font.pixelSize: 12
            color: Theme.text
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            color: highlighted ? Theme.accentSoft : "transparent"
            radius: 6
        }
    }

    popup: Popup {
        y: control.height + 4
        width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 260)
        padding: 4
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: Rectangle {
            radius: Theme.radiusInner
            color: Theme.glassFill
            border.color: Theme.glassBorder
            border.width: 1
        }
    }
}
