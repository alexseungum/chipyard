import os
import re
import shutil
import time
from typing import List, Optional, Tuple

import hammer.tech as hammer_tech
import power_reports
from hammer.config import load_config_from_defaults
from hammer.power.joules import Joules
from hammer.vlsi import FlowLevel, HammerToolStep

LEVEL_NAMES = {FlowLevel.RTL: "rtl", FlowLevel.SYN: "syn"}


class CS262Joules(Joules):
    def get_config(self) -> Tuple[List[dict], List[dict]]:
        configs, types = load_config_from_defaults("hammer.power.joules", types=True)
        return configs + [power_reports.DEFAULTS, {"power.joules.ple": True, "power.joules.window_only": False}], types + [power_reports.TYPES, {"power.joules.ple": "bool", "power.joules.window_only": "bool"}]

    @property
    def db_dir(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(self.run_dir)), f"power-{LEVEL_NAMES[self.level]}-rundir")

    @property
    def db_names(self) -> List[str]:
        return ["pre_synthesize_design", "pre_report_power"] if self.level == FlowLevel.RTL else ["pre_report_power"]

    def db_valid(self) -> bool:
        dbs = [os.path.join(self.db_dir, n) for n in self.db_names]
        if not all(os.path.isfile(d) for d in dbs):
            return False
        inputs = [f for f in self.input_files if os.path.exists(f)]
        newest = max((os.path.getmtime(f) for f in inputs), default=0.0)
        return min(os.path.getmtime(d) for d in dbs) >= newest

    @property
    def ple(self) -> bool:
        return self.level == FlowLevel.SYN and bool(self.get_setting("power.joules.ple"))

    @property
    def window_only(self) -> bool:
        return bool(self.get_setting("power.joules.window_only")) and bool(self.get_power_report_configs())

    def report_power(self) -> bool:
        if not self.window_only:
            return super().report_power()
        waveforms = self.waveforms
        self.waveforms = []
        try:
            return super().report_power()
        finally:
            self.waveforms = waveforms

    @property
    def use_db(self) -> bool:
        if not hasattr(self, "_cs262_use_db"):
            self._cs262_use_db = os.path.abspath(self.run_dir) != self.db_dir and not self.ple and self.db_valid()
        return self._cs262_use_db

    @property
    def steps(self) -> List[HammerToolStep]:
        if self.use_db:
            return self.make_steps_from_methods([self.report_power])
        return super().steps

    def db_path(self, name: str) -> str:
        return os.path.join(self.db_dir, name) if self.use_db else name

    def block_append(self, cmds: str, clean: bool = True, verbose: bool = True) -> bool:
        rtl = self.level == FlowLevel.RTL
        if cmds == "read_db pre_report_power":
            if rtl:
                super().block_append(f"set_rtl_stim_to_gate_config -init {self.db_path('pre_synthesize_design')} -keep_libraries", clean, verbose)
            appended = True if self.ple else super().block_append(f"read_db {self.db_path('pre_report_power')}", clean, verbose)
            super().block_append("create_clock_tree -name cs262_clock_tree -infer_clock_buffers -fanout compute", clean, verbose)
            return appended
        if self.ple and cmds.startswith("read_netlist "):
            self.append_ple(clean, verbose)
        if rtl and cmds.startswith("read_stimulus "):
            cmds += " -resim_cg_enables"
        appended = super().block_append(cmds, clean, verbose)
        m = re.match(r"report_power -stims (\S+) .*-by_hierarchy .*-out (\S+)\.hier\.power\.rpt$", cmds)
        if m:
            self.append_block_categories(m.group(1), m.group(2), clean, verbose)
        return appended

    def append_block_categories(self, stim: str, stem: str, clean: bool, verbose: bool) -> None:
        top = self.get_setting("power.inputs.top_module")
        for b in power_reports.category_blocks(self.get_setting("power.reports.blocks", [])):
            inst = "/{}/{}".format(top, b["inst"].strip("/"))
            super().block_append(f"catch {{report_power -stims {stim} -by_category -inst {inst} -unit mW -out {stem}.cat.{b['name']}.rpt}}", clean, verbose)

    def append_ple(self, clean: bool, verbose: bool) -> None:
        lefs = self.technology.read_libs([hammer_tech.filters.lef_filter], hammer_tech.HammerTechnologyUtils.to_plain_item)
        qrcs = self.technology.read_libs([hammer_tech.filters.qrc_tech_filter], hammer_tech.HammerTechnologyUtils.to_plain_item)
        super().block_append("read_physical -lef {{ {} }}".format(" ".join(lefs)), clean, verbose)
        if qrcs:
            super().block_append(f"set_db qrc_tech_file {{ {qrcs[0]} }}", clean, verbose)
        super().block_append("set_db interconnect_mode ple", clean, verbose)

    def publish_db(self, since: float) -> None:
        if self.use_db or self.ple or os.path.abspath(self.run_dir) == self.db_dir:
            return
        srcs = [os.path.join(self.run_dir, n) for n in self.db_names]
        if not all(os.path.isfile(s) and os.path.getmtime(s) >= since for s in srcs):
            return
        os.makedirs(self.db_dir, exist_ok=True)
        for name, src in zip(self.db_names, srcs):
            dst = os.path.join(self.db_dir, name)
            tmp = f"{dst}.tmp{os.getpid()}"
            shutil.copy2(src, tmp)
            os.replace(tmp, dst)
        self.logger.info(f"Published Joules checkpoints to {self.db_dir}")

    def expected_reports(self) -> int:
        return (0 if self.window_only else len(self.waveforms)) + len(self.get_power_report_configs())

    def run_joules(self) -> bool:
        start = time.time()
        if not super().run_joules():
            return False
        runtime = time.time() - start
        reports = os.path.join(self.run_dir, "reports")
        stems = power_reports.joules_stems(reports, start)
        if len(stems) < self.expected_reports():
            self.logger.error(f"Joules wrote {len(stems)} of {self.expected_reports()} power reports in {reports}; see {self.run_dir}/joules_work/joules.log")
            return False
        self.publish_db(start)
        blocks = self.get_setting("power.reports.blocks", [])
        for stem in stems:
            power_reports.write_joules_reports(reports, stem, blocks, runtime)
        return True


tool = CS262Joules
