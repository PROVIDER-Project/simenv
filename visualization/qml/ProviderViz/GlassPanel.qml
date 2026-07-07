import QtQuick
import QtQuick.Effects
import ProviderViz 1.0

/*! Frosted panel — MultiEffect shadow when useBlur; solid elevated fallback */
Item {
    id: root

    property alias content: contentItem.data
    property int cornerRadius: Theme.radiusOuter
    property int padding: Theme.spaceUnit + 4

    implicitWidth: contentItem.implicitWidth + padding * 2
    implicitHeight: contentItem.implicitHeight + padding * 2

    Rectangle {
        id: shadowPlate
        anchors.fill: panel
        anchors.topMargin: Theme.useBlur ? 0 : 3
        visible: !Theme.useBlur
        color: Theme.shadowColor
        radius: cornerRadius
        opacity: 0.25
    }

    Rectangle {
        id: panel
        anchors.fill: parent
        border.color: Theme.glassBorder
        border.width: 1
        radius: cornerRadius
        opacity: Theme.useBlur ? 0.94 : 1.0
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.lighter(Theme.glassFill, Theme.isDark ? 1.10 : 1.015) }
            GradientStop { position: 1.0; color: Theme.glassFill }
        }

        layer.enabled: Theme.useBlur
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.shadowColor
            shadowBlur: 0.4
            shadowVerticalOffset: 4
            shadowHorizontalOffset: 0
            blurMax: 32
        }

        // Top highlight hairline
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: cornerRadius * 0.5
            anchors.rightMargin: cornerRadius * 0.5
            anchors.topMargin: 1
            height: 1
            color: Theme.glassHighlight
            opacity: 0.7
        }
    }

    Item {
        id: contentItem
        anchors.fill: parent
        anchors.margins: padding
    }
}
