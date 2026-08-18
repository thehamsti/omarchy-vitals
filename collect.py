#!/usr/bin/env python3
"""Collect a single JSON snapshot of CPU, memory, GPU, disks, and temps.

No third-party dependencies. Designed to run every 1–2s from omarchy-shell.
CPU percent is computed from a previous /proc/stat sample stored in
$XDG_RUNTIME_DIR so this process never sleeps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

SKIP_FS = {
    "autofs",
    "binfmt_misc",
    "bpf",
    "cgroup",
    "cgroup2",
    "configfs",
    "debugfs",
    "devpts",
    "devtmpfs",
    "efivarfs",
    "fusectl",
    "hugetlbfs",
    "mqueue",
    "nsfs",
    "overlay",
    "proc",
    "pstore",
    "ramfs",
    "rpc_pipefs",
    "securityfs",
    "squashfs",
    "sysfs",
    "tmpfs",
    "tracefs",
}

SKIP_MOUNT_PREFIXES = (
    "/boot/efi",
    "/dev",
    "/proc",
    "/run",
    "/snap",
    "/sys",
    "/var/lib/docker",
    "/var/lib/containers",
)

VIRTUAL_TEMP_CHIPS = {
    "acpitz",
    "acpitz_0",
    "iwlwifi",
    "iwlwifi_1_4",
    "r8169",
    "mdio",
}

SKIP_MOUNTS = {"/boot", "/boot/efi", "/efi"}

CPU_TEMP_CHIPS = {
    "coretemp",
    "k10temp",
    "zenpower",
    "cpu_thermal",
    "soc_thermal",
    "cpu-thermal",
    "k10temp-pci-00c3",
}

CPU_TEMP_LABELS = (
    "package id 0",
    "tctl",
    "tdie",
    "tccd1",
    "cpu",
    "physical id 0",
)

NVIDIA_QUERY = (
    "name,uuid,utilization.gpu,utilization.memory,"
    "memory.used,memory.total,temperature.gpu,power.draw,power.limit"
)


def runtime_dir() -> Path:
    raw = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/hamsti-vitals-{os.getuid()}"
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path | str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def read_int(path: Path | str) -> int | None:
    text = read_text(path)
    if text is None:
        return None
    try:
        return int(text.strip().split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def parse_num(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"N/A", "NA", "[N/A]", "[NOT SUPPORTED]"}:
        return None
    token = text.replace(",", "").split()[0]
    token = token.replace("%", "").replace("W", "").replace("C", "")
    try:
        return float(token)
    except ValueError:
        return None


def bytes_from_mib(value: object) -> int | None:
    num = parse_num(value)
    if num is None:
        return None
    return int(num * 1024 * 1024)


def cpu_sample() -> tuple[int, int] | None:
    text = read_text("/proc/stat")
    if not text:
        return None
    first = text.splitlines()[0]
    parts = first.split()
    if not parts or parts[0] != "cpu" or len(parts) < 5:
        return None
    values = [int(x) for x in parts[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return idle, sum(values)


def load_cpu_state(path: Path) -> dict | None:
    raw = read_text(path)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


CPU_MIN_DELTA_SEC = 0.8
CPU_EMA_ALPHA = 0.35


def save_cpu_state(path: Path, idle: int, total: int, percent: float | None) -> None:
    payload = {"idle": idle, "total": total, "ts": time.time(), "percent": percent}
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def collect_cpu() -> dict:
    load1 = load5 = load15 = None
    load = read_text("/proc/loadavg")
    if load:
        parts = load.split()
        if len(parts) >= 3:
            load1, load5, load15 = parse_num(parts[0]), parse_num(parts[1]), parse_num(parts[2])

    cores = os.cpu_count() or 0
    sample = cpu_sample()
    percent = None
    state_path = runtime_dir() / "hamsti-vitals-cpu.json"
    if sample:
        idle, total = sample
        prev = load_cpu_state(state_path) or {}
        prev_percent = parse_num(prev.get("percent"))
        prev_total = int(prev.get("total") or 0)
        prev_idle = int(prev.get("idle") or 0)
        prev_ts = float(prev.get("ts") or 0)
        dt = time.time() - prev_ts if prev_ts else 0.0
        d_total = total - prev_total
        d_idle = idle - prev_idle

        # Two bar instances (one per monitor) can sample a few milliseconds
        # apart and turn a 40ms blip into a fake 80% spike. Reuse the last
        # good reading until a real window has elapsed.
        if prev_ts and dt < CPU_MIN_DELTA_SEC:
            percent = prev_percent
        elif d_total > 0 and prev_total > 0:
            instant = max(0.0, min(100.0, (1.0 - (d_idle / d_total)) * 100.0))
            if prev_percent is None:
                percent = instant
            else:
                percent = CPU_EMA_ALPHA * instant + (1.0 - CPU_EMA_ALPHA) * prev_percent
            save_cpu_state(state_path, idle, total, percent)
        else:
            save_cpu_state(state_path, idle, total, prev_percent)

    return {
        "percent": None if percent is None else round(percent, 1),
        "load1": load1,
        "load5": load5,
        "load15": load15,
        "cores": cores,
    }


def collect_memory() -> dict:
    info: dict[str, int] = {}
    text = read_text("/proc/meminfo") or ""
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        num = parse_num(rest)
        if num is None:
            continue
        info[key] = int(num) * 1024

    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", info.get("MemFree", 0))
    used = max(0, total - available)
    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    swap_used = max(0, swap_total - swap_free)
    percent = (used / total * 100.0) if total else None
    return {
        "percent": None if percent is None else round(percent, 1),
        "usedBytes": used,
        "totalBytes": total,
        "availableBytes": available,
        "swapUsedBytes": swap_used,
        "swapTotalBytes": swap_total,
    }


def iter_hwmon() -> list[dict]:
    chips: list[dict] = []
    root = Path("/sys/class/hwmon")
    if not root.is_dir():
        return chips
    for entry in sorted(root.iterdir()):
        if not entry.name.startswith("hwmon"):
            continue
        name = (read_text(entry / "name") or entry.name).strip()
        sensors: list[dict] = []
        for input_path in sorted(entry.glob("temp*_input")):
            raw = read_int(input_path)
            if raw is None:
                continue
            key = input_path.name[: -len("_input")]
            label = (read_text(entry / f"{key}_label") or key).strip()
            sensors.append(
                {
                    "key": key,
                    "label": label,
                    "celsius": raw / 1000.0,
                }
            )
        if sensors:
            chips.append({"name": name, "path": str(entry), "temps": sensors})
    return chips


def pick_cpu_temp(chips: list[dict]) -> dict | None:
    preferred: list[tuple[int, dict]] = []
    fallback: list[tuple[int, dict]] = []
    for chip in chips:
        chip_name = str(chip.get("name") or "")
        chip_l = chip_name.lower()
        is_cpu_chip = chip_l in CPU_TEMP_CHIPS or chip_l.startswith("coretemp") or chip_l.startswith("k10temp")
        for sensor in chip.get("temps") or []:
            label = str(sensor.get("label") or "")
            rec = {
                "id": "cpu",
                "label": "CPU",
                "chip": chip_name,
                "sensor": label,
                "celsius": sensor.get("celsius"),
            }
            label_l = label.lower()
            if label_l in CPU_TEMP_LABELS:
                preferred.append((CPU_TEMP_LABELS.index(label_l), rec))
            elif is_cpu_chip:
                fallback.append((10, rec))
    if preferred:
        preferred.sort(key=lambda item: item[0])
        return preferred[0][1]
    if fallback:
        return fallback[0][1]
    return None


def pretty_hwmon_label(chip_name: str, label: str, dimm_index: list[int]) -> str:
    chip_l = chip_name.lower()
    label_l = label.lower()
    if chip_l.startswith("spd5118") or chip_l.startswith("jedec") or chip_l.startswith("dimm"):
        dimm_index[0] += 1
        return f"DIMM {dimm_index[0]}"
    if chip_l == "nvme" and label_l == "composite":
        return "NVMe"
    if label and label_l != chip_l and not label_l.startswith("temp"):
        return label
    return chip_name


def collect_hwmon_temps(chips: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    dimm_index = [0]
    for chip in chips:
        chip_name = str(chip.get("name") or "")
        chip_l = chip_name.lower()
        if any(chip_l.startswith(prefix) for prefix in VIRTUAL_TEMP_CHIPS):
            continue
        for sensor in chip.get("temps") or []:
            label = str(sensor.get("label") or chip_name)
            key = (chip_name, label)
            if key in seen:
                continue
            seen.add(key)
            celsius = sensor.get("celsius")
            if celsius is None:
                continue
            pretty = pretty_hwmon_label(chip_name, label, dimm_index)
            out.append(
                {
                    "id": f"{chip_name}:{label}",
                    "label": pretty,
                    "chip": chip_name,
                    "sensor": label,
                    "celsius": celsius,
                }
            )
    return out


def nvidia_gpus() -> list[dict]:
    if not os.environ.get("PATH"):
        return []
    try:
        proc = subprocess.run(
            ["nvidia-smi", f"--query-gpu={NVIDIA_QUERY}", "--format=csv,noheader,nounits"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []

    gpus: list[dict] = []
    for index, line in enumerate(proc.stdout.splitlines()):
        cols = [part.strip() for part in line.split(",")]
        if len(cols) < 7:
            continue
        name, uuid, util, mem_util, mem_used, mem_total, temp = cols[:7]
        power = cols[7] if len(cols) > 7 else None
        limit = cols[8] if len(cols) > 8 else None
        used_b = bytes_from_mib(mem_used)
        total_b = bytes_from_mib(mem_total)
        mem_pct = parse_num(mem_util)
        if mem_pct is None and used_b is not None and total_b:
            mem_pct = used_b / total_b * 100.0
        gpus.append(
            {
                "id": uuid or str(index),
                "index": index,
                "name": name or "NVIDIA GPU",
                "vendor": "nvidia",
                "percent": parse_num(util),
                "memPercent": None if mem_pct is None else round(mem_pct, 1),
                "memUsedBytes": used_b,
                "memTotalBytes": total_b,
                "tempC": parse_num(temp),
                "powerW": parse_num(power),
                "powerLimitW": parse_num(limit),
            }
        )
    return gpus


def drm_cards() -> list[Path]:
    root = Path("/sys/class/drm")
    if not root.is_dir():
        return []
    cards: list[Path] = []
    for entry in sorted(root.iterdir()):
        if not entry.name.startswith("card") or "-" in entry.name:
            continue
        if (entry / "device").is_dir():
            cards.append(entry)
    return cards


def vendor_name(vendor: str | None) -> str | None:
    if not vendor:
        return None
    value = vendor.strip().lower()
    if value in {"0x10de", "10de"}:
        return "nvidia"
    if value in {"0x1002", "1002", "0x1022", "1022"}:
        return "amd"
    if value in {"0x8086", "8086"}:
        return "intel"
    return None


def amd_gpus(existing_names: set[str]) -> list[dict]:
    gpus: list[dict] = []
    for card in drm_cards():
        device = card / "device"
        vendor = vendor_name(read_text(device / "vendor"))
        if vendor != "amd":
            continue
        name = (read_text(device / "product_name") or "").strip() or f"AMD GPU ({card.name})"
        if name in existing_names:
            continue
        used = read_int(device / "mem_info_vram_used")
        total = read_int(device / "mem_info_vram_total")
        busy = parse_num(read_text(device / "gpu_busy_percent"))
        temp = None
        hwmon = device / "hwmon"
        if hwmon.is_dir():
            for chip in sorted(hwmon.iterdir()):
                for label_name, fallback_input in (
                    ("junction", "temp2_input"),
                    ("edge", "temp1_input"),
                ):
                    for label_path in chip.glob("temp*_label"):
                        if (read_text(label_path) or "").strip().lower() == label_name:
                            raw = read_int(chip / label_path.name.replace("_label", "_input"))
                            if raw is not None:
                                temp = raw / 1000.0
                                break
                    if temp is None:
                        raw = read_int(chip / fallback_input)
                        if raw is not None:
                            temp = raw / 1000.0
                    if temp is not None:
                        break
                if temp is not None:
                    break
        mem_pct = (used / total * 100.0) if used is not None and total else None
        gpus.append(
            {
                "id": card.name,
                "index": len(gpus),
                "name": name,
                "vendor": "amd",
                "percent": None if busy is None else round(busy, 1),
                "memPercent": None if mem_pct is None else round(mem_pct, 1),
                "memUsedBytes": used,
                "memTotalBytes": total,
                "tempC": temp,
                "powerW": None,
                "powerLimitW": None,
            }
        )
    return gpus


def collect_gpus() -> list[dict]:
    gpus = nvidia_gpus()
    names = {str(gpu.get("name") or "") for gpu in gpus}
    gpus.extend(amd_gpus(names))
    return gpus


def collect_disks() -> list[dict]:
    text = read_text("/proc/self/mounts") or read_text("/proc/mounts") or ""
    seen_devices: set[str] = set()
    disks: list[dict] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mount, fstype = parts[0], parts[1], parts[2]
        if fstype in SKIP_FS:
            continue
        if not device.startswith("/dev/"):
            continue
        if any(mount == prefix or mount.startswith(prefix + "/") for prefix in SKIP_MOUNT_PREFIXES):
            continue
        if mount in SKIP_MOUNTS:
            continue
        if device in seen_devices:
            continue
        try:
            stat = os.statvfs(mount)
        except OSError:
            continue
        total = stat.f_frsize * stat.f_blocks
        available = stat.f_frsize * stat.f_bavail
        if total <= 0:
            continue
        used = max(0, total - available)
        seen_devices.add(device)
        disks.append(
            {
                "mount": mount,
                "device": device,
                "fstype": fstype,
                "percent": round(used / total * 100.0, 1),
                "usedBytes": used,
                "totalBytes": total,
            }
        )
    disks.sort(key=lambda d: (0 if d["mount"] == "/" else 1, d["mount"]))
    return disks


SKIP_NET_INTERFACES = {"lo", "lo0", "veth", "docker", "br-", "virbr", "vboxnet", "tun", "tap"}


def collect_network() -> dict:
    text = read_text("/proc/net/dev")
    if not text:
        return {"rxBytes": 0, "txBytes": 0, "rxRate": 0, "txRate": 0}
    rx_total = 0
    tx_total = 0
    for line in text.splitlines()[2:]:
        if ":" not in line:
            continue
        iface, rest = line.split(":", 1)
        iface = iface.strip()
        if any(iface.startswith(p) or iface == p for p in SKIP_NET_INTERFACES):
            continue
        parts = rest.split()
        if len(parts) < 10:
            continue
        try:
            rx_total += int(parts[0])
            tx_total += int(parts[8])
        except (ValueError, IndexError):
            continue

    state_path = runtime_dir() / "hamsti-vitals-net.json"
    prev = load_json(state_path)
    rx_rate = 0
    tx_rate = 0
    now = time.time()
    if prev:
        prev_rx = int(prev.get("rxBytes") or 0)
        prev_tx = int(prev.get("txBytes") or 0)
        prev_ts = float(prev.get("ts") or 0)
        dt = now - prev_ts if prev_ts else 0
        if dt > 0.5:
            rx_rate = max(0, (rx_total - prev_rx) / dt)
            tx_rate = max(0, (tx_total - prev_tx) / dt)

    write_json(state_path, {"ts": now, "rxBytes": rx_total, "txBytes": tx_total})
    return {
        "rxBytes": rx_total,
        "txBytes": tx_total,
        "rxRate": round(rx_rate),
        "txRate": round(tx_rate),
    }


def merge_temps(cpu: dict, gpus: list[dict], hwmon_temps: list[dict]) -> list[dict]:
    out: list[dict] = []
    if cpu.get("tempC") is not None:
        out.append(
            {
                "id": "cpu",
                "label": "CPU",
                "chip": cpu.get("tempChip") or "cpu",
                "sensor": cpu.get("tempSensor") or "CPU",
                "celsius": cpu["tempC"],
            }
        )
    for index, gpu in enumerate(gpus):
        if gpu.get("tempC") is None:
            continue
        out.append(
            {
                "id": f"gpu{index}",
                "label": "GPU" if len(gpus) == 1 else f"GPU {index}",
                "chip": gpu.get("vendor") or "gpu",
                "sensor": gpu.get("name") or "GPU",
                "celsius": gpu["tempC"],
            }
        )

    seen_c = {round(float(item["celsius"]), 1) for item in out if item.get("celsius") is not None}
    for item in hwmon_temps:
        celsius = item.get("celsius")
        if celsius is None:
            continue
        chip = str(item.get("chip") or "").lower()
        label = str(item.get("label") or "").lower()
        if chip.startswith("coretemp") or chip.startswith("k10temp") or chip.startswith("zenpower"):
            continue
        if chip in {"nvidia", "amdgpu"} or label in {"edge", "junction"}:
            continue
        rounded = round(float(celsius), 1)
        if rounded in seen_c:
            continue
        seen_c.add(rounded)
        pretty = item.get("label") or item.get("chip") or "Sensor"
        if pretty.lower() == "composite":
            pretty = (item.get("chip") or "NVMe").upper() if item.get("chip") == "nvme" else pretty
            if item.get("chip") == "nvme":
                pretty = "NVMe"
        out.append(
            {
                "id": item.get("id") or pretty,
                "label": pretty,
                "chip": item.get("chip"),
                "sensor": item.get("sensor") or pretty,
                "celsius": celsius,
            }
        )
    return out


def temp_priority(item: dict) -> int:
    ident = str(item.get("id") or "").lower()
    chip = str(item.get("chip") or "").lower()
    label = str(item.get("label") or "").lower()
    if ident == "cpu" or chip.startswith("coretemp") or chip.startswith("k10temp") or chip.startswith("zenpower"):
        return 0
    if ident.startswith("gpu") or chip in {"nvidia", "amdgpu"}:
        return 1
    if "nvme" in chip or label == "nvme":
        return 2
    if label.startswith("dimm") or chip.startswith("spd5118"):
        return 3
    return 8


def pick_hottest(temps: list[dict]) -> dict | None:
    ranked: list[tuple[int, float, dict]] = []
    for item in temps:
        celsius = item.get("celsius")
        if celsius is None:
            continue
        ranked.append((temp_priority(item), -float(celsius), item))
    if not ranked:
        return None
    # Prefer CPU/GPU/NVMe; only fall back to DIMMs or leftovers if those are missing.
    primary = [row for row in ranked if row[0] <= 2]
    pool = primary or ranked
    pool.sort(key=lambda row: row[1])
    return pool[0][2]


TOP_N = 5
DIR_TTL_SEC = 15 * 60
DIR_SCAN_TIMEOUT_SEC = 25
SKIP_DIR_NAMES = {
    "boot",
    "dev",
    "lost+found",
    "media",
    "mnt",
    "proc",
    "run",
    "snap",
    "swap",
    "sys",
    "tmp",
}
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def short_name(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return "?"
    if len(text) > 1 and text[1] == ":" and "\\" in text:
        text = text.split(" --", 1)[0]
        return text.replace("\\", "/").split("/")[-1][:40] or "?"
    token = text.split()[0]
    return token.replace("\\", "/").split("/")[-1][:40] or "?"


def comm_from_cmdline(pid: int, fallback: str) -> str:
    raw = read_text(f"/proc/{pid}/cmdline")
    if not raw:
        return fallback
    parts = [part for part in raw.split("\0") if part]
    if not parts:
        return fallback
    return short_name(parts[0])


def parse_stat(text: str) -> tuple[str, int] | None:
    left = text.find("(")
    right = text.rfind(")")
    if left < 0 or right <= left:
        return None
    comm = text[left + 1 : right]
    rest = text[right + 2 :].split()
    if len(rest) < 13:
        return None
    try:
        return comm, int(rest[11]) + int(rest[12])
    except ValueError:
        return None


def iter_proc_dirs():
    try:
        entries = os.scandir("/proc")
    except OSError:
        return
    with entries:
        for entry in entries:
            if entry.name.isdigit():
                yield int(entry.name), entry.path


def load_json(path: Path) -> dict:
    raw = read_text(path)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def collect_os_processes() -> tuple[list[dict], list[dict]]:
    sample = cpu_sample()
    total = sample[1] if sample else 0
    state_path = runtime_dir() / "hamsti-vitals-procs.json"
    prev = load_json(state_path)
    prev_total = int(prev.get("total") or 0)
    prev_procs = prev.get("procs") if isinstance(prev.get("procs"), dict) else {}
    stale = (time.time() - float(prev.get("ts") or 0)) > 45

    def snapshot_procs() -> list[dict]:
        self_pid = os.getpid()
        rows: list[dict] = []
        for pid, path in iter_proc_dirs():
            if pid == self_pid:
                continue
            stat = read_text(f"{path}/stat")
            if not stat:
                continue
            parsed = parse_stat(stat)
            if not parsed:
                continue
            comm, cpu_time = parsed
            rss = 0
            statm = read_text(f"{path}/statm")
            if statm:
                parts = statm.split()
                if len(parts) > 1:
                    try:
                        rss = int(parts[1]) * PAGE_SIZE
                    except ValueError:
                        rss = 0
            rows.append({"pid": pid, "name": short_name(comm), "cpuTime": cpu_time, "rss": rss})
        return rows

    rows = snapshot_procs()
    if (not prev_procs or stale or prev_total <= 0) and total > 0:
        time.sleep(0.06)
        sample = cpu_sample()
        total = sample[1] if sample else total
        prev_total = int(prev.get("total") or 0) if prev_procs and not stale else 0
        if prev_total <= 0:
            prev_procs = {str(row["pid"]): row["cpuTime"] for row in rows}
            rows = snapshot_procs()

    delta_total = total - prev_total
    cpu_rows: list[dict] = []
    mem_rows: list[dict] = []
    next_procs: dict[str, int] = {}
    for row in rows:
        pid_key = str(row["pid"])
        next_procs[pid_key] = row["cpuTime"]
        prev_time = prev_procs.get(pid_key)
        percent = None
        if prev_time is not None and delta_total > 0:
            percent = max(0.0, min(100.0, (row["cpuTime"] - int(prev_time)) / delta_total * 100.0))
        if percent is not None and percent > 0:
            cpu_rows.append({"pid": row["pid"], "name": row["name"], "percent": round(percent, 1)})
        if row["rss"] > 0:
            mem_rows.append({"pid": row["pid"], "name": row["name"], "bytes": row["rss"]})

    write_json(state_path, {"ts": time.time(), "total": total, "procs": next_procs})
    cpu_rows.sort(key=lambda item: -item["percent"])
    mem_rows.sort(key=lambda item: -item["bytes"])
    cpu_rows = [row for row in cpu_rows if row["percent"] >= 0.1][:TOP_N]
    mem_rows = mem_rows[:TOP_N]
    for row in cpu_rows + mem_rows:
        row["name"] = comm_from_cmdline(row["pid"], row["name"])
    return cpu_rows, mem_rows


def collect_gpu_processes() -> list[dict]:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []

    rows: list[dict] = []
    for line in proc.stdout.splitlines():
        cols = [part.strip() for part in line.split(",")]
        if len(cols) < 3:
            continue
        pid = parse_num(cols[0])
        used = bytes_from_mib(cols[-1])
        if used is None or used <= 0:
            continue
        rows.append(
            {
                "pid": int(pid) if pid is not None else 0,
                "name": short_name(",".join(cols[1:-1])),
                "bytes": used,
            }
        )
    rows.sort(key=lambda item: -item["bytes"])
    return rows[:TOP_N]


def du_cache_path() -> Path:
    return runtime_dir() / "hamsti-vitals-du.json"


def du_lock_path() -> Path:
    return runtime_dir() / "hamsti-vitals-du.lock"


def dir_scan_running() -> bool:
    lock = du_lock_path()
    if not lock.exists():
        return False
    try:
        age = time.time() - lock.stat().st_mtime
    except OSError:
        return False
    if age > 90:
        try:
            lock.unlink()
        except OSError:
            pass
        return False
    return True


def spawn_dir_scan(mounts: list[str]) -> None:
    if not mounts or dir_scan_running():
        return
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--scan-dirs", *mounts],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return


def collect_directories(mounts: list[str]) -> dict:
    cache = load_json(du_cache_path())
    cached_mounts = cache.get("mounts") if isinstance(cache.get("mounts"), dict) else {}
    scanning = dir_scan_running()
    stale: list[str] = []
    out: dict = {}
    now = time.time()
    for mount in mounts:
        entry = cached_mounts.get(mount) if isinstance(cached_mounts.get(mount), dict) else {}
        items = entry.get("items") if isinstance(entry.get("items"), list) else []
        ts = float(entry.get("ts") or 0)
        age = now - ts if ts else 10**9
        if age > DIR_TTL_SEC:
            stale.append(mount)
        out[mount] = {
            "scanning": scanning or (age > DIR_TTL_SEC and not items),
            "items": items[:TOP_N],
            "ts": ts,
        }
    if stale:
        spawn_dir_scan(stale)
    return out


def first_level_dirs(mount: str) -> list[str]:
    paths: list[str] = []
    try:
        entries = os.scandir(mount)
    except OSError:
        return paths
    with entries:
        for entry in entries:
            name = entry.name
            if name in SKIP_DIR_NAMES:
                continue
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            paths.append(entry.path)
    paths.sort()
    return paths


def du_bytes(path: str, timeout: float) -> int | None:
    try:
        proc = subprocess.run(
            ["du", "-s", "-x", "-B1", path],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode not in (0, 1) or not proc.stdout:
        return None
    num = parse_num(proc.stdout.split()[0] if proc.stdout.split() else "")
    return int(num) if num is not None else None


def scan_dirs(mounts: list[str]) -> None:
    try:
        os.nice(19)
    except OSError:
        pass
    lock = du_lock_path()
    try:
        lock.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        return

    cache = load_json(du_cache_path())
    cached_mounts = cache.get("mounts") if isinstance(cache.get("mounts"), dict) else {}
    deadline = time.monotonic() + DIR_SCAN_TIMEOUT_SEC
    try:
        for mount in mounts:
            remaining = deadline - time.monotonic()
            if remaining <= 0.5:
                break
            children = first_level_dirs(mount)
            if not children:
                continue
            per = max(1.5, min(8.0, remaining / max(1, len(children))))
            items: list[dict] = []
            for child in children:
                remaining = deadline - time.monotonic()
                if remaining <= 0.4:
                    break
                used = du_bytes(child, timeout=min(per, remaining))
                if used is None or used <= 0:
                    continue
                items.append(
                    {
                        "path": child,
                        "label": os.path.basename(child.rstrip("/")) or child,
                        "bytes": used,
                    }
                )
            items.sort(key=lambda item: -item["bytes"])
            cached_mounts[mount] = {"ts": time.time(), "items": items[: max(TOP_N, 8)]}
        write_json(du_cache_path(), {"mounts": cached_mounts})
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def collect_extras() -> dict:
    cpu_rows, mem_rows = collect_os_processes()
    disks = collect_disks()
    mounts = [disk["mount"] for disk in disks if disk.get("mount")]
    if not mounts:
        mounts = ["/"]
    return {
        "ok": True,
        "ts": time.time(),
        "processes": {
            "cpu": cpu_rows,
            "memory": mem_rows,
            "gpu": collect_gpu_processes(),
        },
        "directories": collect_directories(mounts),
    }


def collect() -> dict:
    cpu = collect_cpu()
    memory = collect_memory()
    chips = iter_hwmon()
    cpu_temp = pick_cpu_temp(chips)
    if cpu_temp:
        cpu["tempC"] = cpu_temp.get("celsius")
        cpu["tempChip"] = cpu_temp.get("chip")
        cpu["tempSensor"] = cpu_temp.get("sensor")
    else:
        cpu["tempC"] = None
        cpu["tempChip"] = None
        cpu["tempSensor"] = None

    gpus = collect_gpus()
    disks = collect_disks()
    network = collect_network()
    temps = merge_temps(cpu, gpus, collect_hwmon_temps(chips))
    hottest = pick_hottest(temps)

    return {
        "ok": True,
        "ts": time.time(),
        "cpu": cpu,
        "memory": memory,
        "gpus": gpus,
        "disks": disks,
        "network": network,
        "temps": temps,
        "hottest": hottest,
    }


def main() -> int:
    args = sys.argv[1:]
    pretty = "--pretty" in args
    try:
        if "--scan-dirs" in args:
            mounts = [arg for arg in args if arg not in {"--scan-dirs", "--pretty", "--extras"}]
            scan_dirs(mounts or ["/"])
            return 0
        snapshot = collect_extras() if "--extras" in args else collect()
    except Exception as exc:  # pragma: no cover - last-resort guard
        snapshot = {"ok": False, "error": str(exc), "ts": time.time()}
    json.dump(snapshot, sys.stdout, indent=2 if pretty else None, separators=None if pretty else (",", ":"))
    sys.stdout.write("\n")
    return 0 if snapshot.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
