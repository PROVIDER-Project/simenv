import QtQuick
import QtQuick.Layouts
import ProviderViz 1.0

RowLayout {
    id: root
    property color swatch: Theme.accentSoja
    property string label: ""
    property string value: ""
    spacing: 6

    Rectangle {
        width: 8; height: 8; radius: 4
        color: root.swatch
        Layout.alignment: Qt.AlignVCenter
    }
    Text {
        text: root.label
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: 11
    }
    Text {
        text: root.value
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: 11
        font.weight: Font.DemiBold
        font.hintingPreference: Font.PreferNoHinting
    }
}
