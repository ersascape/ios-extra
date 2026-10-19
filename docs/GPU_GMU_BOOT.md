# Booting the A618 GMU: mainline reference and what we measured

Everything here is for the Adreno 618 GPU (DT chip `0x06010800`, SM7150, Redmi Note
10 Pro `sweet`) in this XNU port. It combines (a) what mainline Linux v6.12 does
(source read, external copy under `gpu-fw/`, see "Sources"), (b) what the phone
actually did in our tests (marked **measured**), and (c) what is still unknown.
Source reading is not hardware proof: keep those separate when you add to this file.

## Sources

- Mainline Linux v6.12 `drivers/gpu/drm/msm/adreno/{a6xx_gmu.c,a6xx_gmu.h,a6xx_hfi.c,
  a6xx_hfi.h,a6xx_gpu.c,adreno_gpu.c}` and `registers/adreno/{a6xx_gmu.xml,a6xx.xml}`,
  fetched from git.kernel.org into `/run/media/dipa/android/ios-extra-work/gpu-fw/`
  (raw.githubusercontent.com rate-limits with HTTP 429; use
  `https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/plain/<path>?h=v6.12`).
- Firmware: linux-firmware commit `a2dcb924f0897368b0b4f305cbf9808cdda90ce0`,
  `qcom/a630_gmu.bin` (32768 bytes, SHA256
  `da8d9b1b1f5c1a0b311f32567093b4828f3c80031dd8435f91ac13c664e173a6`) and
  `qcom/a630_sqe.fw` (34188 bytes, SHA256
  `1c21b527d9183487cc550dabbb3f43e555df5a977a461934fc61f0635a9aa90c`). Mainline uses
  these for A618. The Xiaomi downstream tree (`758bb7ef…`, ignored under
  `research/gpu-sources/`) wants `a618_gmu.bin` and uses a different, register-based
  HFI; its source is still the reference for DT clocks/regulators, **not** for the
  GMU protocol. The phone's own `a618_gmu.bin` lives in the `super` partition, which
  was never backed up; it is not used.
- Pinned Xiaomi DT facts: `docs/GPU_POWER_SEQUENCE.md`.

## Address map (physical)

| Block | Address | Notes |
| --- | --- | --- |
| GCC | `0x00100000` (+`0x90000` mapped) | GPU config AHB `0x71004`, memnoc `0x7100c`, snoc dvm `0x71018`, ddrss axi `0x4452c`, GPLL0 mode `0x0`, GPLL0 vote `0x52000`, GPU GPLL gate `0x52004` (bit15 GPLL0, bit16 GPLL0/2) |
| GPUCC | `0x05090000` (`0x9000`) | CX GDSCR `0x106c`, GX GDSCR `0x100c`, GMU RCG cmd/cfg `0x1120`/`0x1124`, branches ahb `0x1078`, cx-apb `0x1088`, cx-gmu `0x1098`, cxo `0x109c` |
| GMU registers | `0x0506a000` (`0x31000`) | see below |
| GPU SMMU (kgsl) | `0x05040000` (`0x10000`) | 4 KiB pages, CB0 at `+0x8000` |
| GPU PDC cfg / seq | `0x0b290000` / `0x0b490000` (`0x10000` each) | DT `kgsl_gmu_pdc_cfg` / `kgsl_gmu_pdc_seq` |
| Command DB locator | `0x0c3f000c` | -> reserved-RAM DB (e.g. `0x85fe0000`) |
| Apps RSC / TCS | `0x18220000` / `0x18220d00` | `sweet_rpmh.c`, DRV2, 2 ACTIVE TCS |

## GMU register offsets

GMU block byte offset = mainline `a6xx_gmu.xml` dword index x 4 = (a6xx_reg.h GPU
dword index - `0x1A800`) x 4. The RSCC block is `gmu + 0x23000` (mainline
`gmu->rscc = gmu->mmio + 0x23000`; RSCC dword indexes from `a6xx_gmu.xml` x 4).

| Register | Dword index | GMU byte offset | Seen on phone |
| --- | --- | --- | --- |
| `GMU_ICACHE_CONFIG` / `DCACHE_CONFIG` / `SYS_BUS_CONFIG` | `0x4c00` / `0x4c01` / `0x4c0f` | `0x13000` / `0x13004` / `0x1303c` | not read |
| ITCM start / DTCM start | `0x1B400` / `0x1C400` (gpu index) | `0x3000` / `0x7000` | written + read back 0 mismatches |
| `GMU_CM3_SYSRESET` | `0x5000` | `0x14000` | `1` (reset held) |
| `GMU_CM3_BOOT_CONFIG` | `0x5001` | `0x14004` | not read |
| `GMU_CM3_FW_BUSY` / `FW_INIT_RESULT` / `CM3_CFG` | `0x501a` / `0x501c` / `0x502d` | `0x14068` / `0x14070` / `0x140b4` | `0` / `0` / `0x52` |
| `GMU_PWR_COL_INTER_FRAME_CTRL` / `HYST` | `0x50c0` / `0x50c1` | `0x14300` / `0x14304` | not read |
| `GMU_RPMH_CTRL` | `0x50e8` | `0x143a0` | not read |
| `GPU_GMU_CX_GMU_PWR_COL_CP_MSG` / `CP_RESP` | `0x5100` / `0x5101` | `0x14400` / `0x14404` | not read |
| `GMU_HFI_CTRL_STATUS` / `QTBL_INFO` / `QTBL_ADDR` / `CTRL_INIT` | `0x5180` / `0x5184` / `0x5185` / `0x5186` | `0x14600` / `0x14610` / `0x14614` / `0x14618` | not read |
| `GMU_HFI_SFR_ADDR` | `0x5182` | `0x14608` | not read |
| `GMU_HOST2GMU_INTR_SET`, `GMU2HOST_INTR_INFO` | `0x5194`, `0x5192` | `0x14650`, `0x14648` | not read |
| `GMU_GENERAL_0` / `GENERAL_7` | `0x51c5` / `0x51cc` | `0x14714` / `0x14730` | `0` / not read |
| `GMU_AO_HOST_INTERRUPT_STATUS` | `0x9305` | `0x24c14` | `0` |
| `GMU_RSCC_CONTROL_REQ` / `ACK` | `0x9307` / `0x9308` | `0x24c1c` / `0x24c20` | `0` / `0` |
| `GMU_AHB_FENCE_RANGE_0` | `0x9311` | `0x24c44` | not read |
| `GMU_BOOT_SLUMBER_OPTION`, `GX_VOTE_IDX`, `MX_VOTE_IDX` | `0x23f8`, `0x23f9`, `0x23fa` | `0x8fe0`, `0x8fe4`, `0x8fe8` | not read |
| `GMU_GX_SPTPRAC_POWER_CONTROL`, `SPTPRAC_PWR_CLK_STATUS` | `0x81`, `0x50d0` | `0x204`, `0x14340` | not read |

(Offsets other than the "seen" ones were computed from the xml and not yet exercised;
re-derive them from `a6xx_gmu.xml` before relying on them.)

## Mainline resume sequence, legacy (A630-family incl. A618) flow

From `a6xx_gmu_fw_start()`, `a6xx_gmu_start()`, `a6xx_rpmh_start()`,
`a6xx_gmu_power_config()`, `a6xx_gmu_gfx_rail_on()`, `a6xx_gmu_hfi_start()` (v6.12):

1. Power: CX GDSC on, GMU clock 200 MHz and `gmu`/`cxo`/`axi`/`memnoc` clocks on.
   **Done and measured** (0083-0085).
2. `GMU_GENERAL_7 = 1` (TCM retention).
3. `a6xx_rpmh_start`: `RSCC_CONTROL_REQ = BIT(1)`; poll `RSCC_CONTROL_ACK` bit 1
   (100 us step, 10 ms); poll RSCC `SEQ_BUSY_DRV0` == 0; `REQ = 0`.
4. Load firmware. Legacy image: write the whole file to `ITCM_START`
   (<= 0x8000 bytes). **Done** (0086).
5. `FW_INIT_RESULT = 0`; `CM3_BOOT_CONFIG = 0x02` (cold boot).
6. `HFI_QTBL_ADDR = hfi.iova`; `HFI_QTBL_INFO = 1`.
7. `AHB_FENCE_RANGE_0 = BIT(31) | (0xa << 18) | 0xa0` (non-A7xx).
8. `CM3_CFG = 0x4052` (measured reset value `0x52`; bit 14 keeps the NMI handler off).
9. `HFI_SFR_ADDR = chipid` where `chipid = (adreno chip_id & 0xffff0000) |
   ((chip_id << 4) & 0xf000) | ((chip_id << 8) & 0x0f00)`.
10. `PWR_COL_CP_MSG = log.iova | (log.size / 4096 - 1)`.
11. `a6xx_gmu_power_config`: `SYS_BUS_CONFIG = 1`, `ICACHE_CONFIG = 1`,
    `DCACHE_CONFIG = 1`, `PWR_COL_INTER_FRAME_CTRL = 0x09c40400`, idle-level
    dependent `INTER_FRAME_HYST`/`SPTPRAC_HYST = 0x000a1680` and control bits, then
    `GMU_RPMH_CTRL |= RPMH_INTERFACE|LLC_VOTE|DDR_VOTE|MX_VOTE|CX_VOTE|GFX_VOTE enables`.
    (Bit values: `a6xx_gmu.xml`, read before using.)
12. `a6xx_gmu_start`: read the dword at `REG_A6XX_GMU_CM3_DTCM_START + 0xff8` (GMU
    byte offset `0x7000 + 0xff8*4 = 0xAFE0`, i.e. firmware image offset `0x7fe0`). If `<= 0x20010004` then
    `mask = 0xffffffff, expected = 0xbabeface`, else `mask = 0x1ff, expected = 0x100`.
    In `a630_gmu.bin` the word at file offset `0x7fe0` is `0` (the firmware fills it
    at run time), so the check reads whatever the firmware has written by then.
    Then `CM3_SYSRESET = 1`; `PWR_COL_CP_RESP = 0`; `CM3_SYSRESET = 0`; poll
    `FW_INIT_RESULT & mask == expected` (100 us step, 10 ms).
13. Legacy only: `a6xx_gmu_gfx_rail_on`: `BOOT_SLUMBER_OPTION = 0`;
    `GX_VOTE_IDX = vote & 0xff`, `MX_VOTE_IDX = (vote >> 8) & 0xff` with `vote` the
    GX ARC vote for the highest GPU frequency; OOB request `BOOT_SLUMBER`.
14. If `idle_level < SPTP`: `a6xx_sptprac_enable`: `GX_SPTPRAC_POWER_CONTROL =
    0x778000`; poll `SPTPRAC_PWR_CLK_STATUS & 0x38 == 0x28` (1 us step, 100 us).
15. `a6xx_gmu_hfi_start`: `HFI_CTRL_INIT = 1`; poll `HFI_CTRL_STATUS` bit 0 (10 ms).
16. OOB protocol (`a6xx_gmu_set_oob`): write `1 << request` to `HOST2GMU_INTR_SET`;
    poll `GMU2HOST_INTR_INFO` for `1 << ack`; write that bit to `GMU2HOST_INTR_CLR`.
    Legacy bits: `GPU_SET` request 16 / ack 24; others in `a6xx_gmu_oob_bits[]`.

Not yet read in detail: HFI message formats/versions, the GX/CX/MX ARC vote
table construction (`a6xx_gmu_rpmh_arc_votes_init`: built from `cmd_db_read_aux_data`
levels and the OPP table), GMU-side GX power-up, the `a6xx_gpu` CP/SQE startup.

## GMU memory (mainline legacy flow)

One GMU address space (`msm_iommu_new(gmu->dev)`, IOVA `0x0 .. 0x80000000`):
dummy page 4 KiB at fixed IOVA `0x60000000`; then, allocated from `0x60001000`
upwards: debug 16 KiB (legacy only), log 16 KiB, HFI 16 KiB. All write-combined
(non-cacheable). HFI buffer layout (`a6xx_hfi_init`): queue table header (6 dwords:
version, size, qhdr0_offset, qhdr_size, num_queues=2, active_queues=2) at offset 0,
queue headers (12 dwords each: status, iova, type, size, msg_size, dropped,
rx/tx watermark, rx/tx request, read_index, write_index) right after it; command
queue data at +4 KiB (type `10<<8 | 0`), GMU response queue at +8 KiB
(`10<<8 | 4` for legacy). The mainline DT for the GMU stream is, as remembered (not re-checked
in this session), `iommus = <&adreno_smmu 5 0x400>` (stream 5, mask `0x400`); the
Xiaomi DT lists GMU user/kernel streams 4/5. Our tests matched stream 5 exactly (SMR mask 0) and
never ran a master through it.

## GPU SMMU facts (0087-0089)

**Measured, before any programming:** `sCR0 0x00200626`, `sCR1/sCR2/sACR 0`,
`IDR0 0x48016605`, `IDR1 0x20008005`, `IDR2 0x00007511`, `IDR7 0`; 5 stream groups,
5 context banks, every `S2CR` = `0x000200ff` (TYPE=2 fault, CBNDX 0xff), every `SMR`
= 0, all context banks zero, `sGFSR` 0. Decoded from the ARM SMMUv2 manual from
memory (unverified): CLIENTPD=0 (translation on), USFCFG=1, stream matching, coherent
table walk, ATOS present, 4/16/64 KiB granules, 48-bit UBS, 36-bit OAS.

**Measured, programming (`sweetgpu=8`, CB3 / stream 5):** tables = L1[1]->L2,
L2[256]->L3, L3[0]->page; PTE `0x40000104663f43` (valid page, AF, inner-shareable,
AP RW, nG, XN, attr 0). Writes that read back exactly: `CBA2R3=1`, `CB3 TCR2=1`,
`TCR=0x802020` (T0SZ 32, SH0 outer, EPD1), `TTBR0=<pa>`, `MAIR0=0x44`, `SCTLR=0x27`
(M|TRE|AFE|CFRE), `S2CR3=3` (translate, CB3), `SMR3=0x80000005`.
ATOS (CB `ATS1PR` +0x800, `ATSR` +0x8f0, `PAR` +0x50) returned the right page for
IOVA `0x60000000` and `0x60000fff`, and a fault (PAR bit 0) for `0x60001000` and
`0x20000000`. Restore: `SMR3<-0` works (stream group inactive); **`S2CR3` refuses
`0x200ff` and `0x20000` (stays 3) and `CBAR3` refuses `0` and `0x20000` (stays
`0x10000`)** while all CB registers revert. Inference: only translate/bypass S2CR
types and stage-1/nested CBAR types are accepted. Several 32-bit reads of the GR0/GR1
pages (SMR/S2CR/CBAR/CBA2R, not CB registers) came back with `0xfffffe3f` in bits
63:32 of the destination register although the instruction was `ldr w`: those pages
are probably trapped and emulated by the hypervisor. Always treat GR0/GR1 reads as
32-bit values (mask them).

## RSC / PDC facts (0090-0092)

**Measured before init:** RSCC already contained mainline's `PDC_SEQ_START_ADDR=0x4520`,
`PDC_MATCH_VALUE_LO/HI=0x4510/0x4514`, `PDC_SLAVE_ID_DRV0=1`, `HIDDEN_TCS_CMD0_ADDR=
0x82204514`; everything else (RSC sequencer memory, all PDC registers, PDC sequence
memory) was 0; RSCC REQ/ACK 0, `SEQ_BUSY` 0, `TCS0/TCS3_DRV0_STATUS` 1.
**Measured after `sweetgpu=10`:** 48 writes (table `gpu_rpmh_init[]` in
`bsd/dev/sweet_gpu.c`), 39 read back, 9 did not (the first was `HIDDEN_TCS_CMD0_ADDR`
which keeps `0x82204514`; the other 8 are unknown until the 0092 image is run).
RSC stop handshake completed: `RSC_STATUS0_DRV0 = 0x01010006`. The configuration is
left in place; it is not known whether it survives a reboot.

## Rails and clocks (0082-0085)

ARC raw level tables from the command DB (hardware requests carry the table **index**,
not the corner number or millivolts): `gfx.lvl` addr `0x30050`, `cx.lvl` `0x30000`,
`mx.lvl` `0x30010`; `cx`/`gfx`: raw `0,16,64,128,192,256`; `mx`: `0,16,192,320,384`.
LOW_SVS = raw 64 (`cx` index 2); `mx` has no 64 so its first level >= 64 is `192`
(index 2). CX GDSC enable needs MX then CX LOW_SVS votes (downstream `gdsc_enable`).
Clock stage: set `0x52004` bit 16, GMU RCG `0x1124 = 0x602` (source 6 = GPLL0/2,
HID 2 = divide 1.5 => 200 MHz) then `CMD` UPDATE; cx-gmu CBCR with wake/sleep fields
`0xF` (`0x00004ff1` running). `ahb` and `cxo` are already enabled by ABL (they read
"off" only while CX is collapsed). `memnoc`/`ddrss-axi` are *voted* branches: their
status bit can read "running" because of another master, so ownership is the enable
bit only. The measured RCG stays at `0x602` after the tests (unused).

## Hypervisor / protection observations

- No test so far faulted on a read; GR0/GR1 SMMU pages behave as if emulated.
- S2CR/CBAR "inert" encodings are refused; SMR=0 deactivates a group.
- 9 of 48 RSC/PDC writes did not stick (reason unknown: read-only/hardware-owned
  registers, or filtering).
- `fastboot getvar` must never be run on this phone.

## What is still unknown (do not guess; measure)

1. Which 9 RSC/PDC writes are refused, and whether the RSC/PDC programming persists
   across a reboot (0092 answers both).
2. Whether the GMU firmware reaches `FW_INIT_RESULT` with our (not yet allocated or
   mapped) HFI/log/debug buffers, and what it does to the rails it controls.
3. Whether the GMU stream really is 5 with mask `0x400`, and whether the GMU's
   masters work through our context bank (ATOS only proves the page tables).
4. GX power-up, the CP/SQE microcode path (`a630_sqe.fw`), the secure `a615_zap`
   shader (the hypervisor may own the secure side) and the first command submission.
