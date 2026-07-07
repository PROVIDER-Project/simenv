import QtQuick
import QtQuick.Effects
import ProviderViz 1.0

/*! Soft colored glow behind an active NodePin (CRM-map "glow bloom"). A blurred
    disc in the node's group color, gently pulsing. Size tracks the pin diameter
    (which already encodes throughput); inactive nodes render nothing. The caller
    counter-scales by 1/zoom so the bloom stays screen-stable like the pin. */
Item {
    id: root

    property real diam: 60          // matched to pin diameter by the caller
    property color color: "#888888"
    property bool active: true

    width: diam
    height: diam
    visible: active

    // Blurred source disc → soft radial glow.
    Rectangle {
        id: src
        anchors.fill: parent
        radius: width / 2
        color: root.color
        visible: false
    }

    MultiEffect {
        id: glow
        anchors.fill: src
        source: src
        blurEnabled: true
        blur: 1.0
        blurMax: 40
        // Base intensity; the pulse animates around it.
        opacity: 0.34
        transformOrigin: Item.Center

        SequentialAnimation on scale {
            running: root.active
            loops: Animation.Infinite
            NumberAnimation { from: 0.86; to: 1.14; duration: 1700; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1.14; to: 0.86; duration: 1700; easing.type: Easing.InOutSine }
        }
        SequentialAnimation on opacity {
            running: root.active
            loops: Animation.Infinite
            NumberAnimation { from: 0.24; to: 0.42; duration: 1700; easing.type: Easing.InOutSine }
            NumberAnimation { from: 0.42; to: 0.24; duration: 1700; easing.type: Easing.InOutSine }
        }
    }
}
