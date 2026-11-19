#!/usr/bin/env bash
set -o pipefail
cy=$(cd $1 && pwd); tag=$2; shift 2
stages=${@:-buildfile syn par}
logdir=$(mkdir -p ${BENCH_LOGDIR:-$HOME/cy-bench-logs} && cd ${BENCH_LOGDIR:-$HOME/cy-bench-logs} && pwd)
cd $cy && source env.sh && cd vlsi || exit 1
BENCH_CONFIG=${BENCH_CONFIG:-BigRocketConfig}
BENCH_FLOW=${BENCH_FLOW:-sky130-power}
[ "$BENCH_FLOW" = sky130-power ] && BENCH_EXTRA_CONFS=${BENCH_EXTRA_CONFS-bench-bwrc.yml}
[ -n "$BENCH_PAR_CONF" ] && export HAMMER_EXTRA_ARGS="-p $cy/vlsi/$BENCH_PAR_CONF"
for s in $stages; do
  echo "$(date +%T) START $tag $s" | tee -a $logdir/$tag.stages
  /usr/bin/time -v -o $logdir/$tag.$s.time make $s flow=$BENCH_FLOW CONFIG=$BENCH_CONFIG EXTRA_CONFS="$BENCH_EXTRA_CONFS" $BENCH_MAKE_ARGS > $logdir/$tag.$s.log 2>&1
  rc=$?
  echo "$(date +%T) END $tag $s rc=$rc wall=$(grep Elapsed $logdir/$tag.$s.time | awk '{print $NF}')" | tee -a $logdir/$tag.stages
  [ $rc -ne 0 ] && exit $rc
done
