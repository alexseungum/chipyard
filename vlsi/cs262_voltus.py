import os
import shutil
from functools import cached_property
from typing import List, Optional, Tuple

from cs262_power_hook import extract_window, fsdb_max_time_ns
from hammer.config import load_config_from_defaults
from hammer.power.voltus import Voltus
from hammer.vlsi import HammerToolStep, MMMCCorner, TimeValue


class CS262Voltus(Voltus):
    def get_config(self) -> Tuple[List[dict], List[dict]]:
        configs, types = load_config_from_defaults("hammer.power.voltus", types=True)
        return configs + [{"power.voltus.vectorbased": True, "power.voltus.rail": True, "power.voltus.views": []}], types + [{"power.voltus.vectorbased": "bool", "power.voltus.rail": "bool", "power.voltus.views": "list[str]"}]

    @property
    def steps(self) -> List[HammerToolStep]:
        rail = self.get_setting("power.voltus.rail")
        return self.make_steps_from_methods(
            [self.check_level] + ([self.init_technology] if rail else []) + [self.init_design, self.static_power, self.active_power]
            + ([self.static_rail, self.active_rail] if rail else []) + [self.run_voltus, self.hierarchical_power])

    def get_mmmc_spice_corners(self, corner: MMMCCorner) -> List[str]:
        matches = self.filter_for_mmmc(voltage=corner.voltage, temp=corner.temp)
        return [lib.spice_model_file.lib_corner for lib in self.technology.get_available_libraries()
                if lib.spice_model_file is not None and lib.spice_model_file.lib_corner is not None and matches(lib)]

    @staticmethod
    def view_name(corner: MMMCCorner) -> str:
        return "{}.{}_view".format(corner.name, corner.type.name.lower())

    @property
    def view_names(self) -> List[str]:
        views = [self.view_name(corner) for corner in self.get_mmmc_corners()]
        keep = self.get_setting("power.voltus.views") or []
        return [v for v in views if v in keep] if keep else views

    @property
    def tb_scope(self) -> str:
        return "{}/{}".format(self.get_setting("power.inputs.tb_name"), self.get_setting("power.inputs.tb_dut"))

    @cached_property
    def dynamic_windows(self) -> List[Tuple[str, str, str]]:
        starts = self.get_setting("power.inputs.start_times")
        ends = self.get_setting("power.inputs.end_times")
        if starts and ends:
            return [(waveform, "{}ns".format(TimeValue(start).value_in_units("ns")), "{}ns".format(TimeValue(end).value_in_units("ns")))
                    for waveform, start, end in zip(self.waveforms, starts, ends)]
        windows = []
        for waveform in self.waveforms:
            end = fsdb_max_time_ns(os.path.join(os.getcwd(), waveform))
            if end <= 0:
                self.logger.warning("Could not read end time of {}, skipping dynamic vector-based analysis".format(waveform))
                continue
            self.logger.info("Full-simulation window in {}: 0ns to {}ns".format(waveform, end))
            windows.append((waveform, "0ns", "{}ns".format(end)))
        return windows

    def extract_window(self, waveform: str, start: str, end: str) -> str:
        windows = self.attr_getter("_extracted_windows", {})
        if waveform not in windows:
            path = os.path.join(os.getcwd(), waveform)
            start_ns, end_ns = TimeValue(start).value_in_units("ns"), TimeValue(end).value_in_units("ns")
            windows[waveform] = path if start_ns <= 0 and end_ns >= fsdb_max_time_ns(path) else extract_window(self, path, start_ns, end_ns)
            self.attr_setter("_extracted_windows", windows)
        return windows[waveform]

    def report_power_views(self, out_dir: str) -> None:
        views = self.view_names
        if not views:
            self.verbose_append("report_power -out_dir {}".format(out_dir))
        for view in views:
            self.verbose_append("report_power -view {} -out_dir {}.{}".format(view, out_dir, view))

    def read_waveform(self, waveform: str, window: str = "") -> None:
        formats = {".vcd": "vcd", ".vpd": "vcd", ".fsdb": "fsdb", ".shm": "shm", ".trn": "shm"}
        fmt = formats[os.path.splitext(waveform.rstrip(".gz"))[1].lower()]
        self.verbose_append("read_activity_file -reset -format {} {} {} -scope {}".format(
            fmt, os.path.join(os.getcwd(), waveform), window, self.tb_scope))

    def init_design(self) -> bool:
        if not super().init_design():
            return False
        self.verbose_append("set_power_pads -reset")
        for net in self.get_all_power_nets() + self.get_all_ground_nets():
            self.append("""
set pp [open {net}.pp w]
foreach bump [get_db bumps -if {{.net.name == {net}}}] {{
    lassign [get_db $bump .center] x y
    puts $pp "[get_db $bump .name] $x $y AP"
}}
close $pp
""".format(net=net.name))
            self.verbose_append("set_power_pads -net {0} -format xy -file {0}.pp".format(net.name))
        return True

    def fsdb_power(self) -> bool:
        self.verbose_append("set_db power_method static")
        self.verbose_append("set_db power_write_static_currents true")
        self.verbose_append("set_db power_write_db true")
        for waveform in self.waveforms:
            self.read_waveform(waveform)
            self.report_power_views("staticPowerReports.{}".format(os.path.basename(waveform)))
        for waveform, start, end in self.dynamic_windows:
            self.read_waveform(self.extract_window(waveform, start, end), "-start {} -end {}".format(start, end))
            self.report_power_views("windowPowerReports.{}".format(os.path.basename(waveform)))
        return True

    def active_power(self) -> bool:
        self.verbose_append("set_db power_method dynamic_vectorless")
        self.verbose_append("set_dynamic_power_simulation -resolution 500ps")
        self.report_power_views("activePowerReports")

        self.fsdb_power()

        if not self.get_setting("power.voltus.vectorbased"):
            return True
        self.verbose_append("set_db power_method dynamic_vectorbased")
        for waveform, start, end in self.dynamic_windows:
            name = os.path.basename(waveform)
            self.read_waveform(self.extract_window(waveform, start, end), "-start {} -end {}".format(start, end))
            self.report_power_views("activePowerReports.{}".format(name))
            self.verbose_append("report_vector_profile -detailed_report true -out_file activePowerProfile.{}".format(name))
        return True

    def rail_analysis(self, method: str, power_dir: str, output_dir: Optional[str] = None) -> bool:
        corners = self.get_mmmc_corners()
        if not corners:
            return super().rail_analysis(method, power_dir, output_dir)
        if not output_dir:
            output_dir = method + "RailReports"
        accuracy = self.get_setting("power.voltus.rail_accuracy") or ("hd" if self.ran_tech_stdcell_pgv else "xd")
        nets = [net.name for net in self.get_all_power_nets() + self.get_all_ground_nets()]
        for corner in corners:
            view = self.view_name(corner)
            pg_libs = self.get_mmmc_pgv(corner)
            if self.ran_tech_stdcell_pgv:
                pg_libs.append(os.path.join(self.tech_lib_dir, corner.name, "techonly.cl"))
                pg_libs.append(os.path.join(self.stdcell_lib_dir, corner.name, "stdcells.cl"))
            if self.ran_macro_pgv:
                pg_libs.extend(os.path.join(self.macro_lib_dir, corner.name, "macros_{}.cl".format(cell)) for cell in self.macro_pgv_cells)
            self.append("set pg_libs {{}}\nforeach lib {{ {} }} {{ if {{[file exists $lib]}} {{ lappend pg_libs $lib }} }}".format(" ".join(pg_libs)))
            self.verbose_append("set_rail_analysis_config -method {} -accuracy {} -process_techgen_em_rules true -em_peak_analysis true -enable_rlrp_analysis true -gif_resolution high -verbosity true{} -extraction_tech_file {} -power_grid_libraries $pg_libs -analysis_view {} -temperature {}".format(
                method, accuracy, " -enable_sensitivity_analysis true" if method == "static" else "", self.get_mmmc_qrc(corner), view, corner.temp.value))
            self.verbose_append("set_power_data -reset")
            self.verbose_append("set_power_data -format current {{ {} }}".format(" ".join("{}.{}/{}_{}.ptiavg".format(power_dir, view, method, net) for net in nets)))
            self.verbose_append("report_rail -output_dir {}.{} -type domain ALL".format(output_dir, view))
        return True

    def static_rail(self) -> bool:
        passed = self.rail_analysis("static", "staticPowerReports")
        for waveform in self.waveforms:
            name = os.path.basename(waveform)
            passed = self.rail_analysis("static", "staticPowerReports." + name, "staticRailReports." + name) and passed
        return passed

    def active_rail(self) -> bool:
        passed = self.rail_analysis("dynamic", "activePowerReports", "activeRailReports")
        if not self.get_setting("power.voltus.vectorbased"):
            return passed
        for waveform, _, _ in self.dynamic_windows:
            name = os.path.basename(waveform)
            passed = self.rail_analysis("dynamic", "activePowerReports." + name, "activeRailReports." + name) and passed
        return passed

    @property
    def power_report_dirs(self) -> List[str]:
        bases = ["staticPowerReports", "activePowerReports"]
        bases += ["staticPowerReports." + os.path.basename(waveform) for waveform in self.waveforms]
        bases += ["windowPowerReports." + os.path.basename(waveform) for waveform, _, _ in self.dynamic_windows]
        if self.get_setting("power.voltus.vectorbased"):
            bases += ["activePowerReports." + os.path.basename(waveform) for waveform, _, _ in self.dynamic_windows]
        views = self.view_names
        return ["{}.{}".format(base, view) for base in bases for view in views] if views else bases

    def hierarchical_power(self) -> bool:
        for report_dir in self.power_report_dirs:
            path = os.path.join(self.run_dir, report_dir)
            if not os.path.exists(os.path.join(path, "power.db")):
                continue
            tcl = os.path.join(path, "hier_power.tcl")
            self.write_contents_to_path("if {{[catch {{read_power_db -in_file {0}/power.db; report_power -hierarchy all -out_dir {0} -report_prefix hier}} err]}} {{puts \"ERROR: $err\"}}\nexit".format(path), tcl)
            self.run_executable([self.get_setting("power.voltus.voltus_bin"), "-no_gui", "-common_ui", "-log", os.path.join(path, "hier_power.log"), "-overwrite", "-init", tcl], cwd=self.run_dir)
            if os.path.exists(os.path.join(path, "hier.rpt")) and not os.path.exists(os.path.join(path, "power.rpt")):
                shutil.copyfile(os.path.join(path, "hier.rpt"), os.path.join(path, "power.rpt"))
        return True


tool = CS262Voltus
