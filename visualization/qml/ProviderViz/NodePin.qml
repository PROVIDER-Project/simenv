import QtQuick
import QtQuick.Effects
import ProviderViz 1.0

/*! Supply-chain node marker: soft disc + hairline ring + centered outline icon.
    Disc radius encodes quantity (capped upstream); icon stays a fixed size so it
    is always legible. Not glass, not glow — a quiet cartographic pin. */
Item {
    id: root

    property real diam: 40
    property color baseColor: "#888888"
    property url iconSource: ""
    property bool active: true

    width: diam
    height: diam

    // Muted fill: pull the group hue gently toward the map surface so the disc
    // reads as a calm pin rather than a saturated bubble.
    readonly property color discColor: Qt.tint(baseColor, Qt.rgba(Theme.surface.r,
                                        Theme.surface.g, Theme.surface.b, 0.18))

    // Soft contact shadow
    Rectangle {
        anchors.fill: parent
        anchors.margins: -1
        radius: width / 2
        color: "transparent"
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Theme.nodeShadow
            shadowBlur: 0.6
            shadowVerticalOffset: 2
            blurMax: 24
        }
        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: root.discColor
        }
    }

    // Disc + hairline ring
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: root.discColor
        border.color: Theme.nodeRing
        border.width: Math.max(1, diam * 0.045)
    }

    // Centered outline icon, fixed size, recolored to a light on-disc tint
    Image {
        id: glyph
        anchors.centerIn: parent
        width: Math.round(diam * 0.44)
        height: width
        source: root.iconSource
        sourceSize: Qt.size(width * 2, height * 2)
        smooth: true
        visible: false
    }
    MultiEffect {
        anchors.fill: glyph
        source: glyph
        colorization: 1.0
        colorizationColor: Theme.nodeIcon
        brightness: 0.0
    }
}
