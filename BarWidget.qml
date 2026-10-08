import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "hamsti.vitals"

  property var snapshot: Model.emptySnapshot()

  readonly property int refreshSec: Math.max(1, parseInt(setting("refreshIntervalSec", 2), 10) || 2)
  readonly property int warnPercent: Math.max(1, parseInt(setting("warnPercent", 90), 10) || 90)
  readonly property int warnTempC: Math.max(1, parseInt(setting("warnTempC", 85), 10) || 85)
  readonly property string tempUnit: setting("tempUnit", "C")
  readonly property string clickAction: setting("clickAction", "Panel")
  readonly property var metrics: Model.visibleMetrics(root.settings, root.snapshot)
  readonly property var verticalLines: Model.verticalLines(root.metrics)
  readonly property bool alarming: Model.anyWarned(root.snapshot, root.warnPercent, root.warnTempC)
  readonly property string collector: Model.fileUrlToPath(Qt.resolvedUrl("collect.py"))
  readonly property string barTooltip: Model.tooltipLines(root.snapshot, root.settings)

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
    if ("snapshot" in target) target.snapshot = root.snapshot
  }

  function applySnapshot(raw) {
    var next = Model.parseSnapshot(raw)
    if (!next) return
    root.snapshot = next
    if (panelLoader.item && "snapshot" in panelLoader.item)
      panelLoader.item.snapshot = next
  }

  function refresh() {
    if (!collectProc.running) collectProc.running = true
  }

  function openMonitor() {
    if (root.bar) root.bar.run("omarchy-launch-or-focus-tui btop")
  }

  function handlePress(buttonId) {
    if (buttonId === Qt.RightButton) {
      root.openMonitor()
      return
    }
    if (buttonId === Qt.MiddleButton) {
      root.refresh()
      return
    }
    if (String(root.clickAction).toLowerCase() === "btop") {
      root.openMonitor()
      return
    }
    root.togglePanel()
  }

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function open() {
    if (panelLoader.item && panelLoader.item.open) panelLoader.item.open()
  }

  function close() {
    if (panelLoader.item && panelLoader.item.close) panelLoader.item.close()
  }

  function togglePanel() {
    if (panelLoader.item && panelLoader.item.toggle) panelLoader.item.toggle()
  }

  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  visible: root.metrics.length > 0

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()
  onSnapshotChanged: injectPanel()

  Process {
    id: collectProc
    command: ["python3", root.collector]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applySnapshot(text)
    }
  }

  Timer {
    interval: root.refreshSec * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  IpcHandler {
    target: "hamsti.vitals"

    function refresh(): void { root.broadcast("refresh") }
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.togglePanel() }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.vertical ? "" : ""
    labelVisible: false
    hasVisualContent: root.metrics.length > 0
    tooltipText: root.barTooltip
    horizontalMargin: 8.75
    verticalPadding: 8.75
    fixedWidth: root.vertical ? -1 : Math.max(12, metricsRow.implicitWidth + scaledHorizontalMargin * 2)
    fixedHeight: root.vertical ? Math.max(Style.bar.iconSlot, verticalCol.implicitHeight) : -1
    useActiveColor: true
    active: root.alarming

    onPressed: function(b) { root.handlePress(b) }

    Row {
      id: metricsRow
      visible: !root.vertical
      anchors.centerIn: parent
      spacing: Style.space(10)

      Repeater {
        model: root.metrics

        Row {
          required property var modelData
          spacing: Style.space(5)

          Text {
            text: modelData.icon
            color: button.active && button.useActiveColor ? button.activeColor : button.foreground
            font.family: button.fontFamily
            font.pixelSize: modelData.useText ? Style.font.caption : Style.bar.iconFont
            font.bold: !!modelData.useText
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            text: modelData.text
            color: button.active && button.useActiveColor ? button.activeColor : button.foreground
            font.family: button.fontFamily
            font.pixelSize: Style.font.body
            anchors.verticalCenter: parent.verticalCenter
          }
        }
      }
    }

    Column {
      id: verticalCol
      visible: root.vertical
      anchors.centerIn: parent
      spacing: 0

      Repeater {
        model: root.verticalLines

        OpticalGlyph {
          required property string modelData
          width: button.width
          height: Style.bar.iconSlot
          text: modelData
          fontFamily: button.fontFamily
          fontSize: modelData.length > 3 ? button.fontSize * 0.9 : button.fontSize
          color: button.active && button.useActiveColor ? button.activeColor : button.foreground
        }
      }
    }
  }
}
