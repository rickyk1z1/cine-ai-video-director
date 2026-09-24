#!/usr/bin/env python3
"""Read a minimal hardware inventory; emit JSON without installing dependencies.

Usage: python probe_hardware.py [--output /workspace/hardware-profile.json]
No Blender changes, network access, serial numbers, UUIDs, or default file writes.
Hardware tiers are provisional hints; only a Blender benchmark can calibrate them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone

GIB = 1024 ** 3
MIB = 1024 ** 2

# Fixed, read-only CIM properties. AdapterRAM is intentionally excluded: it can
# truncate VRAM on Windows and does not prove dedicated or shared memory capacity.
WINDOWS_QUERY = r"""
$ErrorActionPreference = 'Stop'
$cpuInfo = @(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
$osInfo = Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory
$gpuInfo = @(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterCompatibility,DriverVersion)
@{cpu=$cpuInfo; ram=$osInfo; gpus=$gpuInfo} | ConvertTo-Json -Depth 4 -Compress
"""


def run_readonly(args: list[str], timeout: int = 12) -> str | None:
    """Run only callers' fixed inventory commands; never invoke a shell."""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def positive_int(value) -> int | None:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def mib_bytes(value: str) -> int | None:
    try:
        parsed = float(value.strip())
        return int(parsed * MIB) if 0 <= parsed < 1e8 else None
    except (ValueError, OverflowError):
        return None


def unknown_gpu(name: str, vendor: str | None, driver: str | None, source: str):
    return {
        "name": name, "vendor": vendor,
        "dedicated_vram_total_bytes": None,
        "dedicated_vram_free_bytes": None,
        "driver_version": driver, "memory_kind": "unknown",
        "source": source, "confidence": "partial",
    }


def windows_inventory(profile: dict) -> None:
    ps = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not ps:
        return
    raw = run_readonly([ps, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_QUERY])
    if not raw:
        return
    try:
        info = json.loads(raw.lstrip("\ufeff"))
        processors = info.get("cpu", [])
        if isinstance(processors, dict):
            processors = [processors]
        cores = [positive_int(p.get("NumberOfCores")) for p in processors]
        threads = [positive_int(p.get("NumberOfLogicalProcessors")) for p in processors]
        if processors:
            profile["cpu"].update({
                "name": "; ".join(str(p.get("Name", "unknown")).strip() for p in processors),
                "physical_cores": sum(cores) if all(cores) else None,
                "logical_threads": sum(threads) if all(threads) else profile["cpu"]["logical_threads"],
                "source": "windows_cim", "confidence": "measured",
            })
        ram = info.get("ram") or {}
        total_kib = positive_int(ram.get("TotalVisibleMemorySize"))
        available_kib = positive_int(ram.get("FreePhysicalMemory"))
        profile["ram"].update({
            "total_bytes": total_kib * 1024 if total_kib else None,
            "available_bytes": available_kib * 1024 if available_kib else None,
            "source": "windows_cim", "confidence": "measured" if total_kib else "unknown",
        })
        gpu_info = info.get("gpus", [])
        if isinstance(gpu_info, dict):
            gpu_info = [gpu_info]
        for gpu in gpu_info:
            profile["gpus"].append(unknown_gpu(
                str(gpu.get("Name") or "unknown"), gpu.get("AdapterCompatibility"),
                gpu.get("DriverVersion"), "windows_cim",
            ))
        profile["source"].append("windows_cim")
    except (TypeError, ValueError, AttributeError):
        profile["warnings"].append("Windows CIM inventory could not be decoded; unavailable values remain null.")


def linux_inventory(profile: dict) -> None:
    try:
        entries = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            entries[key] = positive_int(value.split()[0])
        total, available = entries.get("MemTotal"), entries.get("MemAvailable")
        profile["ram"].update({
            "total_bytes": total * 1024 if total else None,
            "available_bytes": available * 1024 if available else None,
            "source": "/proc/meminfo", "confidence": "measured" if total else "unknown",
        })
        profile["source"].append("/proc/meminfo")
    except (OSError, ValueError, IndexError):
        pass
    try:
        # Read only CPU model/topology keys; never report processor serial fields.
        records = Path("/proc/cpuinfo").read_text().split("\n\n")
        topology, model = set(), None
        for record in records:
            fields = dict(line.split(":", 1) for line in record.splitlines() if ":" in line)
            fields = {key.strip(): value.strip() for key, value in fields.items()}
            model = model or fields.get("model name") or fields.get("Processor")
            if "physical id" in fields and "core id" in fields:
                topology.add((fields["physical id"], fields["core id"]))
        profile["cpu"].update({
            "name": model or profile["cpu"]["name"],
            "physical_cores": len(topology) or None,
            "source": "/proc/cpuinfo", "confidence": "measured" if model else "partial",
        })
        profile["source"].append("/proc/cpuinfo")
    except (OSError, ValueError):
        pass


def mac_inventory(profile: dict) -> None:
    sysctl = shutil.which("sysctl")
    if not sysctl:
        return
    values = {key: run_readonly([sysctl, "-n", key], timeout=4) for key in (
        "machdep.cpu.brand_string", "hw.physicalcpu", "hw.logicalcpu", "hw.memsize"
    )}
    profile["cpu"].update({
        "name": values["machdep.cpu.brand_string"] or profile["cpu"]["name"],
        "physical_cores": positive_int(values["hw.physicalcpu"]),
        "logical_threads": positive_int(values["hw.logicalcpu"]) or profile["cpu"]["logical_threads"],
        "source": "sysctl", "confidence": "partial",
    })
    total = positive_int(values["hw.memsize"])
    profile["ram"].update({
        "total_bytes": total, "source": "sysctl", "confidence": "partial" if total else "unknown",
    })
    profile["source"].append("sysctl")
    profile["warnings"].append("Available RAM and GPU/shared-memory capacity are unknown; system RAM is never counted as dedicated VRAM.")


def nvidia_inventory(profile: dict) -> None:
    executable = shutil.which("nvidia-smi")
    if not executable and os.name == "nt":
        # Existing vendor/system paths only; never download or install a utility.
        candidates = [
            Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe",
        ]
        executable = next((str(path) for path in candidates if path.is_file()), None)
    if not executable:
        return
    raw = run_readonly([
        executable, "--query-gpu=name,driver_version,memory.total,memory.free",
        "--format=csv,noheader,nounits",
    ], timeout=8)
    if not raw:
        return
    matched = set()
    for row in csv.reader(io.StringIO(raw)):
        if len(row) != 4:
            continue
        name, driver, total_text, free_text = [cell.strip() for cell in row]
        total, free = mib_bytes(total_text), mib_bytes(free_text)
        if total == 0:
            total = None
        if total is None or (free is not None and free > total):
            free = None
        match = next((i for i, gpu in enumerate(profile["gpus"])
                      if i not in matched and gpu["name"].casefold() == name.casefold()), None)
        gpu = {
            "name": name, "vendor": "NVIDIA", "driver_version": driver or None,
            "dedicated_vram_total_bytes": total, "dedicated_vram_free_bytes": free,
            "memory_kind": "dedicated" if total else "unknown",
            "source": "nvidia-smi", "confidence": "measured" if total else "partial",
        }
        if match is None:
            profile["gpus"].append(gpu)
            matched.add(len(profile["gpus"]) - 1)
        else:
            profile["gpus"][match] = gpu
            matched.add(match)
    if matched:
        profile["source"].append("nvidia-smi")


def choose_tier(profile: dict) -> tuple[str, list[str]]:
    """Conservative inventory hint, not a viewport-performance prediction."""
    ram = profile["ram"]["total_bytes"]
    gpus = profile["gpus"]
    capacities = [gpu["dedicated_vram_total_bytes"] for gpu in gpus]
    threads = profile["cpu"]["logical_threads"]
    if not ram or not capacities or any(value is None for value in capacities):
        return "low", ["RAM or a possible GPU's dedicated VRAM is unknown; start low until Blender device selection and calibration are verified."]
    # Device selection has not been verified. Never add multiple GPU capacities.
    vram = min(capacities)
    if ram >= 32 * GIB and vram >= 12 * GIB and threads and threads >= 16:
        tier = "high"
    elif ram >= 16 * GIB and vram >= 6 * GIB and threads and threads >= 8:
        tier = "mid"
    else:
        tier = "low"
    basis = ["Uses total RAM, CPU threads, and the smallest detected dedicated GPU capacity; GPU capacities are never summed."]
    free_ram = profile["ram"]["available_bytes"]
    free_gpu = [gpu["dedicated_vram_free_bytes"] for gpu in gpus]
    known_free_gpu = [value for value in free_gpu if value is not None]
    if free_ram is not None and free_ram < 4 * GIB or known_free_gpu and min(known_free_gpu) < 2 * GIB:
        tier = "low"
        basis.append("Current free memory is low; candidate tier reduced to low.")
    elif tier == "high" and (free_ram is not None and free_ram < 8 * GIB or known_free_gpu and min(known_free_gpu) < 4 * GIB):
        tier = "mid"
        basis.append("Current free memory limits headroom; candidate tier reduced to mid.")
    basis.append("Heuristic only: verify Blender's active GPU and benchmark the intended viewport/resolution before assigning final budgets.")
    return tier, basis


def collect_profile() -> dict:
    profile = {
        "schema_version": "1.1", "profile_id": "pending",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "os": {"system": platform.system(), "release": platform.release(), "architecture": platform.machine()},
        "cpu": {"name": platform.processor() or None, "physical_cores": None,
                "logical_threads": os.cpu_count(), "source": "python_stdlib", "confidence": "fallback"},
        "ram": {"total_bytes": None, "available_bytes": None, "source": "unknown", "confidence": "unknown"},
        "gpus": [], "source": ["python_stdlib"], "confidence": "unknown",
        "tier_hint": "low", "tier_basis": [], "blender": None,
        "calibration": {"status": "not_run", "measurement_method": "hardware_inventory_only",
                        "viewport_playback_verified": False, "viewport_fps": None, "depsgraph_ms_p95": None},
        "warnings": ["Blender's active viewport/render device has not been verified.",
                     "Hardware inventory and free-memory snapshots do not establish playback FPS."],
    }
    inventory = {"Windows": windows_inventory, "Linux": linux_inventory, "Darwin": mac_inventory}.get(platform.system())
    if inventory:
        inventory(profile)
    nvidia_inventory(profile)
    profile["tier_hint"], profile["tier_basis"] = choose_tier(profile)
    if profile["ram"]["total_bytes"]:
        profile["confidence"] = "measured_partial"
    elif profile["cpu"]["logical_threads"]:
        profile["confidence"] = "fallback"
    # Hash only non-unique model/capacity data, excluding transient memory pressure,
    # paths, machine names and unique hardware identifiers. This is an inventory
    # cache hint; Blender version/device/backend/resolution must key calibration.
    identity = {
        "os": profile["os"], "cpu": profile["cpu"], "ram_total_bytes": profile["ram"]["total_bytes"],
        "gpus": [{key: gpu[key] for key in ("name", "dedicated_vram_total_bytes", "driver_version")}
                 for gpu in profile["gpus"]],
    }
    profile["profile_id"] = "hw-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    return profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional explicit workspace JSON path; otherwise only stdout is written.")
    args = parser.parse_args()
    document = json.dumps(collect_profile(), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document, encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
