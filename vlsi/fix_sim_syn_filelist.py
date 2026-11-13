#!/usr/bin/env python3
"""
fix_sim_syn_filelist.py
Rewrites a gate-level sim input JSON so the testharness/support files appear
first and the stage-specific gate netlist(s) are appended at the end.

Usage:
    python3 fix_sim_syn_filelist.py <sim-input-files.yml> <sim-stage-input.json>
"""

import json
import re
import sys

def load_support_files(sim_inputs_yml):
    with open(sim_inputs_yml) as f:
        return [
            m.group(1)
            for line in f
            for m in [re.match(r'\s+- "(.+)"', line)]
            if m
        ]

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <sim-input-files.yml> <sim-stage-input.json>")
        sys.exit(1)

    sim_inputs_yml = sys.argv[1]
    sim_stage_input_json = sys.argv[2]

    support_files = load_support_files(sim_inputs_yml)

    with open(sim_stage_input_json) as f:
        d = json.load(f)
    stage_input_files = d.get("sim.inputs.input_files", [])
    if not stage_input_files:
        print(f"Expected sim.inputs.input_files in {sim_stage_input_json}")
        sys.exit(1)

    stage_input_file_set = set(stage_input_files)
    ordered_support_files = [f for f in support_files if f not in stage_input_file_set]
    d["sim.inputs.input_files"] = ordered_support_files + stage_input_files

    with open(sim_stage_input_json, "w") as f:
        json.dump(d, f, indent=4)
        f.write("\n")

    print(
        f"Wrote {len(ordered_support_files)} support files followed by "
        f"{len(stage_input_files)} gate-level netlist file(s)"
    )

if __name__ == "__main__":
    main()
