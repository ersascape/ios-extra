# A618 power and firmware dependencies

This is a source audit for the next hardware experiment, not an implemented
power sequence. Patch 0080 reached the phone's home screen using guarded,
read-only clock inventory; patch 0081 preserves that inventory for delayed
USB reports. Neither starts GPU execution.

The downstream reference is Xiaomi's `sweet-r-oss` source at immutable commit
[`758bb7ef50af360e728662a1ed3b3a1b977a2f13`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/758bb7ef50af360e728662a1ed3b3a1b977a2f13).
Downloaded source stays in the ignored `research/gpu-sources/` tree.

## Firmware identity

The matching A618 entry in
[`adreno-gpulist.h`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/758bb7ef50af360e728662a1ed3b3a1b977a2f13/drivers/gpu/msm/adreno-gpulist.h#L395)
selects `a630_sqe.fw`, **`a618_gmu.bin`**, and the secure subsystem name
`a615_zap`. Its GMU version fields are major 1, minor 8; GMEM is 512 KiB.
These are source declarations. The exact phone firmware bytes, version
compatibility and secure loader availability have not been verified.

The mainline SM7150 catalog instead names `a630_gmu.bin`. That difference
must be resolved before selecting firmware; a matching GPU family name alone
does not establish interchangeability. Do not derive a filename extension
or a secure-loader protocol solely from the downstream subsystem name.

## Startup dependency map

| Dependency | Downstream behavior | Work still needed in XNU |
| --- | --- | --- |
| CX rail and domain | `gmu_start` enables the CX GDSC before GMU clocks | Decode command DB ARC resources and the domain's parent supply, establish a held vote, bounded status checks and rollback |
| GMU clocks and bus | Set the GMU clock rate, enable its DT clock list, enable IRQs, request startup DDR bandwidth | Audit clock parents/PLL/rate programming and interconnect votes; implement owned references |
| GMU memory | Separate user/kernel SMMU contexts; persistent HFI and log buffers mapped before firmware start | SMMU context setup, page-table granule, cache maintenance, fault reporting and stable buffer lifetimes |
| RSC/PDC and GMU firmware | Cold boot installs RSC/PDC sequences and loads GMU TCM through AHB | Confirm exact SoC register layout and firmware format; bounded firmware-ready checks |
| GMU handshake and GX | Publish HFI/log addresses, configure power, release GMU reset; the DT enables the register-based HFI quirk | Implement the matching OOB/rail handshake and hold GX stable before core access |
| SQE and command execution | Program SQE GPU virtual address and perform applicable secure initialization | Verify secure initialization contract, map buffers, bring up one queue and observe a known memory write |

This order is derived from
[`kgsl_gmu.c:gmu_start`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/758bb7ef50af360e728662a1ed3b3a1b977a2f13/drivers/gpu/msm/kgsl_gmu.c#L1632)
and
[`adreno_a6xx_gmu.c:a6xx_gmu_fw_start`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/758bb7ef50af360e728662a1ed3b3a1b977a2f13/drivers/gpu/msm/adreno_a6xx_gmu.c#L1009).
Their probe-time allocations precede the startup call. Error handling must
be designed explicitly for XNU rather than copied from a Linux call graph.

## Rails are ARC levels, not LDO millivolts

The existing `sweet_rpmh_vreg_enable` accepts only `ldoc11` and the
2950–3400 mV range needed by the display path. GPU/GMU code instead queries
`gfx.lvl`, `cx.lvl` and `mx.lvl`. The downstream driver reads each resource's
command DB auxiliary table to translate voltage corners into ARC hardware
level indices and build dependent-rail votes.

The relevant contracts are
[`kgsl_gmu.c:rpmh_arc_cmds`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/758bb7ef50af360e728662a1ed3b3a1b977a2f13/drivers/gpu/msm/kgsl_gmu.c#L594)
and
[`rpmh-regulator.c:rpmh_regulator_load_arc_level_mapping`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/758bb7ef50af360e728662a1ed3b3a1b977a2f13/drivers/regulator/rpmh-regulator.c#L1244).
Reusing the existing transport may be possible, but requires a distinct ARC
resource/table contract. Passing a corner or guessed voltage to the LDO
helper is not a valid GPU power vote.

The inherited `rh_lookup` also explicitly accepts only VRM entries. ARC
inspection needs a separate validated lookup contract rather than merely
changing the resource string at its caller. The command DB header carries
resource-table and auxiliary-data offsets; each matching entry contributes
its own auxiliary offset and length. Validate both ranges and accept only
bounded, even-length level tables before interpreting their `uint16_t`
elements. Preserve the existing display client's VRM validation.

## Domain control and ownership

[`gdsc-regulator.c:gdsc_enable`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/758bb7ef50af360e728662a1ed3b3a1b977a2f13/drivers/clk/qcom/gdsc-regulator.c#L259)
includes conditional parent-rail votes, root clocks, software reset,
GMEM reset/clamps, hardware-control exclusion, barriers and status polling.
Which branches apply depends on the actual domain's DT configuration.
The saved phone DT gives CX GDSCR `0x0509106c` and GX `0x0509100c`, with
additional control/status registers. A single clear of `SW_COLLAPSE` does
not reproduce the whole regulator contract.

The downstream code also distinguishes a domain powered by another owner
from the host's own software vote. An instantaneous `PWR_ON` bit does not
hold a GMU-managed domain awake. Keep the current probe's restriction on
GPU/GMU/SMMU mappings until a stable power hold has been implemented.

## Memory and handshake details

The
[`sdmmagpie-gpu.dtsi`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/758bb7ef50af360e728662a1ed3b3a1b977a2f13/arch/arm64/boot/dts/qcom/sdmmagpie-gpu.dtsi)
declares GPU stream 0, GMU user stream 4 and GMU kernel stream 5. These match
the saved device-tree inventory. It specifies GMU clocks `gmu_clk`,
`cxo_clk`, `axi_clk`, `memnoc_clk`, a 200 MHz GMU power level, and
`qcom,gpu-quirk-hfi-use-reg`. Source DT is still distinct from measured
register state after ABL.

`kgsl_gmu.c` reserves ITCM at `0x00000` (16 KiB), DTCM at `0x40000`
(16 KiB), noncached kernel VA at `0x60000000` (512 MiB), and noncached
user VA at `0x80000000` (1 GiB). Firmware startup receives already-mapped
HFI queue and log-buffer virtual addresses before the GMU leaves reset.
Therefore the SMMU path is a startup prerequisite even before submitting
GPU commands. XNU's 16 KiB CPU pages do not determine SMMU granule support.

## Next implementation boundary

First recover a complete report from 0081, including all GCC values and
both raw GDSCR values. Then extend command DB inspection to expose the
ARC resource metadata and level tables without voting. Use those observed
tables and the source audit to design a separate opt-in, bounded CX/GMU
power experiment. Firmware loading and command submission follow their
memory and secure-initialization prerequisites.
