flow ?= none
EXTRA_CONFS ?=

ifeq ($(flow),sky130-power)
    tech_name         ?= sky130
    CONFIG            ?= TinyRocketConfig
    TOOLS_CONF        ?= power-tools.yml
    TECH_CONF         ?= power-sky130.yml
    DESIGN_CONFS      ?= power-design-sky130.yml
    VLSI_OBJ_DIR      ?= build-sky130-power
    HAMMER_EXEC       ?= ./power-vlsi-sky130
    INPUT_CONFS       ?= $(TOOLS_CONF) $(TECH_CONF) $(DESIGN_CONFS) $(EXTRA_CONFS)
endif
