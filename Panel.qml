import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "hamsti.vitals"
  ipcTarget: ""
  manageIpc: false

  property var snapshot: Model.emptySnapshot()
  property var extras: Model.emptyExtras()
  property bool settingsOpen: false
  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  readonly property color foreground: bar ? bar.foreground : Color.popups.text
  readonly property color accent: Color.accent
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Color.muted
  readonly property color track: Style.hoverFillFor(foreground, Color.accent)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property int refreshSec: Math.max(1, parseInt(setting("refreshIntervalSec", 2), 10) || 2)
  readonly property int warnPercent: Math.max(1, parseInt(setting("warnPercent", 90), 10) || 90)
  readonly property int warnTempC: Math.max(1, parseInt(setting("warnTempC", 85), 10) || 85)
  readonly property string tempUnit: setting("tempUnit", "C")
  readonly property string displayMode: setting("display", "All")
  readonly property string clickAction: setting("clickAction", "Panel")
  readonly property string barStyle: setting("barStyle", "Icons")
  readonly property string diskMount: setting("diskMount", "/")
  readonly property bool compactBar: Model.isOn(setting("compact", false), false)
  readonly property bool showCpu: Model.isOn(setting("showCpu", true), true)
  readonly property bool showMemory: Model.isOn(setting("showMemory", true), true)
  readonly property bool showGpu: Model.isOn(setting("showGpu", true), true)
  readonly property bool showDisk: Model.isOn(setting("showDisk", false), false)
  readonly property bool showNetwork: Model.isOn(setting("showNetwork", true), true)
  readonly property bool showTemp: Model.isOn(setting("showTemp", true), true)
  readonly property var cpu: snapshot && snapshot.cpu ? snapshot.cpu : {}
  readonly property var memory: snapshot && snapshot.memory ? snapshot.memory : {}
  readonly property var gpu: Model.primaryGpu(snapshot)
  readonly property var disks: snapshot && snapshot.disks ? snapshot.disks : []
  readonly property var network: snapshot && snapshot.network ? snapshot.network : {}
  readonly property var temps: snapshot && snapshot.temps ? snapshot.temps : []
  readonly property var cpuRows: Model.processCpuRows(extras)
  readonly property var memoryRows: Model.processMemoryRows(extras)
  readonly property var gpuRows: Model.processGpuRows(extras)
  readonly property string collector: Model.fileUrlToPath(Qt.resolvedUrl("collect.py"))
  readonly property string phrase: Model.statusPhrase(snapshot, warnPercent, warnTempC)
  property string shownPhrase: phrase
  readonly property string heroTemp: snapshot && snapshot.hottest
    ? Model.formatTempFull(snapshot.hottest.celsius, tempUnit)
    : Model.formatTempFull(cpu.tempC, tempUnit)
  readonly property string heroTempLabel: snapshot && snapshot.hottest && snapshot.hottest.label
    ? String(snapshot.hottest.label)
    : "CPU"

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function applyExtras(raw) {
    var next = Model.parseExtras(raw)
    if (next) root.extras = next
  }

  function refreshExtras() {
    if (extrasProc.running) return
    extrasProc.running = true
  }

  function persist(patch) {
    var entry = { id: root.moduleName }
    var src = root.settings || {}
    var key
    for (key in src) if (key !== "id") entry[key] = src[key]
    for (key in patch) entry[key] = patch[key]
    root.settings = entry
    if (root.hostWidget) root.hostWidget.settings = entry
    if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
      root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  function persistOne(key, value) {
    var patch = {}
    patch[key] = value
    persist(patch)
  }

  function toggleFlag(key, current) {
    persistOne(key, current ? "Off" : "On")
  }

  function stepInt(key, fallback, delta, min, max) {
    var current = parseInt(setting(key, fallback), 10)
    if (!isFinite(current)) current = fallback
    persistOne(key, Math.max(min, Math.min(max, current + delta)))
  }

  function openMonitor() {
    if (root.bar) root.bar.run("omarchy-launch-or-focus-tui btop")
    root.close()
  }

  onPhraseChanged: phraseSwap.restart()

  SequentialAnimation {
    id: phraseSwap
    NumberAnimation { target: heroPhrase; property: "opacity"; to: 0; duration: 90 }
    ScriptAction { script: root.shownPhrase = root.phrase }
    NumberAnimation { target: heroPhrase; property: "opacity"; to: 1; duration: 180; easing.type: Easing.OutCubic }
  }

  onOpenedChanged: {
    if (root.opened) root.refreshExtras()
    else root.settingsOpen = false
  }

  Process {
    id: extrasProc
    command: ["python3", root.collector, "--extras"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyExtras(text)
    }
  }

  Timer {
    interval: Math.max(1000, root.refreshSec * 1000)
    running: root.opened
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refreshExtras()
  }

  function meterColor(warned) {
    return warned ? root.urgent : root.accent
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem ? root.anchorItem : root
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(440))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onActivateRequested: root.openMonitor()
      onTextKey: function(t) {
        if (t === "b" || t === "o") root.openMonitor()
      }

      Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height

      Column {
        id: column
        width: scroll.width
        spacing: Style.space(14)

        Item {
          width: parent.width
          implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight, heroTempCol.implicitHeight)

          Text {
            id: heroIcon
            text: "󰈐"
            color: root.accent
            font.family: root.fontFamily
            font.pixelSize: Style.font.display
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter

            Behavior on color { ColorAnimation { duration: 220 } }
          }

          Column {
            id: heroLabels
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(14)
            anchors.right: heroTempCol.left
            anchors.rightMargin: Style.space(10)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Text {
              text: "Vitals"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
              elide: Text.ElideRight
              width: parent.width
            }

            Text {
              id: heroPhrase
              text: root.shownPhrase.toUpperCase()
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.2
              elide: Text.ElideRight
              width: parent.width
            }
          }

          Column {
            id: heroTempCol
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(1)

            Text {
              text: root.heroTemp
              color: Model.metricWarned("temp", root.snapshot, root.warnPercent, root.warnTempC) ? root.urgent : root.accent
              font.family: root.fontFamily
              font.pixelSize: Style.font.displayLarge
              font.bold: true
              horizontalAlignment: Text.AlignRight
              anchors.right: parent.right

              Behavior on color { ColorAnimation { duration: 220 } }
            }

            Text {
              text: root.heroTempLabel.toUpperCase()
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.1
              horizontalAlignment: Text.AlignRight
              anchors.right: parent.right
            }
          }
        }

        MetricBlock {
          icon: "󰍛"
          title: "CPU"
          value: Model.formatPercent(root.cpu.percent)
          fraction: Number(root.cpu.percent) / 100
          warned: Model.metricWarned("cpu", root.snapshot, root.warnPercent, root.warnTempC)
          meta: [
            Model.formatTempFull(root.cpu.tempC, root.tempUnit),
            root.cpu.cores ? (root.cpu.cores + " cores") : "",
            root.cpu.load1 !== null && root.cpu.load1 !== undefined ? ("load " + Model.formatLoad(root.cpu.load1)) : ""
          ].filter(function(part) { return part && part !== "—" }).join("  ·  ")
          rows: root.cpuRows
        }

        MetricBlock {
          icon: "󰘚"
          title: "Memory"
          value: Model.formatPercent(root.memory.percent)
          fraction: Number(root.memory.percent) / 100
          warned: Model.metricWarned("memory", root.snapshot, root.warnPercent, root.warnTempC)
          meta: Model.formatBytes(root.memory.usedBytes) + " / " + Model.formatBytes(root.memory.totalBytes)
            + (root.memory.swapTotalBytes > 0
              ? ("  ·  swap " + Model.formatBytes(root.memory.swapUsedBytes))
              : "")
          rows: root.memoryRows
        }

        MetricBlock {
          visible: root.gpu !== null
          icon: "󰢮"
          title: root.gpu && root.gpu.name ? String(root.gpu.name).replace(/^NVIDIA GeForce /, "") : "GPU"
          value: Model.formatPercent(root.gpu ? root.gpu.percent : null)
          fraction: root.gpu ? Number(root.gpu.percent) / 100 : 0
          warned: Model.metricWarned("gpu", root.snapshot, root.warnPercent, root.warnTempC)
          meta: {
            if (!root.gpu) return ""
            var parts = []
            if (root.gpu.memUsedBytes && root.gpu.memTotalBytes)
              parts.push(Model.formatBytes(root.gpu.memUsedBytes) + " / " + Model.formatBytes(root.gpu.memTotalBytes))
            var temp = Model.formatTempFull(root.gpu.tempC, root.tempUnit)
            if (temp !== "—") parts.push(temp)
            if (root.gpu.powerW !== null && root.gpu.powerW !== undefined)
              parts.push(Math.round(Number(root.gpu.powerW)) + " W")
            return parts.join("  ·  ")
          }
          rows: root.gpuRows
        }

        Repeater {
          model: root.disks

          MetricBlock {
            required property var modelData
            icon: "󰋊"
            title: modelData.mount === "/" ? "Storage" : modelData.mount
            value: Model.formatPercent(modelData.percent)
            fraction: Number(modelData.percent) / 100
            warned: Number(modelData.percent) >= root.warnPercent
            meta: Model.formatBytes(modelData.usedBytes) + " / " + Model.formatBytes(modelData.totalBytes)
              + (modelData.fstype ? ("  ·  " + modelData.fstype) : "")
            rows: Model.directoryRows(root.extras, modelData.mount)
          }
        }

        MetricBlock {
          visible: root.showNetwork
          icon: "󰈀"
          title: "Network"
          value: "↓" + Model.formatRate(root.network.rxRate || 0) + "  ↑" + Model.formatRate(root.network.txRate || 0)
          fraction: 0
          warned: false
          meta: "↓" + Model.formatBytes(root.network.rxBytes || 0) + " total  ·  ↑" + Model.formatBytes(root.network.txBytes || 0) + " total"
          rows: []
        }

        Column {
          visible: root.temps.length > 0
          width: parent.width
          spacing: Style.space(10)

          PanelSeparator { foreground: root.foreground }

          PanelSectionHeader {
            text: "TEMPERATURES"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Flow {
            width: parent.width
            spacing: Style.space(8)

            Repeater {
              model: root.temps

              BorderSurface {
                required property var modelData
                implicitWidth: tempLabel.implicitWidth + Style.space(12)
                implicitHeight: tempLabel.implicitHeight + Style.space(8)
                color: Number(modelData.celsius) >= root.warnTempC
                  ? Style.hoverFillFor(root.urgent, Color.accent)
                  : "transparent"
                borderSpec: Border.controlSpec(
                  Number(modelData.celsius) >= root.warnTempC ? "hover-cursor" : "normal",
                  Number(modelData.celsius) >= root.warnTempC ? root.urgent : root.foreground,
                  Color.accent
                )
                radius: Style.cornerRadius

                Text {
                  id: tempLabel
                  anchors.centerIn: parent
                  text: modelData.label + "  " + Model.formatTempFull(modelData.celsius, root.tempUnit)
                  color: Number(modelData.celsius) >= root.warnTempC ? root.urgent : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                }
              }
            }
          }
        }

        PanelSeparator { foreground: root.foreground }

        Column {
          width: parent.width
          spacing: root.settingsOpen ? Style.space(10) : 0

          Item {
            width: parent.width
            implicitHeight: settingsLabel.implicitHeight + Style.space(8)

            Text {
              id: settingsLabel
              text: "SETTINGS"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.2
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
            }

            Text {
              text: root.settingsOpen ? "▾" : "▸"
              color: root.settingsOpen ? root.accent : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter

              Behavior on color { ColorAnimation { duration: 140 } }
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.settingsOpen = !root.settingsOpen
            }
          }

          Item {
            width: parent.width
            height: root.settingsOpen ? settingsBody.implicitHeight : 0
            clip: true
            opacity: root.settingsOpen ? 1 : 0

            Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: 160 } }

          Column {
            id: settingsBody
            width: parent.width
            spacing: Style.space(12)

            SettingGroup {
              title: "Show on bar"
              hint: "Which pills appear when mode is All"
              SettingPill {
                label: "CPU"
                active: root.showCpu
                enabled: root.displayMode === "All"
                tooltipText: "Show CPU usage on the bar"
                onClicked: root.toggleFlag("showCpu", root.showCpu)
              }
              SettingPill {
                label: "RAM"
                active: root.showMemory
                enabled: root.displayMode === "All"
                tooltipText: "Show memory usage on the bar"
                onClicked: root.toggleFlag("showMemory", root.showMemory)
              }
              SettingPill {
                label: "GPU"
                active: root.showGpu
                enabled: root.displayMode === "All"
                tooltipText: "Show GPU usage on the bar"
                onClicked: root.toggleFlag("showGpu", root.showGpu)
              }
              SettingPill {
                label: "Disk"
                active: root.showDisk
                enabled: root.displayMode === "All"
                tooltipText: "Show disk usage on the bar"
                onClicked: root.toggleFlag("showDisk", root.showDisk)
              }
              SettingPill {
                label: "Network"
                active: root.showNetwork
                enabled: root.displayMode === "All"
                tooltipText: "Show network upload/download rates on the bar"
                onClicked: root.toggleFlag("showNetwork", root.showNetwork)
              }
              SettingPill {
                label: "Temp"
                active: root.showTemp
                enabled: root.displayMode === "All"
                tooltipText: "Append temperatures next to CPU and GPU"
                onClicked: root.toggleFlag("showTemp", root.showTemp)
              }
            }

            SettingGroup {
              title: "Mode"
              hint: "All, or a single metric widget"
              Repeater {
                model: ["All", "CPU", "Memory", "GPU", "Disk", "Network", "Temp"]
                SettingPill {
                  required property string modelData
                  label: modelData
                  active: root.displayMode === modelData
                  tooltipText: modelData === "All" ? "Show every enabled pill" : ("Only show " + modelData)
                  onClicked: root.persistOne("display", modelData)
                }
              }
            }

            SettingGroup {
              title: "Look"
              hint: "Text uses CPU MEM GPU instead of glyphs"
              SettingPill {
                label: "Icons"
                active: root.barStyle !== "Text"
                tooltipText: "Nerd-font glyphs on the bar"
                onClicked: root.persistOne("barStyle", "Icons")
              }
              SettingPill {
                label: "Text"
                active: root.barStyle === "Text"
                tooltipText: "CPU MEM GPU labels on the bar"
                onClicked: root.persistOne("barStyle", "Text")
              }
              SettingPill {
                label: "Compact"
                active: root.compactBar
                tooltipText: "Hide temperatures beside usage"
                onClicked: root.toggleFlag("compact", root.compactBar)
              }
              SettingPill {
                label: "°C"
                active: root.tempUnit !== "F"
                tooltipText: "Celsius"
                onClicked: root.persistOne("tempUnit", "C")
              }
              SettingPill {
                label: "°F"
                active: root.tempUnit === "F"
                tooltipText: "Fahrenheit"
                onClicked: root.persistOne("tempUnit", "F")
              }
            }

            SettingGroup {
              title: "Click"
              hint: "What a left click on the bar does"
              SettingPill {
                label: "Panel"
                active: String(root.clickAction).toLowerCase() !== "btop"
                tooltipText: "Open this dropdown"
                onClicked: root.persistOne("clickAction", "Panel")
              }
              SettingPill {
                label: "btop"
                active: String(root.clickAction).toLowerCase() === "btop"
                tooltipText: "Launch btop"
                onClicked: root.persistOne("clickAction", "btop")
              }
            }

            SettingGroup {
              visible: root.disks.length > 0
              title: "Disk"
              hint: "Filesystem the Disk pill tracks"
              Repeater {
                model: root.disks
                SettingPill {
                  required property var modelData
                  label: modelData.mount
                  active: root.diskMount === modelData.mount
                  tooltipText: "Track " + modelData.mount
                  onClicked: root.persistOne("diskMount", modelData.mount)
                }
              }
            }

            SettingGroup {
              title: "Poll"
              hint: "How often the bar refreshes"
              SettingPill {
                label: "−"
                tooltipText: "Faster refresh"
                onClicked: root.stepInt("refreshIntervalSec", 2, -1, 1, 30)
              }
              SettingPill { label: root.refreshSec + "s"; active: true; tooltipText: "Current poll interval" }
              SettingPill {
                label: "+"
                tooltipText: "Slower refresh"
                onClicked: root.stepInt("refreshIntervalSec", 2, 1, 1, 30)
              }
            }

            SettingGroup {
              title: "Alerts"
              hint: "When the bar flips to the urgent color"
              SettingPill {
                label: "−"
                tooltipText: "Lower usage warning"
                onClicked: root.stepInt("warnPercent", 90, -5, 50, 100)
              }
              SettingPill { label: root.warnPercent + "%"; active: true; tooltipText: "Warn at this usage" }
              SettingPill {
                label: "+"
                tooltipText: "Raise usage warning"
                onClicked: root.stepInt("warnPercent", 90, 5, 50, 100)
              }
              SettingPill {
                label: "−"
                tooltipText: "Lower temperature warning"
                onClicked: root.stepInt("warnTempC", 85, -5, 50, 110)
              }
              SettingPill { label: root.warnTempC + "°"; active: true; tooltipText: "Warn at this temperature" }
              SettingPill {
                label: "+"
                tooltipText: "Raise temperature warning"
                onClicked: root.stepInt("warnTempC", 85, 5, 50, 110)
              }
            }
          }
          }
        }

        Text {
          width: parent.width
          text: "Click or press Enter for btop"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
      }
    }
  }

  component MetricBlock: Column {
    property string icon: ""
    property string title: ""
    property string value: ""
    property real fraction: 0
    property bool warned: false
    property string meta: ""
    property var rows: []

    width: parent ? parent.width : implicitWidth
    spacing: Style.space(6)

    Item {
      width: parent.width
      implicitHeight: Math.max(metricTitle.implicitHeight, metricValue.implicitHeight)

      Text {
        id: metricTitle
        text: (icon ? icon + "  " : "") + title
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
        elide: Text.ElideRight
        anchors.left: parent.left
        anchors.right: metricValue.left
        anchors.rightMargin: Style.space(10)
        anchors.verticalCenter: parent.verticalCenter
      }

      Text {
        id: metricValue
        text: value
        color: warned ? root.urgent : root.accent
        font.family: root.fontFamily
        font.pixelSize: Style.font.title
        font.bold: true
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter

        Behavior on color { ColorAnimation { duration: 180 } }
      }
    }

    Item {
      width: parent.width
      implicitHeight: Style.space(8)

      Rectangle {
        id: track
        anchors.fill: parent
        radius: height / 2
        color: root.track
      }

      Rectangle {
        anchors.left: track.left
        anchors.verticalCenter: track.verticalCenter
        height: track.height
        radius: track.radius
        color: warned ? root.urgent : root.accent
        width: Math.max(track.height, track.width * Math.max(0, Math.min(1, fraction)))

        Behavior on width { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
        Behavior on color { ColorAnimation { duration: 180 } }
      }
    }

    Text {
      visible: meta !== ""
      width: parent.width
      text: meta
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      elide: Text.ElideRight
    }

    Column {
      visible: rows && rows.length > 0
      width: parent.width
      spacing: Style.space(3)

      Repeater {
        model: rows

        Row {
          required property var modelData
          width: parent.width
          spacing: Style.space(8)

          Text {
            width: Math.max(0, parent.width - rowValue.implicitWidth - parent.spacing)
            text: modelData.name
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            elide: Text.ElideRight
          }

          Text {
            id: rowValue
            text: modelData.value
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }
        }
      }
    }
  }

  component SettingGroup: Column {
    property string title: ""
    property string hint: ""
    default property alias content: pills.data

    width: parent ? parent.width : implicitWidth
    spacing: Style.space(4)

    Text {
      visible: title !== ""
      text: title
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      font.bold: true
    }

    Text {
      visible: hint !== ""
      width: parent.width
      text: hint
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.WordWrap
    }

    Flow {
      id: pills
      width: parent.width
      spacing: Style.space(6)
    }
  }

  component SettingPill: Button {
    property string label: ""

    text: label
    fontSize: Style.font.bodySmall
    foreground: root.foreground
    fontFamily: root.fontFamily
    horizontalPadding: Style.spacing.controlPaddingX
    verticalPadding: Style.spacing.controlPaddingY + Style.space(2)
    bordered: true
    opacity: enabled ? 1 : 0.4
  }

}
