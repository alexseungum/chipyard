#!/usr/bin/env python3
import os
import re
import subprocess
import time
from typing import Callable, List, Tuple

from hammer.vlsi import HammerDriver, HammerTool, HammerPowerTool, TimeValue

VERDI_BIN = os.path.join(os.environ.get("VERDI_HOME", "/tools/synopsys/verdi/V-2023.12-SP1"), "bin")


def _parse_timescale(ts_str: str) -> float:
    ts_str = ts_str.strip().lower()
    m = re.match(r"([\d.]+)\s*(fs|ps|ns|us|ms|s)", ts_str)
    if not m:
        raise ValueError(f"Cannot parse timescale: {ts_str!r}")
    val = float(m.group(1))
    unit_to_ns = {"fs": 1e-6, "ps": 1e-3, "ns": 1.0, "us": 1e3, "ms": 1e6, "s": 1e9}
    return val * unit_to_ns[m.group(2)]


def fsdb_max_time_ns(fsdb_path: str) -> float:
    result = subprocess.run([os.path.join(VERDI_BIN, "fsdbdebug"), "-info", fsdb_path], capture_output=True, text=True)
    m = re.search(r"maximum xtag\s*:.*\(([\d.]+\s*(?:fs|ps|ns|us|ms|s))\)", result.stdout + result.stderr)
    return _parse_timescale(m.group(1)) if m else 0.0


def power_windows(ht: HammerTool) -> List[Tuple[str, float, float]]:
    waveforms = ht.get_setting("power.inputs.waveforms", []) or []
    starts = ht.get_setting("power.inputs.start_times", []) or []
    ends = ht.get_setting("power.inputs.end_times", []) or []
    return [(w, TimeValue(s).value_in_units("ns"), TimeValue(e).value_in_units("ns")) for w, s, e in zip(waveforms, starts, ends)]


def extract_window(ht: HammerTool, fsdb_path: str, t_start_ns: float, t_end_ns: float) -> str:
    if not fsdb_path.endswith(".fsdb"):
        return fsdb_path
    os.makedirs(ht.run_dir, exist_ok=True)
    windowed = os.path.join(ht.run_dir, os.path.basename(fsdb_path).replace(".fsdb", ".window.fsdb"))
    for _ in range(2):
        if os.path.exists(windowed):
            os.unlink(windowed)
        result = subprocess.run(
            [os.path.join(VERDI_BIN, "fsdbextract"), fsdb_path, "-bt", f"{t_start_ns}ns", "-et", f"{t_end_ns}ns", "-o", windowed],
            capture_output=True, text=True, cwd=ht.run_dir
        )
        if result.returncode == 0 and os.path.exists(windowed) and fsdb_max_time_ns(windowed) >= t_end_ns - 1e-3:
            ht.logger.info(f"power_window_hook: extracted window to {windowed}")
            return windowed
        ht.logger.warning(f"power_window_hook: fsdbextract output does not reach {t_end_ns} ns: {result.stderr}")
    ht.logger.warning("power_window_hook: fsdbextract failed twice, reading full FSDB")
    return fsdb_path


def power_window_hook(ht: HammerTool) -> bool:
    assert isinstance(ht, HammerPowerTool)
    if "joules" not in ht.name:
        return True
    if getattr(ht, "_power_window_done", False):
        return True
    ht._power_window_done = True

    windows = power_windows(ht)
    if not windows:
        return True

    report_configs = []
    for waveform, t_start_ns, t_end_ns in windows:
        fsdb_path = waveform if os.path.isabs(waveform) else os.path.join(os.getcwd(), waveform)
        report_stem = '.'.join(os.path.basename(waveform).split('.')[:-1]) + "_window"
        report_configs.append({
            "waveform_path": extract_window(ht, fsdb_path, t_start_ns, t_end_ns),
            "start_time": f"{t_start_ns:.3f} ns",
            "end_time": f"{t_end_ns:.3f} ns",
            "output_formats": ["report"],
            "report_stem": report_stem,
        })
        ht.logger.info(f"power_window_hook: window {t_start_ns:.3f}ns to {t_end_ns:.3f}ns, report_stem={report_stem}")

    existing = ht.get_setting("power.inputs.report_configs", nullvalue=[]) or []
    ht.set_setting("power.inputs.report_configs", existing + report_configs)
    return True


def timing_funcs(kind: str) -> Tuple[Callable[[HammerDriver], None], Callable[[HammerDriver], None]]:
    start = {}

    def pre(driver: HammerDriver) -> None:
        start["t"] = time.time()

    def post(driver: HammerDriver) -> None:
        end = time.time()
        level = driver.database.get_setting(f"{kind}.inputs.level")
        key = "sim.inputs.benchmarks" if kind == "sim" else "power.inputs.waveforms"
        paths = driver.database.get_setting(key) or [""]
        workload = os.path.basename(paths[0]).split(".")[0]
        tool = driver.sim_tool if kind == "sim" else driver.power_tool
        log = os.path.join(driver.obj_dir, "power-timing.csv")
        new = not os.path.exists(log)
        with open(log, "a") as f:
            if new:
                f.write("kind,level,tool,workload,start,end,seconds\n")
            f.write(",".join([
                kind, str(level), tool.name if tool else "", workload,
                time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(start["t"])),
                time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(end)),
                f"{end - start['t']:.0f}",
            ]) + "\n")

    return pre, post
