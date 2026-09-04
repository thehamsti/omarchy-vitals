function clamp(value, lo, hi) {
  var n = Number(value)
  if (!isFinite(n)) return lo
  return Math.max(lo, Math.min(hi, n))
}

function isOn(value, fallback) {
  if (value === undefined || value === null || value === "") return !!fallback
  if (typeof value === "boolean") return value
  var s = String(value).replace(/^\s+|\s+$/g, "").toLowerCase()
  if (s === "on" || s === "true" || s === "1" || s === "yes") return true
  if (s === "off" || s === "false" || s === "0" || s === "no") return false
  return !!fallback
}

function fileUrlToPath(url) {
  var s = String(url || "")
  if (s.indexOf("file://") === 0) s = s.substring(7)
  try {
    return decodeURIComponent(s)
  } catch (e) {
    return s
  }
}

function emptySnapshot() {
  return {
    ok: false,
    ts: 0,
    cpu: { percent: null, tempC: null, load1: null, load5: null, load15: null, cores: 0 },
    memory: { percent: null, usedBytes: 0, totalBytes: 0, availableBytes: 0, swapUsedBytes: 0, swapTotalBytes: 0 },
    gpus: [],
    disks: [],
    network: { rxBytes: 0, txBytes: 0, rxRate: 0, txRate: 0 },
    temps: [],
    hottest: null
  }
}

function emptyExtras() {
  return {
    ok: false,
    processes: { cpu: [], memory: [], gpu: [] },
    directories: {}
  }
}

function parseSnapshot(raw) {
  var text = String(raw || "").replace(/^\s+|\s+$/g, "")
  if (!text) return null
  try {
    var data = JSON.parse(text)
    if (!data || typeof data !== "object") return null
    if (!data.cpu) data.cpu = emptySnapshot().cpu
    if (!data.memory) data.memory = emptySnapshot().memory
    if (!Array.isArray(data.gpus)) data.gpus = []
    if (!Array.isArray(data.disks)) data.disks = []
    if (!data.network) data.network = emptySnapshot().network
    if (!Array.isArray(data.temps)) data.temps = []
    return data
  } catch (e) {
    return null
  }
}

function primaryGpu(snapshot) {
  var gpus = snapshot && snapshot.gpus ? snapshot.gpus : []
  return gpus.length > 0 ? gpus[0] : null
}

function diskForMount(snapshot, mount) {
  var disks = snapshot && snapshot.disks ? snapshot.disks : []
  var wanted = String(mount || "/")
  var i
  for (i = 0; i < disks.length; i++) {
    if (disks[i] && disks[i].mount === wanted) return disks[i]
  }
  if (wanted !== "/" ) {
    for (i = 0; i < disks.length; i++) {
      if (disks[i] && disks[i].mount === "/") return disks[i]
    }
  }
  return disks.length > 0 ? disks[0] : null
}

function formatPercent(value, emptyText) {
  if (value === undefined || value === null || !isFinite(Number(value))) return emptyText || "—"
  return Math.round(Number(value)) + "%"
}

function formatProcessPercent(value, emptyText) {
  if (value === undefined || value === null || !isFinite(Number(value))) return emptyText || "—"
  var n = Number(value)
  if (n < 10) return n.toFixed(1) + "%"
  return Math.round(n) + "%"
}

function formatTemp(celsius, unit, emptyText) {
  if (celsius === undefined || celsius === null || !isFinite(Number(celsius))) return emptyText || "—"
  var c = Number(celsius)
  if (String(unit || "C").toUpperCase().indexOf("F") === 0) return Math.round(c * 9 / 5 + 32) + "°"
  return Math.round(c) + "°"
}

function formatTempFull(celsius, unit, emptyText) {
  if (celsius === undefined || celsius === null || !isFinite(Number(celsius))) return emptyText || "—"
  var c = Number(celsius)
  if (String(unit || "C").toUpperCase().indexOf("F") === 0) return Math.round(c * 9 / 5 + 32) + "°F"
  return Math.round(c) + "°C"
}

function formatBytes(bytes, emptyText) {
  var n = Number(bytes)
  if (!isFinite(n) || n < 0) return emptyText || "—"
  var value = n
  var unit = "B"
  if (n >= 1024) { value = n / 1024; unit = "KB" }
  if (n >= 1024 * 1024) { value = n / (1024 * 1024); unit = "MB" }
  if (n >= 1024 * 1024 * 1024) { value = n / (1024 * 1024 * 1024); unit = "GB" }
  if (n >= 1024 * 1024 * 1024 * 1024) { value = n / (1024 * 1024 * 1024 * 1024); unit = "TB" }
  if (unit === "B" || unit === "KB" || unit === "MB") return Math.round(value) + " " + unit
  var rounded = value >= 10 ? value.toFixed(1) : value.toFixed(2)
  return String(Number(rounded)) + " " + unit
}

function formatRate(bytesPerSec, emptyText) {
  if (bytesPerSec === undefined || bytesPerSec === null) return emptyText || "—"
  var n = Number(bytesPerSec)
  if (!isFinite(n) || n < 0) return emptyText || "—"
  if (n < 1024) return Math.round(n) + " B/s"
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB/s"
  if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB/s"
  return (n / (1024 * 1024 * 1024)).toFixed(2) + " GB/s"
}

function formatLoad(value) {
  if (value === undefined || value === null || !isFinite(Number(value))) return "—"
  return Number(value).toFixed(2)
}

function metricWarned(kind, snapshot, warnPercent, warnTempC) {
  var cpu = snapshot && snapshot.cpu ? snapshot.cpu : {}
  var memory = snapshot && snapshot.memory ? snapshot.memory : {}
  var gpu = primaryGpu(snapshot)
  var disk = diskForMount(snapshot, "/")
  if (kind === "cpu") return Number(cpu.percent) >= warnPercent || Number(cpu.tempC) >= warnTempC
  if (kind === "memory") return Number(memory.percent) >= warnPercent
  if (kind === "gpu") return !!(gpu && (Number(gpu.percent) >= warnPercent || Number(gpu.tempC) >= warnTempC))
  if (kind === "disk") return !!(disk && Number(disk.percent) >= warnPercent)
  if (kind === "temp") {
    var hottest = snapshot && snapshot.hottest ? snapshot.hottest.celsius : null
    return Number(hottest) >= warnTempC
  }
  return false
}

function anyWarned(snapshot, warnPercent, warnTempC) {
  return metricWarned("cpu", snapshot, warnPercent, warnTempC)
    || metricWarned("memory", snapshot, warnPercent, warnTempC)
    || metricWarned("gpu", snapshot, warnPercent, warnTempC)
    || metricWarned("disk", snapshot, warnPercent, warnTempC)
    || metricWarned("temp", snapshot, warnPercent, warnTempC)
}

function statusPhrase(snapshot, warnPercent, warnTempC) {
  if (!snapshot || snapshot.ok === false && !snapshot.cpu) return "Waiting for sensors"
  var cpu = snapshot.cpu || {}
  var memory = snapshot.memory || {}
  var gpu = primaryGpu(snapshot)
  var hottest = snapshot.hottest ? Number(snapshot.hottest.celsius) : NaN
  if (isFinite(hottest) && hottest >= warnTempC) return "Running hot"
  if (Number(cpu.percent) >= warnPercent || Number(memory.percent) >= warnPercent || (gpu && Number(gpu.percent) >= warnPercent))
    return "Under load"
  if (Number(cpu.percent) >= 70 || Number(memory.percent) >= 70 || (gpu && Number(gpu.percent) >= 70) || (isFinite(hottest) && hottest >= warnTempC - 10))
    return "Working hard"
  return "Running cool"
}

function visibleMetrics(settings, snapshot) {
  var display = String((settings && settings.display) || "All")
  var showCpu = isOn(settings && settings.showCpu, true)
  var showMemory = isOn(settings && settings.showMemory, true)
  var showGpu = isOn(settings && settings.showGpu, true)
  var showDisk = isOn(settings && settings.showDisk, false)
  var showNetwork = isOn(settings && settings.showNetwork, true)
  var showTemp = isOn(settings && settings.showTemp, true)
  var diskMount = (settings && settings.diskMount) || "/"
  var unit = (settings && settings.tempUnit) || "C"
  var compact = isOn(settings && settings.compact, false)
  var useText = String((settings && settings.barStyle) || "Icons") === "Text"
  var cpu = snapshot && snapshot.cpu ? snapshot.cpu : {}
  var memory = snapshot && snapshot.memory ? snapshot.memory : {}
  var gpu = primaryGpu(snapshot)
  var disk = diskForMount(snapshot, diskMount)
  var network = snapshot && snapshot.network ? snapshot.network : {}
  var hottest = snapshot && snapshot.hottest ? snapshot.hottest : null
  var items = []

  function markFor(kind, glyph) {
    if (!useText) return glyph
    if (kind === "cpu") return "CPU"
    if (kind === "memory") return "MEM"
    if (kind === "gpu") return "GPU"
    if (kind === "disk") return "DISK"
    if (kind === "network") return "NET"
    if (kind === "temp") return "TEMP"
    return glyph
  }

  function push(kind, icon, value, detail, available) {
    if (!available) return
    if (display !== "All" && display.toLowerCase() !== kind) return
    items.push({
      kind: kind,
      icon: markFor(kind, icon),
      useText: useText,
      value: value,
      detail: detail || "",
      text: compact || !detail ? value : (value + " " + detail)
    })
  }

  if (display === "CPU" || display === "Memory" || display === "GPU" || display === "Disk" || display === "Network" || display === "Temp") {
    showCpu = display === "CPU"
    showMemory = display === "Memory"
    showGpu = display === "GPU"
    showDisk = display === "Disk"
    showNetwork = display === "Network"
    showTemp = display === "Temp"
  }

  if (showCpu) {
    push(
      "cpu",
      "󰍛",
      formatPercent(cpu.percent),
      showTemp && display === "All" && !compact ? formatTemp(cpu.tempC, unit) : "",
      true
    )
  }
  if (showMemory) {
    push("memory", "󰘚", formatPercent(memory.percent), "", true)
  }
  if (showGpu) {
    push(
      "gpu",
      "󰢮",
      formatPercent(gpu ? gpu.percent : null),
      showTemp && display === "All" && !compact && gpu ? formatTemp(gpu.tempC, unit) : "",
      !!gpu
    )
  }
  if (showDisk) {
    push("disk", "󰋊", formatPercent(disk ? disk.percent : null), "", !!disk)
  }
  if (showNetwork) {
    var hasNet = network.rxRate !== undefined || network.txRate !== undefined
    var netText = "↓" + formatRate(network.rxRate || 0) + "  ↑" + formatRate(network.txRate || 0)
    push("network", "󰈀", netText, "", hasNet)
  }
  if (showTemp && display === "Temp") {
    push("temp", "󰔏", formatTemp(hottest ? hottest.celsius : (cpu.tempC), unit), "", true)
  }
  return items
}

function tooltipLines(snapshot, settings) {
  var unit = (settings && settings.tempUnit) || "C"
  var cpu = snapshot && snapshot.cpu ? snapshot.cpu : {}
  var memory = snapshot && snapshot.memory ? snapshot.memory : {}
  var gpu = primaryGpu(snapshot)
  var disk = diskForMount(snapshot, (settings && settings.diskMount) || "/")
  var network = snapshot && snapshot.network ? snapshot.network : {}
  var lines = []
  lines.push("CPU  " + formatPercent(cpu.percent) + "  " + formatTempFull(cpu.tempC, unit))
  lines.push("RAM  " + formatPercent(memory.percent) + "  " + formatBytes(memory.usedBytes) + " / " + formatBytes(memory.totalBytes))
  if (gpu) {
    lines.push("GPU  " + formatPercent(gpu.percent) + "  " + formatTempFull(gpu.tempC, unit))
    if (gpu.memUsedBytes && gpu.memTotalBytes)
      lines.push("VRAM " + formatBytes(gpu.memUsedBytes) + " / " + formatBytes(gpu.memTotalBytes))
  }
  if (disk) lines.push("Disk " + formatPercent(disk.percent) + "  " + disk.mount)
  if (network.rxRate !== undefined || network.txRate !== undefined) {
    lines.push("NET  ↓" + formatRate(network.rxRate || 0) + "  ↑" + formatRate(network.txRate || 0))
  }
  return lines.join("\n")
}

function verticalLines(items) {
  var lines = []
  for (var i = 0; i < (items || []).length; i++) lines.push(items[i].value)
  return lines
}

function parseExtras(raw) {
  var text = String(raw || "").replace(/^\s+|\s+$/g, "")
  if (!text) return null
  try {
    var data = JSON.parse(text)
    if (!data || typeof data !== "object") return null
    if (!data.processes) data.processes = emptyExtras().processes
    if (!data.processes.cpu) data.processes.cpu = []
    if (!data.processes.memory) data.processes.memory = []
    if (!data.processes.gpu) data.processes.gpu = []
    if (!data.directories || typeof data.directories !== "object") data.directories = {}
    return data
  } catch (e) {
    return null
  }
}

function namedRows(list, valueKey, formatter) {
  var rows = []
  var items = list || []
  for (var i = 0; i < items.length; i++) {
    var item = items[i] || {}
    var name = String(item.name || item.label || "")
    if (!name) continue
    rows.push({ name: name, value: formatter(item[valueKey]) })
  }
  return rows
}

function processCpuRows(extras) {
  return namedRows(extras && extras.processes ? extras.processes.cpu : [], "percent", formatProcessPercent)
}

function processMemoryRows(extras) {
  return namedRows(extras && extras.processes ? extras.processes.memory : [], "bytes", formatBytes)
}

function processGpuRows(extras) {
  return namedRows(extras && extras.processes ? extras.processes.gpu : [], "bytes", formatBytes)
}

function directoryRows(extras, mount) {
  var dirs = extras && extras.directories ? extras.directories : {}
  var entry = dirs[mount || "/"] || dirs["/"] || null
  if (!entry) return []
  var rows = namedRows(entry.items, "bytes", formatBytes)
  if (rows.length === 0 && entry.scanning) return [{ name: "Measuring…", value: "" }]
  return rows
}

if (typeof module !== "undefined") {
  module.exports = {
    clamp: clamp,
    isOn: isOn,
    fileUrlToPath: fileUrlToPath,
    emptySnapshot: emptySnapshot,
    emptyExtras: emptyExtras,
    parseSnapshot: parseSnapshot,
    parseExtras: parseExtras,
    processCpuRows: processCpuRows,
    processMemoryRows: processMemoryRows,
    processGpuRows: processGpuRows,
    directoryRows: directoryRows,
    primaryGpu: primaryGpu,
    diskForMount: diskForMount,
    formatPercent: formatPercent,
    formatProcessPercent: formatProcessPercent,
    formatTemp: formatTemp,
    formatTempFull: formatTempFull,
    formatBytes: formatBytes,
    formatRate: formatRate,
    formatLoad: formatLoad,
    metricWarned: metricWarned,
    anyWarned: anyWarned,
    statusPhrase: statusPhrase,
    visibleMetrics: visibleMetrics,
    tooltipLines: tooltipLines,
    verticalLines: verticalLines
  }
}
