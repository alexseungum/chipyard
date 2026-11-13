POWER_CONF = $(OBJ_DIR)/power-inputs.yml
POWER_RTL_CONF = $(OBJ_DIR)/power-rtl-inputs.yml
POWER_SYN_CONF = $(OBJ_DIR)/power-syn-inputs.yml
POWER_PAR_CONF = $(OBJ_DIR)/power-par-inputs.yml
POWER_PAR_HIER_CONF = $(OBJ_DIR)/power-par-$(VLSI_TOP)-inputs.yml

POWER_TOP ?= $(VLSI_TOP)
POWER_DUT ?= $(VLSI_MODEL_DUT_NAME)
POWER_CLOCK_PERIOD ?= 2.0ns
POWER_START_TIME ?= 0ns
POWER_END_TIME ?=
VOLTUS_CONF ?= $(vlsi_dir)/voltus.yml
VOLTUS_SKIP_VECTORBASED ?=
VOLTUS_SKIP_RAIL ?=
VOLTUS_POWER_ONLY ?=
JOULES_WINDOW_ONLY ?=
POWER_RUNDIR ?=
POWER_WAVEFORM = $(call get_sim_out_name,$(BINARY)).$(if $(USE_VPD),vpd,fsdb)
POWER_TEST = $(basename $(notdir $(BINARY)))
POWER_BLOCKS_CONF ?= $(vlsi_dir)/power-blocks.yml
power_rundir = $(or $(POWER_RUNDIR),$(OBJ_DIR)/power-$(1)-rundir$(if $(BINARY),-$(POWER_TEST)))

.PHONY: $(POWER_CONF) $(POWER_RTL_CONF) $(POWER_SYN_CONF) $(POWER_PAR_CONF) $(POWER_PAR_HIER_CONF)

$(POWER_CONF): $(VLSI_RTL) check-binary
	mkdir -p $(dir $@)
	echo "power.inputs:" > $@
	echo "  top_module: $(POWER_TOP)" >> $@
	echo "  tb_name: TestDriver" >> $@
	echo "  tb_dut: 'testHarness/$(POWER_DUT)'" >> $@
	echo "  saifs: []" >> $@
ifneq ($(POWER_END_TIME),)
	echo "  start_times: ['$(POWER_START_TIME)']" >> $@
	echo "  end_times: ['$(POWER_END_TIME)']" >> $@
else
	echo "  start_times: []" >> $@
	echo "  end_times: []" >> $@
endif
ifneq ($(POWER_TOP),$(VLSI_TOP))
	echo "vlsi.inputs.clocks: [{name: clock, period: '$(POWER_CLOCK_PERIOD)'}]" >> $@
	echo "vlsi.inputs.delays: []" >> $@
	echo "vlsi.inputs.custom_sdc_constraints: []" >> $@
endif

$(POWER_RTL_CONF): $(VLSI_RTL)
	echo "vlsi.core.power_tool: cs262_joules" > $@
	echo "power.inputs:" >> $@
	echo "  level: rtl" >> $@
	$(if $(BINARY),echo "  waveforms: ['$(POWER_WAVEFORM)']" >> $@)
	echo "  input_files:" >> $@
	for x in $$(cat $(VLSI_RTL)); do \
		echo '    - "'$$x'"' >> $@; \
	done
	$(if $(JOULES_WINDOW_ONLY),echo "power.joules.window_only: true" >> $@)

$(POWER_SYN_CONF): $(VLSI_RTL)
	echo "vlsi.core.power_tool: cs262_joules" > $@
	echo "power.inputs:" >> $@
	echo "  level: syn" >> $@
	$(if $(BINARY),echo "  waveforms: ['$(POWER_WAVEFORM)']" >> $@)
	$(if $(JOULES_WINDOW_ONLY),echo "power.joules.window_only: true" >> $@)

$(POWER_PAR_CONF): $(VLSI_RTL)
	echo "vlsi.core.power_tool: hammer.power.voltus" > $@
	echo "power.inputs:" >> $@
	echo "  level: par" >> $@
	$(if $(BINARY),echo "  waveforms: ['$(POWER_WAVEFORM)']" >> $@)
	echo "  database: '$(OBJ_DIR)/par-rundir/$(VLSI_TOP)_FINAL'" >> $@
	$(if $(VOLTUS_SKIP_VECTORBASED)$(VOLTUS_POWER_ONLY),echo "power.voltus.vectorbased: false" >> $@)
	$(if $(VOLTUS_SKIP_RAIL)$(VOLTUS_POWER_ONLY),echo "power.voltus.rail: false" >> $@)

$(POWER_PAR_HIER_CONF): $(VLSI_RTL)
	echo "vlsi.core.power_tool: hammer.power.voltus" > $@
	echo "power.inputs:" >> $@
	echo "  level: par" >> $@
	$(if $(BINARY),echo "  waveforms: ['$(POWER_WAVEFORM)']" >> $@)
	echo "  database: '$(OBJ_DIR)/par-$(VLSI_TOP)/$(VLSI_TOP)_FINAL'" >> $@
	$(if $(VOLTUS_SKIP_VECTORBASED)$(VOLTUS_POWER_ONLY),echo "power.voltus.vectorbased: false" >> $@)
	$(if $(VOLTUS_SKIP_RAIL)$(VOLTUS_POWER_ONLY),echo "power.voltus.rail: false" >> $@)

power-rtl: $(POWER_CONF) $(POWER_RTL_CONF) sim-rtl-debug
power-rtl-$(VLSI_TOP): $(POWER_CONF) $(POWER_RTL_CONF) sim-rtl-debug-$(VLSI_TOP)
power-rtl: override HAMMER_POWER_EXTRA_ARGS += -p $(POWER_CONF) -p $(POWER_RTL_CONF) -p $(POWER_BLOCKS_CONF)
power-rtl-$(VLSI_TOP): override HAMMER_POWER_EXTRA_ARGS += -p $(POWER_CONF) -p $(POWER_RTL_CONF) -p $(POWER_BLOCKS_CONF)
redo-power-rtl: $(POWER_CONF) $(POWER_RTL_CONF)
redo-power-rtl-$(VLSI_TOP): $(POWER_CONF) $(POWER_RTL_CONF)
redo-power-rtl: override HAMMER_EXTRA_ARGS += -p $(POWER_CONF) -p $(POWER_RTL_CONF) -p $(POWER_BLOCKS_CONF)
power-rtl redo-power-rtl: export HAMMER_POWER_RUNDIR = $(call power_rundir,rtl)
redo-power-rtl-$(VLSI_TOP): override HAMMER_EXTRA_ARGS += -p $(POWER_CONF) -p $(POWER_RTL_CONF) -p $(POWER_BLOCKS_CONF)

power-syn: $(POWER_CONF) $(POWER_SYN_CONF) sim-syn-debug
power-syn-$(VLSI_TOP): $(POWER_CONF) $(POWER_SYN_CONF) sim-syn-debug-$(VLSI_TOP)
power-syn: override HAMMER_POWER_EXTRA_ARGS += -p $(TOOLS_CONF) -p $(POWER_CONF) -p $(POWER_SYN_CONF) -p $(POWER_BLOCKS_CONF)
power-syn-$(VLSI_TOP): override HAMMER_POWER_EXTRA_ARGS += -p $(TOOLS_CONF) -p $(POWER_CONF) -p $(POWER_SYN_CONF) -p $(POWER_BLOCKS_CONF)
redo-power-syn: $(POWER_CONF) $(POWER_SYN_CONF)
redo-power-syn-$(VLSI_TOP): $(POWER_CONF) $(POWER_SYN_CONF)
redo-power-syn: override HAMMER_EXTRA_ARGS += -p $(TOOLS_CONF) -p $(POWER_CONF) -p $(POWER_SYN_CONF) -p $(POWER_BLOCKS_CONF)
power-syn redo-power-syn: export HAMMER_POWER_RUNDIR = $(call power_rundir,syn)
redo-power-syn-$(VLSI_TOP): override HAMMER_EXTRA_ARGS += -p $(TOOLS_CONF) -p $(POWER_CONF) -p $(POWER_SYN_CONF) -p $(POWER_BLOCKS_CONF)

power-par: $(POWER_CONF) $(POWER_PAR_CONF) sim-par-debug
power-par-$(VLSI_TOP): $(POWER_CONF) $(POWER_PAR_HIER_CONF) sim-par-debug-$(VLSI_TOP)
power-par: override HAMMER_POWER_EXTRA_ARGS += -p $(TOOLS_CONF) -p $(POWER_CONF) -p $(POWER_PAR_CONF) -p $(VOLTUS_CONF)
power-par-$(VLSI_TOP): override HAMMER_POWER_EXTRA_ARGS += -p $(TOOLS_CONF) -p $(POWER_CONF) -p $(POWER_PAR_HIER_CONF) -p $(VOLTUS_CONF)
redo-power-par: $(POWER_CONF) $(POWER_PAR_CONF)
redo-power-par-$(VLSI_TOP): $(POWER_CONF) $(POWER_PAR_HIER_CONF)
redo-power-par: override HAMMER_EXTRA_ARGS += -p $(TOOLS_CONF) -p $(POWER_CONF) -p $(POWER_PAR_CONF) -p $(VOLTUS_CONF)
redo-power-par-$(VLSI_TOP): override HAMMER_EXTRA_ARGS += -p $(TOOLS_CONF) -p $(POWER_CONF) -p $(POWER_PAR_HIER_CONF) -p $(VOLTUS_CONF)

$(POWER_SYN_CONF): EXTRA_SIM_OUT_NAME = syn
$(POWER_PAR_CONF) $(POWER_PAR_HIER_CONF): EXTRA_SIM_OUT_NAME = par

$(OBJ_DIR)/power-%/power-output-full.json: private override HAMMER_EXTRA_ARGS += $(HAMMER_POWER_EXTRA_ARGS)
