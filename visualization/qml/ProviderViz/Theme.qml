pragma Singleton
import QtQuick

/*! Design tokens — light default. Matches visualization/DESIGN.md + REDESIGN.md */
QtObject {
    property string mode: "light"

    readonly property bool isDark: mode === "dark"
    readonly property bool useBlur: true

    // Surfaces — light-first: airy, near-white, low-chroma warm neutrals.
    readonly property color surface: isDark ? "#14161A" : "#F5F4F1"
    readonly property color surfaceRaised: isDark ? "#1C1F24" : "#FCFBF9"

    // Text
    readonly property color text: isDark ? "#E6E4E0" : "#1A1816"
    readonly property color textMuted: isDark ? "#8A8680" : "#6B6560"

    // Accent
    readonly property color accentSoja: isDark ? "#E0A84A" : "#B8720E"
    readonly property color accentFeed: isDark ? "#D47862" : "#A85A48"
    readonly property color accentDrought: isDark ? "#D06A48" : "#B4552F"
    readonly property color accentTransport: isDark ? "#7FA8C0" : "#5C7E92"
    // Live: a run is generating data (header pulse).
    readonly property color live: isDark ? "#5BA870" : "#3D7A52"

    // Glass chrome
    readonly property color glassFill: isDark ? "#2A3139" : "#FFFFFF"
    readonly property color glassBorder: isDark ? "#3E4854" : "#D0CAC2"
    readonly property color glassHighlight: isDark ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.55)
    readonly property color shadowColor: isDark ? "#80000000" : "#1A1A1816"

    // Map — soft environmental (de-chart). Light ocean is airy + low-chroma so
    // the map reads pale and desaturated (CRM-map direction), accent saturation
    // is reserved for data markers.
    readonly property color mapOceanTop: isDark ? "#243440" : "#E1EAED"
    readonly property color mapOceanBottom: isDark ? "#1A2830" : "#CFDDE2"
    readonly property color mapLand: isDark ? "#354550" : "#DDD6CA"
    readonly property color mapCoast: isDark ? "#405060" : "#C8BFB4"
    readonly property color mapLabel: isDark ? "#90A0AA" : "#5C5650"

    // Controls
    readonly property color border: isDark ? "#2E3339" : "#D5D0C8"
    readonly property color controlFill: isDark ? "#20242B" : "#FBFAF8"
    readonly property color controlFillHover: isDark ? "#272C34" : "#F1EEE8"
    readonly property color controlBorder: isDark ? "#39414B" : "#D8D2C9"
    readonly property color accentSoft: isDark ? Qt.rgba(0.88, 0.66, 0.29, 0.16)
                                              : Qt.rgba(0.72, 0.45, 0.05, 0.12)

    // Map data chrome
    readonly property color nodeRing: isDark ? Qt.rgba(1, 1, 1, 0.20) : Qt.rgba(1, 1, 1, 0.72)
    readonly property color nodeIcon: Qt.rgba(1, 1, 1, 0.96)
    readonly property color nodeShadow: isDark ? Qt.rgba(0, 0, 0, 0.45) : Qt.rgba(0.16, 0.13, 0.10, 0.28)

    // Corridors — soft cool flow lines + brighter comet dots travelling them.
    readonly property color corridor: isDark ? "#7BA6BE" : "#6E93A8"
    readonly property color comet: isDark ? "#AFD4E6" : "#4E7E96"

    // Chart
    readonly property color chartGrid: isDark ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(0.10, 0.09, 0.08, 0.06)
    readonly property color chartBaseline: isDark ? Qt.rgba(1, 1, 1, 0.10) : Qt.rgba(0.10, 0.09, 0.08, 0.10)

    readonly property int radiusOuter: 14
    readonly property int radiusInner: 9
    readonly property int radiusControl: 8
    readonly property int spaceUnit: 8
    readonly property string fontFamily: "Segoe UI"
    readonly property string monoFamily: "Consolas"
}
