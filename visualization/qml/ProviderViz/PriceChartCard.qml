import QtQuick
import QtQuick.Layouts
import ProviderViz 1.0

GlassPanel {
    id: root
    implicitHeight: 178

    ColumnLayout {
        width: parent.width
        spacing: Theme.spaceUnit

        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            Text {
                text: "Price"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 12
                font.weight: Font.DemiBold
                font.letterSpacing: 0.3
            }
            Item { Layout.fillWidth: true }

            // Legend
            LegendDot { swatch: Theme.accentSoja; label: "soja"; value: app.sojaText }
            LegendDot { swatch: Theme.accentFeed; label: "feed"; value: app.feedText }
        }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 116

            Canvas {
                id: canvas
                anchors.fill: parent

                Connections {
                    target: chart
                    function onChartChanged() { canvas.requestPaint() }
                }
                Connections {
                    target: Theme
                    function onModeChanged() { canvas.requestPaint() }
                }

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    ctx.clearRect(0, 0, width, height)

                    var padTop = 8, padBottom = 6
                    var h = height - padTop - padBottom
                    var y0 = padTop

                    // Horizontal grid (3 lines) + baseline
                    ctx.strokeStyle = Theme.chartGrid
                    ctx.lineWidth = 1
                    for (var g = 0; g <= 3; g++) {
                        var gy = Math.round(y0 + h * g / 3) + 0.5
                        ctx.beginPath()
                        ctx.moveTo(0, gy)
                        ctx.lineTo(width, gy)
                        ctx.stroke()
                    }

                    if (!chart.hasData)
                        return
                    var soja = chart.sojaNorm
                    var feed = chart.feedNorm
                    var n = Math.max(soja.length, feed.length)
                    if (n < 2)
                        return

                    function px(i, len) { return i * width / (len - 1) }
                    function py(v) { return y0 + h - v * h }

                    // Soja area fill
                    if (soja.length >= 2) {
                        var grad = ctx.createLinearGradient(0, y0, 0, y0 + h)
                        grad.addColorStop(0, Qt.rgba(Theme.accentSoja.r, Theme.accentSoja.g, Theme.accentSoja.b, 0.22))
                        grad.addColorStop(1, Qt.rgba(Theme.accentSoja.r, Theme.accentSoja.g, Theme.accentSoja.b, 0.0))
                        ctx.fillStyle = grad
                        ctx.beginPath()
                        ctx.moveTo(0, y0 + h)
                        for (var i = 0; i < soja.length; i++)
                            ctx.lineTo(px(i, soja.length), py(soja[i]))
                        ctx.lineTo(width, y0 + h)
                        ctx.closePath()
                        ctx.fill()
                    }

                    function line(series, color, w) {
                        ctx.strokeStyle = color
                        ctx.lineWidth = w
                        ctx.lineJoin = "round"
                        ctx.beginPath()
                        for (var i = 0; i < series.length; i++) {
                            var x = px(i, series.length), y = py(series[i])
                            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
                        }
                        ctx.stroke()
                    }

                    line(feed, Qt.rgba(Theme.accentFeed.r, Theme.accentFeed.g, Theme.accentFeed.b, 0.75), 1.4)
                    line(soja, Theme.accentSoja, 2.0)

                    // Playhead
                    var pf = chart.playheadFraction
                    var pxpos = pf * width
                    ctx.strokeStyle = Theme.chartBaseline
                    ctx.lineWidth = 1
                    ctx.setLineDash([3, 4])
                    ctx.beginPath()
                    ctx.moveTo(Math.round(pxpos) + 0.5, y0)
                    ctx.lineTo(Math.round(pxpos) + 0.5, y0 + h)
                    ctx.stroke()
                    ctx.setLineDash([])

                    // Marker dot on soja at playhead
                    if (soja.length >= 2) {
                        var idx = Math.round(pf * (soja.length - 1))
                        var mx = px(idx, soja.length), my = py(soja[idx])
                        ctx.fillStyle = Theme.surface
                        ctx.beginPath(); ctx.arc(mx, my, 3.5, 0, Math.PI * 2); ctx.fill()
                        ctx.fillStyle = Theme.accentSoja
                        ctx.beginPath(); ctx.arc(mx, my, 2.4, 0, Math.PI * 2); ctx.fill()
                    }
                }
                Component.onCompleted: requestPaint()
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
            }
        }
    }
}
