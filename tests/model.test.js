const assert = require("assert")
const M = require("../Model.js")

assert.strictEqual(M.formatPercent(12.4), "12%")
assert.strictEqual(M.formatPercent(null), "—")
assert.strictEqual(M.formatTemp(51.2, "C"), "51°")
assert.strictEqual(M.formatTemp(51.2, "F"), "124°")
assert.strictEqual(M.formatTempFull(45, "C"), "45°C")
assert.strictEqual(M.formatBytes(67017666560), "62.4 GB")
assert.strictEqual(M.formatBytes(1998232485888), "1.82 TB")
assert.strictEqual(M.formatBytes(4132864), "4 MB")
assert.strictEqual(M.formatRate(1024), "1.0 KB/s")
assert.strictEqual(M.formatRate(1048576), "1.0 MB/s")
assert.strictEqual(M.formatRate(null), "—")
assert.strictEqual(M.isOn("On", false), true)
assert.strictEqual(M.isOn("Off", true), false)

const snap = M.parseSnapshot(JSON.stringify({
  ok: true,
  cpu: { percent: 12.3, tempC: 51, load1: 0.4, cores: 24 },
  memory: { percent: 50.5, usedBytes: 33849724928, totalBytes: 67017666560, swapUsedBytes: 0, swapTotalBytes: 1 },
  gpus: [{ name: "NVIDIA GeForce RTX 5090", percent: 4, tempC: 45, memUsedBytes: 2194677760, memTotalBytes: 34196160512 }],
  disks: [{ mount: "/", percent: 16, usedBytes: 1, totalBytes: 2 }],
  network: { rxBytes: 1000000, txBytes: 500000, rxRate: 102400, txRate: 51200 },
  temps: [],
  hottest: { label: "CPU", celsius: 51 }
}))

const icons = M.visibleMetrics({ display: "All", showDisk: "Off", showTemp: "On", showNetwork: "Off", barStyle: "Icons" }, snap)
assert.deepStrictEqual(icons.map((item) => item.kind), ["cpu", "memory", "gpu"])
assert.ok(icons[0].text.indexOf("12%") >= 0)
assert.strictEqual(icons[0].useText, false)

const netDefault = M.visibleMetrics({ display: "All", barStyle: "Icons" }, snap)
assert.deepStrictEqual(netDefault.map((item) => item.kind), ["cpu", "memory", "gpu", "network"])

const text = M.visibleMetrics({ display: "All", showDisk: "Off", showNetwork: "Off", barStyle: "Text" }, snap)
assert.deepStrictEqual(text.map((item) => item.icon), ["CPU", "MEM", "GPU"])
assert.strictEqual(text[0].useText, true)

const withNet = M.visibleMetrics({ display: "All", showDisk: "Off", showNetwork: "On", barStyle: "Icons" }, snap)
assert.deepStrictEqual(withNet.map((item) => item.kind), ["cpu", "memory", "gpu", "network"])
assert.ok(withNet[3].value.indexOf("↓") >= 0)
assert.ok(withNet[3].value.indexOf("↑") >= 0)

assert.strictEqual(M.statusPhrase(snap, 90, 85), "Running cool")
assert.strictEqual(M.statusPhrase({ cpu: { percent: 95 }, memory: {}, hottest: { celsius: 40 } }, 90, 85), "Under load")
assert.strictEqual(M.statusPhrase({ cpu: {}, memory: {}, hottest: { celsius: 90 } }, 90, 85), "Running hot")

const extras = M.parseExtras(JSON.stringify({
  processes: { cpu: [{ name: "chrome", percent: 1.4 }], memory: [], gpu: [] },
  directories: { "/": { items: [{ label: "home", bytes: 1024 }], scanning: false } }
}))
assert.strictEqual(M.processCpuRows(extras)[0].value, "1.4%")
assert.strictEqual(M.directoryRows(extras, "/")[0].name, "home")

console.log("model ok")
