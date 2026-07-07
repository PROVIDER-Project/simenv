import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Shapes
import ProviderViz 1.0

/*! Atlantic-centered basemap — raster land/heat from Python, dynamic overlays in QML. */
Item {
    id: root

    clip: true

    property real panX: 0
    property real panY: 0

    readonly property real mapWidth: width
    readonly property real mapHeight: width * map.aspectRatio
    readonly property real mapOffsetY: Math.max(0, (height - mapHeight) / 2)
    readonly property string landSource: Theme.isDark ? map.landImageDark : map.landImageLight
    readonly property string heatSource: Theme.isDark ? map.heatMaskDark : map.heatMaskLight
    // Snap zoom so we do not re-rasterize on every wheel tick; one tile per 0.5× step.
    readonly property real rasterZoom: Math.max(1, Math.round(map.zoom * 2) / 2)
    readonly property int rasterW: Math.ceil(map.canvasW * rasterZoom)
    readonly property int rasterH: Math.ceil(map.canvasH * rasterZoom)

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusOuter
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.mapOceanTop }
            GradientStop { position: 0.5; color: Theme.mapOceanBottom }
            GradientStop { position: 1.0; color: Theme.mapOceanBottom }
        }
    }

    Item {
        id: mapLayer
        x: root.panX + (root.width - mapWidth * map.zoom) / 2
        y: root.mapOffsetY + root.panY + (mapHeight - mapHeight * map.zoom) / 2
        width: root.mapWidth
        height: root.mapHeight
        scale: map.zoom
        transformOrigin: Item.TopLeft

        Image {
            id: landImage
            anchors.fill: parent
            source: root.landSource
            sourceSize: Qt.size(root.rasterW, root.rasterH)
            fillMode: Image.Stretch
            smooth: true
            mipmap: false
            cache: false
        }

        Image {
            id: heatImage
            anchors.fill: parent
            source: root.heatSource
            sourceSize: Qt.size(root.rasterW, root.rasterH)
            fillMode: Image.Stretch
            smooth: true
            mipmap: false
            visible: app.heatmapVisible && app.droughtAlpha > 0.01
            opacity: Math.min(app.droughtAlpha * 0.72, 0.75)
            Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.OutQuad } }
            cache: false
        }

        Repeater {
            model: map.visibleLabels
            delegate: Text {
                text: modelData.display
                color: Theme.mapLabel
                font.family: Theme.fontFamily
                font.pixelSize: 8
                font.weight: Font.Medium
                opacity: 0.6
                x: modelData.x * mapLayer.width - implicitWidth / 2
                y: modelData.y * mapLayer.height - implicitHeight / 2
            }
        }

        Repeater {
            model: map.ports
            delegate: Item {
                x: modelData.x * mapLayer.width - 3.5
                y: modelData.y * mapLayer.height - 3.5
                width: 7
                height: 7
                Rectangle {
                    anchors.fill: parent
                    radius: 3.5
                    color: modelData.role === "export"
                           ? (Theme.isDark ? "#6B9E78" : "#5A8A68")
                           : (Theme.isDark ? "#8A9EB8" : "#6A7A94")
                    border.color: Theme.mapCoast
                    border.width: 0.5
                    opacity: 0.85
                }
            }
        }

        // Faint corridor base lines — one per active origin route. Geometry is
        // static (map.routePaths is constant); only opacity reacts to load.
        Repeater {
            model: map.routePaths
            delegate: Shape {
                anchors.fill: parent
                antialiasing: true
                readonly property int load: map.corridorLoads[modelData.origin] || 0
                opacity: load > 0 ? Math.min(0.14 + load * 0.05, 0.42) : 0.0
                Behavior on opacity { NumberAnimation { duration: 300 } }

                ShapePath {
                    strokeColor: Theme.corridor
                    strokeWidth: 2.2 / map.zoom
                    fillColor: "transparent"
                    capStyle: ShapePath.RoundCap
                    joinStyle: ShapePath.RoundJoin
                    PathPolyline {
                        path: modelData.points.map(function(p) {
                            return Qt.point(p.x * mapLayer.width, p.y * mapLayer.height)
                        })
                    }
                }
            }
        }

        // Flowing comet dots travelling the corridors — density ∝ volume via the
        // upstream ship-count. Soft glow halo + bright core; zoom-stable.
        Repeater {
            model: map.ships
            delegate: Item {
                visible: modelData.visible
                x: modelData.nx * mapLayer.width
                y: modelData.ny * mapLayer.height
                width: 0
                height: 0
                scale: 1 / map.zoom
                transformOrigin: Item.Center

                Rectangle {
                    anchors.centerIn: parent
                    width: 8
                    height: 8
                    radius: 4
                    color: Theme.comet
                    opacity: 0.5
                    layer.enabled: true
                    layer.effect: MultiEffect {
                        blurEnabled: true
                        blur: 1.0
                        blurMax: 16
                    }
                }
                Rectangle {
                    anchors.centerIn: parent
                    width: 3.5
                    height: 3.5
                    radius: 1.75
                    color: Theme.comet
                }
            }
        }

        // Glow blooms behind active nodes (drawn under the pins).
        Repeater {
            model: app.nodes
            delegate: Item {
                readonly property real pinDiam: modelData.r * mapLayer.width * 2
                x: modelData.cx * mapLayer.width
                y: modelData.cy * mapLayer.height
                width: 0
                height: 0
                scale: 1 / map.zoom
                transformOrigin: Item.Center

                NodeBloom {
                    anchors.centerIn: parent
                    diam: parent.pinDiam * 2.6
                    color: modelData.color
                    active: modelData.active
                    Behavior on diam { NumberAnimation { duration: 150; easing.type: Easing.OutQuad } }
                }
            }
        }

        Repeater {
            model: app.nodes
            delegate: Item {
                property real diam: modelData.r * mapLayer.width * 2
                x: modelData.cx * mapLayer.width - diam / 2
                y: modelData.cy * mapLayer.height - diam / 2
                width: diam
                height: diam

                NodePin {
                    anchors.centerIn: parent
                    diam: parent.diam
                    baseColor: modelData.color
                    iconSource: modelData.icon
                    active: modelData.active
                    opacity: modelData.opacity
                    // Icons should not scale with map zoom — counter-scale so the
                    // pin keeps a constant screen size while the map zooms.
                    scale: 1 / map.zoom
                    transformOrigin: Item.Center
                    Behavior on diam { NumberAnimation { duration: 150; easing.type: Easing.OutQuad } }
                    Behavior on opacity { NumberAnimation { duration: 150 } }
                }
            }
        }
    }

    Text {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 10
        z: 2
        text: map.geoNote
        color: Theme.mapLabel
        font.family: Theme.fontFamily
        font.pixelSize: 9
        opacity: 0.72
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.NoButton
        hoverEnabled: false
        propagateComposedEvents: true

        property real _dragStartX: 0
        property real _dragStartY: 0
        property bool _dragging: false

        onPressed: (mouse) => {
            if (map.zoom > 1.01) {
                _dragging = true
                _dragStartX = mouse.x - root.panX
                _dragStartY = mouse.y - root.panY
            }
        }
        onReleased: _dragging = false
        onPositionChanged: (mouse) => {
            if (_dragging && map.zoom > 1.01) {
                root.panX = mouse.x - _dragStartX
                root.panY = mouse.y - _dragStartY
            }
        }
        onWheel: (wheel) => {
            var delta = wheel.angleDelta.y
            if (delta === 0)
                return
            var step = delta > 0 ? 1.12 : 1 / 1.12
            var z = Math.max(1, Math.min(8, map.zoom * step))
            if (z <= 1.01) {
                root.panX = 0
                root.panY = 0
            }
            map.setZoom(z)
            wheel.accepted = true
        }
    }

    Connections {
        target: map
        function onZoomChanged() {
            if (map.zoom <= 1.01) {
                root.panX = 0
                root.panY = 0
            }
        }
    }
}
