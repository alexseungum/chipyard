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

ifeq ($(flow),sky130-openroad)
    tech_name         ?= sky130
    CONFIG            ?= TinyRocketConfig
    TOOLS_CONF        ?= openroad-tools.yml
    TECH_CONF         ?= power-sky130.yml
    DESIGN_CONFS      ?= openroad-design-sky130.yml
    OPENROAD_ENV      ?= openroad-env.yml
    VLSI_OBJ_DIR      ?= build-sky130-openroad
    HAMMER_EXEC       ?= ./openroad-vlsi-sky130
    INPUT_CONFS       ?= $(TOOLS_CONF) $(TECH_CONF) $(DESIGN_CONFS) $(OPENROAD_ENV) $(EXTRA_CONFS)
    ENABLE_YOSYS_FLOW  = 1
    ifeq ($(wildcard $(OPENROAD_ENV)),)
        $(error $(OPENROAD_ENV) not found, run ./openroad-setup.sh <install-dir> first)
    endif
endif
