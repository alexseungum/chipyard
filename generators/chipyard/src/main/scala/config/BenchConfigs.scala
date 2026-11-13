package chipyard

import org.chipsalliance.cde.config.{Config}

// Small Rocket for the scratch-vs-NFS Sky130 PAR benchmark (mirrors barduino-vlsi's memory setup)
class SmallRocketConfig extends Config(
  new testchipip.soc.WithNoScratchpads ++                // no on-chip scratchpad SRAM
  new chipyard.config.WithBroadcastManager ++            // replace L2$ with a broadcast hub
  new freechips.rocketchip.rocket.WithNSmallCores(1) ++  // single small rocket-core (4KiB I$/D$, no FPU/VM)
  new chipyard.config.AbstractConfig)

// Big Rocket (FPU, VM, 16KiB 4-way I$/D$) with the same memory setup as SmallRocketConfig
class BigRocketConfig extends Config(
  new testchipip.soc.WithNoScratchpads ++
  new chipyard.config.WithBroadcastManager ++
  new freechips.rocketchip.rocket.WithNBigCores(1) ++
  new chipyard.config.AbstractConfig)

// Medium BOOM (2-wide OoO, 16KiB 4-way I$/D$) with the same memory setup as SmallRocketConfig
class MediumBoomBenchConfig extends Config(
  new testchipip.soc.WithNoScratchpads ++
  new chipyard.config.WithBroadcastManager ++
  new boom.v3.common.WithNMediumBooms(1) ++
  new chipyard.config.AbstractConfig)
