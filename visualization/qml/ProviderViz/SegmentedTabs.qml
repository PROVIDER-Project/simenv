import QtQuick
import ProviderViz 1.0

/*! Segmented tab control (CRM-map "Core / Growth markets" analogue). Bound to a
    string model; emits activated(index). Used for the scenario switch. */
Item {
    id: root

    property var model: []
    property int currentIndex: 0
    signal activated(int index)

    // Strip a "Scenario N — baseline" label down to "Baseline".
    function shortLabel(s) {
        var str = String(s)
        var dash = str.indexOf("—")
        var out = dash >= 0 ? str.substring(dash + 1).trim() : str
        return out.length ? out.charAt(0).toUpperCase() + out.slice(1) : str
    }

    implicitHeight: 34
    implicitWidth: track.implicitWidth

    Rectangle {
        id: track
        anchors.fill: parent
        radius: Theme.radiusControl
        color: Theme.controlFill
        border.color: Theme.controlBorder
        border.width: 1
        implicitWidth: row.implicitWidth + 6

        Row {
            id: row
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 3
            spacing: 0

            Repeater {
                model: root.model
                delegate: Item {
                    id: seg
                    required property int index
                    required property var modelData
                    readonly property bool selected: index === root.currentIndex

                    width: Math.max(96, label.implicitWidth + 28)
                    height: root.height - 6
                    anchors.verticalCenter: parent ? parent.verticalCenter : undefined

                    Rectangle {
                        anchors.fill: parent
                        radius: Theme.radiusControl - 2
                        color: seg.selected ? Theme.glassFill : "transparent"
                        border.color: seg.selected ? Theme.controlBorder : "transparent"
                        border.width: 1
                        opacity: seg.selected ? 1.0 : (hover.hovered ? 0.6 : 0.0)
                        Behavior on opacity { NumberAnimation { duration: 100 } }
                    }

                    Text {
                        id: label
                        anchors.centerIn: parent
                        text: root.shortLabel(seg.modelData)
                        color: seg.selected ? Theme.text : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        font.weight: seg.selected ? Font.DemiBold : Font.Medium
                    }

                    HoverHandler { id: hover }
                    TapHandler { onTapped: root.activated(seg.index) }
                }
            }
        }
    }
}
