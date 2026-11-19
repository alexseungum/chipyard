#!/usr/bin/env bash
set -euo pipefail

vlsi_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
prefix=$(mkdir -p "${1:-$HOME/openroad-tools}" && cd "${1:-$HOME/openroad-tools}" && pwd)
out=${2:-$vlsi_dir/openroad-env.yml}

if command -v mamba > /dev/null; then pm=mamba; else pm=conda; fi

install() {
    local name=$1 bin=$2
    shift 2
    if [ -x "$prefix/$name/$bin" ] || [ -e "$prefix/$name/$bin" ]; then
        echo "[openroad-setup] $name already installed"
        return
    fi
    echo "[openroad-setup] installing $name"
    $pm create -y -q -p "$prefix/$name" --override-channels "$@"
}

install yosys bin/yosys -c litex-hub -c conda-forge yosys=0.27_4_gb58664d44
install openroad bin/openroad -c litex-hub -c defaults openroad=2.0_12381_g01bba3695 python=3.10
install klayout bin/klayout -c litex-hub -c conda-forge -c defaults klayout=0.28.5_98_g87e2def28
install signoff bin/netgen -c litex-hub -c conda-forge -c defaults magic=8.3.376_0_g5e5879c netgen=1.5.250_0_g178b172
install sky130 share/pdk/sky130A -c litex-hub -c conda-forge open_pdks.sky130a=1.0.457_0_g32e8f23

sram=$prefix/sram22_sky130_macros
if [ ! -d "$sram/.git" ]; then
    echo "[openroad-setup] cloning sram22_sky130_macros"
    git clone -q https://github.com/rahulk29/sram22_sky130_macros "$sram"
fi
git -C "$sram" -c advice.detachedHead=false checkout -q 1f20d16bd0834c2c1686957bb278831770e5880f

for b in yosys/bin/yosys openroad/bin/openroad klayout/bin/klayout signoff/bin/magic signoff/bin/netgen; do
    [ -x "$prefix/$b" ] || { echo "[openroad-setup] missing $prefix/$b" >&2; exit 1; }
done
"$prefix/openroad/bin/openroad" -version

cat > "$out" <<EOF
technology.sky130.sky130A: "$prefix/sky130/share/pdk/sky130A"
technology.sky130.sram22_sky130_macros: "$sram"

synthesis.yosys.yosys_bin: "$prefix/yosys/bin/yosys"
par.openroad.openroad_bin: "$prefix/openroad/bin/openroad"
par.openroad.klayout_bin: "$prefix/klayout/bin/klayout"
drc.klayout.klayout_bin: "$prefix/klayout/bin/klayout"
drc.magic.magic_bin: "$prefix/signoff/bin/magic"
lvs.netgen.netgen_bin: "$prefix/signoff/bin/netgen"
EOF
echo "[openroad-setup] wrote $out"
