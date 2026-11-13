#!/usr/bin/env bash
set -o pipefail
cy=$1; tag=$2; shift 2
stages=${@:-buildfile syn par}
logdir=${BENCH_LOGDIR:-/scratch/syeon-um/cy-bench-logs}
cd $cy && source env.sh && cd vlsi || exit 1
BENCH_CONFIG=${BENCH_CONFIG:-BigRocketConfig}
BENCH_EXTRA_CONFS=${BENCH_EXTRA_CONFS:-bench-bwrc.yml}
[ -n "$BENCH_PAR_CONF" ] && export HAMMER_EXTRA_ARGS="-p $cy/vlsi/$BENCH_PAR_CONF"
for s in $stages; do
  echo "$(date +%T) START $tag $s" | tee -a $logdir/$tag.stages
  /usr/bin/time -v -o $logdir/$tag.$s.time make $s flow=sky130-power CONFIG=$BENCH_CONFIG EXTRA_CONFS="$BENCH_EXTRA_CONFS" $BENCH_MAKE_ARGS > $logdir/$tag.$s.log 2>&1
  rc=$?
  echo "$(date +%T) END $tag $s rc=$rc wall=$(grep Elapsed $logdir/$tag.$s.time | awk '{print $NF}')" | tee -a $logdir/$tag.stages
  [ $rc -ne 0 ] && exit $rc
done
