# FP6 SMMU power and clock prerequisites

## Source evidence

Reference: local Fairphone `android_kernel_fairphone_sm7635`, commit
`9535e0f08`, and selected FP6 stock DTB SHA-256
`8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`.

- `drivers/iommu/arm/arm-smmu/arm-smmu-qcom-pm.c`,
  `arm_smmu_power_on`: regulator enable precedes clock preparation/enable.
  `arm_smmu_power_off` reads IDR0 before withdrawing clocks to complete writes.
- Stock `kgsl-smmu@3da0000`: CX GDSC supply and clock consumer order
  `gpu_cc_hlos1_vote_gpu_smmu`, `gcc_gpu_memnoc_gfx`,
  `gcc_gpu_snoc_dvm_gfx`, `gpu_cc_ahb`.
- `drivers/clk/qcom/gpucc-volcano.c`: SMMU vote GPUCC+0x7000 bit0,
  AHB GPUCC+0x90bc bit0; AHB parent is hub divider+0x942c then
  hub RCG+0x93ec. SMMU uses voted halt polling; AHB uses delay.
- `drivers/clk/qcom/gcc-volcano.c`: memnoc GCC+0x71010 bit0,
  HWCG bit1; SNOC GCC+0x71018 bit0. Memnoc voted halt polling is
  skipped under HWCG; SNOC uses delay. Probe keeps CFG AHB+0x71004
  bit0 enabled. `clk-branch.c` defines these polling/delay semantics.
- Stock CX GDSC is GPUCC+0x9080, hardware control+0x9094, with
  parent `cx.lvl`. `gdsc-regulator.c` rejects hardware-controlled enables,
  clears SW_COLLAPSE, waits eight XO cycles, polls PWR_ON, then delays
  for clock and memory powerup. This domain has no CX reset sequence in DT.
- Stock `cx.lvl` regulator has initial/proxy level 0x180. ARC commands carry
  an index into command-db auxiliary levels, not that raw corner value.
  `cmd-db.c` defines header144, resource header16 and entry24 byte layouts.
- Stock apps RSC DRV2 is 0x17a20000/0x10000, TCS offset0xd00,
  channel0 ACTIVE slots0–2. `rpmh-rsc.c` v3 register layout has TCS
  stride672, command stride24, CONTROL+0x24, STATUS+0x28,
  CMD_ENABLE+0x2c, MSGID+0x34, ADDR+0x38, DATA+0x3c and STATUS+0x40.
  Message0x10108 requests an eight-byte write with response. Completion
  requires IRQ plus command ISSUED/COMPLETE plus idle TCS status.
- Command-db comes from stock reserved-memory0x81c60000/0x20000.
  Linux validates its magic and finds resource auxiliary data; it does not
  impose a command-db or ARC header version gate in this lookup path.
- `clk-rcg2.c` explicitly supports CXO safe configuration for an RCG whose
  normal table lacks CXO. The SMMU-only power path uses 19.2MHz CXO for the
  hub, with ROOT_EN retained. It is not the GMU's required hub performance rate.

## Implementation

Patch0132 borrows a confirmed enabled CX/hub and requests four SMMU clocks.
It preserves inherited votes and restores only acquired branch enable votes
following contained context teardown. Failed containment retains those votes.

Patch0134 adds `fp6smmupower=1`: resolve and acknowledge a CX floor, enable
CX GDSC and bring an off hub up using safe CXO, then use0132 clocks. It retains
CX/RSC/hub ownership for the boot, because no general regulator/clock framework
can yet account for other inherited users. It never releases the shared rail
by sending a zero vote. A failed/uncertain TCS transaction is quarantined and
its slot IRQ is kept masked; boot logging prints the exact slot/state. The
opt-in is separate from `fp6smmu=2` for reproducing the previous test unchanged.

Host modeling checks expected register sequences; it cannot prove that the
hypervisor grants these writes, that the rail physically changed, or that
SMMU TCR2 will accept writes on the phone. Successful context ATOS also does
not establish a real SID5/TBU transaction. Neither patch releases CM3 reset.
