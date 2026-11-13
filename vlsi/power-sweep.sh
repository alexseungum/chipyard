#!/usr/bin/env bash
set -u
cd "$(dirname "$(readlink -f "$0")")"

usage() {
  cat <<EOF
usage: $0 [-j JOBS] [-l LEVELS] [-c CONFIG] [-m MAKE_ARGS] [-s STAGGER] BINARY...
  -j JOBS      tests run in parallel after the first one per level (default 4)
  -l LEVELS    comma-separated power levels: rtl,syn (default rtl,syn)
  -c CONFIG    chipyard CONFIG (default BigRocketConfig)
  -m MAKE_ARGS extra make arguments (default "flow=sky130-power LOADMEM=1")
  -s STAGGER   seconds between make starts (default 90)
env: OBJ_DIR, POWER_SWEEP_LOCK, PASS_RE, FAIL_RE
outputs: build/<...>/power-<level>-rundir-<binary>/{sim.log,power.log,reports/}
EOF
}

JOBS=4
LEVELS=rtl,syn
CONFIG=BigRocketConfig
MAKE_ARGS="flow=sky130-power LOADMEM=1"
STAGGER=90
while getopts "j:l:c:m:s:h" o; do
  case $o in
    j) JOBS=$OPTARG ;;
    l) LEVELS=$OPTARG ;;
    c) CONFIG=$OPTARG ;;
    m) MAKE_ARGS=$OPTARG ;;
    s) STAGGER=$OPTARG ;;
    *) usage; exit 2 ;;
  esac
done
shift $((OPTIND - 1))
[ $# -gt 0 ] || { usage; exit 2; }

for l in ${LEVELS//,/ }; do
  case $l in rtl|syn) ;; *) echo "unsupported level: $l" >&2; exit 2 ;; esac
done

BINS=()
for b in "$@"; do
  [ -f "$b" ] || { echo "binary not found: $b" >&2; exit 2; }
  BINS+=("$(readlink -f "$b")")
done

OBJ=$(readlink -m "${OBJ_DIR:-build-sky130-power/chipyard.harness.TestHarness.$CONFIG-ChipTop}")
mkdir -p "$OBJ"
LOCK=${POWER_SWEEP_LOCK:-$OBJ/.power-sweep.lock}
PASS_RE=${PASS_RE:-'\*\*\* PASSED'}
FAIL_RE=${FAIL_RE:-'DRAM MISMATCH|Assertion failed|\*\*\* FAILED'}

name() { local b; b=$(basename "$1"); echo "${b%.*}"; }
rundir() { echo "$OBJ/power-$1-rundir-$(name "$2")"; }
sim_ok() { grep -q -E "$PASS_RE" "$1" && ! grep -q -E "$FAIL_RE" "$1"; }

mk() {
  local log=$1 hold=$2 fd pid rc
  shift 2
  exec {fd}>>"$LOCK"
  flock "$fd"
  make "$@" $MAKE_ARGS > "$log" 2>&1 {fd}>&- &
  pid=$!
  if [ "$hold" = all ]; then
    wait $pid
    rc=$?
    flock -u "$fd"
    exec {fd}>&-
    return $rc
  fi
  sleep "$hold"
  flock -u "$fd"
  exec {fd}>&-
  wait $pid
}

run_test() {
  local lvl=$1 bin=$2 first=$3 rd sim=FAIL power=SKIP
  rd=$(rundir "$lvl" "$bin")
  mkdir -p "$rd"
  echo "$(date +%T) start $lvl $(name "$bin")"
  if [ "$first" = 1 ]; then
    if mk "$rd/power.log" all "power-$lvl" CONFIG="$CONFIG" BINARY="$bin"; then power=OK; else power=FAIL; fi
    sim_ok "$rd/power.log" && sim=PASS
  else
    mk "$rd/sim.log" "$STAGGER" "redo-sim-$lvl-debug" CONFIG="$CONFIG" BINARY="$bin" HAMMER_EXTRA_ARGS="--only_step run_simulation"
    if sim_ok "$rd/sim.log"; then
      sim=PASS
      if mk "$rd/power.log" "$STAGGER" "redo-power-$lvl" CONFIG="$CONFIG" BINARY="$bin"; then power=OK; else power=FAIL; fi
    fi
  fi
  echo "sim=$sim power=$power" > "$rd/sweep.status"
  echo "$(date +%T) done  $lvl $(name "$bin") sim=$sim power=$power"
}

for lvl in ${LEVELS//,/ }; do
  run_test "$lvl" "${BINS[0]}" 1
done

for lvl in ${LEVELS//,/ }; do
  for bin in "${BINS[@]:1}"; do
    while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do wait -n; done
    run_test "$lvl" "$bin" 0 &
  done
done
wait

printf "\n%-5s %-50s %-5s %-5s %s\n" level test sim power reports
for lvl in ${LEVELS//,/ }; do
  for bin in "${BINS[@]}"; do
    rd=$(rundir "$lvl" "$bin")
    st=$(cat "$rd/sweep.status" 2>/dev/null || echo "sim=? power=?")
    s=${st#sim=}; s=${s%% *}; p=${st##*power=}
    printf "%-5s %-50s %-5s %-5s %s\n" "$lvl" "$(name "$bin")" "$s" "$p" "$rd/reports"
  done
done
