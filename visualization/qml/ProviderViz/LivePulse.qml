import QtQuick
import ProviderViz 1.0

/*! LIVE indicator — a solid dot with a soft outward-pulsing ring + small-caps
    label. Visible only while a run is generating data (`app.live`); playback of
    a finished run is replay, not live. */
Row {
    id: root
    visible: app.live
    spacing: 6

    Item {
        width: 16
        height: 16
        anchors.verticalCenter: parent.verticalCenter

        // Outward-pulsing ring.
        Rectangle {
            id: pulse
            anchors.centerIn: parent
            width: 8
            height: 8
            radius: 4
            color: "transparent"
            border.color: Theme.live
            border.width: 1.5
            transformOrigin: Item.Center

            SequentialAnimation on scale {
                running: root.visible
                loops: Animation.Infinite
                NumberAnimation { from: 1.0; to: 2.6; duration: 1400; easing.type: Easing.OutQuad }
                PauseAnimation { duration: 200 }
            }
            SequentialAnimation on opacity {
                running: root.visible
                loops: Animation.Infinite
                NumberAnimation { from: 0.55; to: 0.0; duration: 1400; easing.type: Easing.OutQuad }
                PauseAnimation { duration: 200 }
            }
        }

        // Solid core dot.
        Rectangle {
            anchors.centerIn: parent
            width: 8
            height: 8
            radius: 4
            color: Theme.live
        }
    }

    Text {
        anchors.verticalCenter: parent.verticalCenter
        text: "LIVE"
        color: Theme.live
        font.family: Theme.fontFamily
        font.pixelSize: 10
        font.weight: Font.DemiBold
        font.letterSpacing: 1.2
    }
}
