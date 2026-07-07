import QtQuick
import QtQuick.Effects
import ProviderViz 1.0

/*! Left icon nav rail (CRM-map direction). Thin vertical rail: view switches at
    the top, theme toggle + avatar pinned at the bottom. Icons are recolored via
    MultiEffect (same pattern as NodePin). View buttons are visual-only
    placeholders in P1 — only the theme toggle is wired. */
Rectangle {
    id: root
    implicitWidth: 56

    // Which nav slot reads as active. Purely presentational in P1.
    property int currentView: 0

    color: Theme.surfaceRaised

    // Right hairline separating rail from the map content.
    Rectangle {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 1
        color: Theme.border
    }

    // -- reusable rail button ------------------------------------------------
    component NavButton: Item {
        id: nb
        property url icon: ""
        property string glyph: ""
        property bool active: false
        property color glyphColor: active ? Theme.accentSoja
                                           : (hover.hovered ? Theme.text : Theme.textMuted)
        signal clicked()

        width: 56
        height: 46

        // Active accent bar on the left edge.
        Rectangle {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: 2.5
            height: 22
            radius: 1.5
            color: Theme.accentSoja
            visible: nb.active
        }

        // Hover / active pill behind the icon.
        Rectangle {
            anchors.centerIn: parent
            width: 38
            height: 38
            radius: Theme.radiusControl
            color: nb.active ? Theme.accentSoft
                             : (hover.hovered ? Theme.controlFillHover : "transparent")
            Behavior on color { ColorAnimation { duration: 100 } }
        }

        // Outline icon, recolored.
        Image {
            id: glyphImg
            anchors.centerIn: parent
            width: 20
            height: 20
            source: nb.icon
            sourceSize: Qt.size(40, 40)
            smooth: true
            visible: false
        }
        MultiEffect {
            anchors.fill: glyphImg
            source: glyphImg
            visible: nb.icon != ""
            colorization: 1.0
            colorizationColor: nb.glyphColor
        }

        // Text-glyph fallback (theme toggle uses this instead of an SVG).
        Text {
            anchors.centerIn: parent
            visible: nb.icon == "" && nb.glyph.length > 0
            text: nb.glyph
            color: nb.glyphColor
            font.family: Theme.fontFamily
            font.pixelSize: 16
        }

        HoverHandler { id: hover }
        TapHandler { onTapped: nb.clicked() }
    }

    // -- layout --------------------------------------------------------------
    Column {
        id: topGroup
        anchors.top: parent.top
        anchors.topMargin: 14
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 4

        NavButton {
            icon: Qt.resolvedUrl("../../assets/icons/nav/map.svg")
            active: root.currentView === 0
            onClicked: root.currentView = 0
        }
        NavButton {
            icon: Qt.resolvedUrl("../../assets/icons/nav/chart.svg")
            active: root.currentView === 1
            onClicked: root.currentView = 1
        }
        NavButton {
            icon: Qt.resolvedUrl("../../assets/icons/nav/runner.svg")
            active: root.currentView === 2
            onClicked: root.currentView = 2
        }
    }

    Column {
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 8

        // Theme toggle — the one wired control in the rail.
        NavButton {
            glyph: Theme.isDark ? "☀" : "☾"   // sun / moon
            onClicked: theme.toggle()
        }

        // Avatar placeholder.
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 30
            height: 30
            radius: 15
            color: Theme.accentSoft
            border.color: Theme.controlBorder
            border.width: 1
            Text {
                anchors.centerIn: parent
                text: "N"
                color: Theme.accentSoja
                font.family: Theme.fontFamily
                font.pixelSize: 12
                font.weight: Font.DemiBold
            }
        }
    }
}
