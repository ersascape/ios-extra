# 0083 — bounded CX power experiment (`sweetgpu=3`)

First GPU hardware write. Opt-in; modes 0/1/2 are unchanged.

## Sequence (all on the boot-time UFS startup thread, after the read-only inventory)

1. Preconditions: GPUCC mapped (config-AHB running), the 0082 ARC inventory
   parsed without error, and CX GDSCR equals the value measured after ABL
   (`0x00222001`: SW_COLLAPSE set, PWR_ON clear, HW_CONTROL clear). Otherwise
   nothing is voted or written and the reason is cached for the USB report.
2. `mx.lvl` then `cx.lvl` ACTIVE-set votes at LOW_SVS (corner 64) through
   `sweet_rpmh_arc_set`. The corner is translated to a command-DB table
   **index** (first raw level >= 64): CX index 2 (raw 64), MX index 2 (raw 192).
   This matches the downstream `gdsc_enable`, which sets the parent to LOW_SVS.
3. Clear `SW_COLLAPSE` in CX GDSCR, wait 1 us, poll `PWR_ON` for up to 1 ms.
4. If it came on, hold 1 ms and re-read.
5. Rollback on every path: set `SW_COLLAPSE`, poll `PWR_ON` clear, release
   `cx.lvl` (index 0) then `mx.lvl` (index 0).

If the MX vote fails nothing else is touched; if the CX vote fails MX is
released and GDSCR is never written.

Not touched: GX, GMU, GPU core, SMMU, clocks, firmware. RPMh ACTIVE votes are
aggregated (max) with other masters, so these votes cannot lower a rail.

## RPMh client changes (`sweet_rpmh.c`)

- `sweet_rpmh_arc_set(res, corner, &level)`: only `cx.lvl`/`mx.lvl`, corner
  0 (release) or 1..128. Validates ARC slave type, address type, even bounded
  auxiliary table, `table[0] == 0`, strictly increasing up to zero padding.
- `rh_send` now takes a command count and arrays; the LDO path sends the same
  three commands as before (host test checks addresses/data).
- `rh_db16` previously truncated a uint16 that crosses an aligned word
  (offset & 3 == 3); fixed. The LDO path did not hit it.

## Tests

`tests/test_rpmh_arc.py` runs the real client against a simulated RSC/TCS/DB
(LDO regression, index selection, table/entry rejection, conflicts, lock,
poison). `tests/test_gpu_probe.py` adds 12 CX-experiment cases with a
simulated GDSC. Both also pass under ASan/UBSan (`IOS_EXTRA_CFLAGS`).

## Phone result

Not run yet. Report lines to look for: `SWEET GPU: CX experiment ...`.

# 0084 — GMU clock stage (`sweetgpu=4`)

Runs inside the 0083 CX window (after the 1 ms hold, before collapse); CX
failures skip it. Nothing is mapped beyond GCC and GPUCC; GMU registers are
untouched.

Preconditions (otherwise nothing is written, reason cached): GPLL0 mode
`LOCK_DET` set and apps vote (`0x52000` bit0) set; GMU RCG and the three
branches readable and self-consistent (enable bit vs CLK_OFF); the cx-gmu
branch (`0x1098`) disabled. The ahb (`0x1078`) and cxo (`0x109c`) branches are
**already enabled by ABL** (phone: 0x00000001 each once CX is on; the earlier
0x80000001 inventory reads were just CX being collapsed). Branches found
enabled are used as they are and never touched; only branches this code enables
are disabled again (report `off` values for the others read 0).

First boot of the stage (0084 image e8dca213) refused on exactly this wrong
assumption and wrote nothing; measured GPLL0 mode 0xd0100005 (locked), vote
0x1, gate 0x52004 = 0x01241d7b (bit16 clear), RCG cmd/cfg 0x80000000/0x0 (root
off, XO source), cx-gmu 0x80004220.

Sequence (pinned Xiaomi `gpucc-sdmmagpie.c` / `gcc-sdmmagpie.c`):
1. set `0x52004` bit16 (GPLL0/2 gate; bit15 and others preserved), 5 us;
2. GMU RCG `0x1124`: source 6 (GPLL0_OUT_MAIN_DIV), HID 2 (divide 1.5, 200 MHz),
   then `CMD` UPDATE (bit0) and poll it clear (500 us bound);
3. cx-gmu only in practice (wake/sleep fields set to 0xF as downstream does);
   ahb/cxo only if they were found disabled. Set enable bit, poll CLK_OFF (bit31) clear (500 us bound each);
4. hold 1 ms, read all three CBCRs;
5. undo in reverse: disable branches (poll off), clear the gate only if this
   code set it, then the 0083 CX collapse and vote release.

The RCG stays configured at 200 MHz after the test: UPDATE on an idle root is
not relied on and nothing consumes it. Report lines: `SWEET GPU: GMU clk ...`.

# 0085 — first GMU register reads (`sweetgpu=5`)

Mode 5 = mode 4 plus, inside the same CX + GMU-clock window:

1. GCC `gcc_gpu_memnoc_gfx_clk` (`0x7100c`) and `gcc_ddrss_gpu_axi_clk`
   (`0x4452c`) enable bit0, the other two GMU DT clocks (`axi_clk`, `memnoc_clk`).
   They are *voted* branches: ownership is decided by the enable bit only
   (a clear status bit can be another master's vote); undo clears only our
   enable bit and does not wait on status. Phone-measured before: memnoc
   `0x80000220`, ddrss-axi `0x00000000`.
2. Map `kgsl_gmu_reg` (`0x0506a000`, `0x31000` bytes) once, only after every clock
   came up. Byte offset = (a6xx register dword index - 0x1A800) * 4, the
   downstream `gmu2gpu_offset`.
3. Read, in order, announcing each read in the log first:
   `CM3_SYSRESET` +0x14000, `CM3_FW_BUSY` +0x14068, `CM3_FW_INIT_RESULT` +0x14070,
   `CM3_CFG` +0x140b4, `GENERAL_0` +0x14714, `AO_HOST_IRQ_STATUS` +0x24c14.
   No writes to the GMU block. Values are cached for the USB reports.

Everything is undone as in 0084. Risk: a read that faults the bus ends the
boot; the announce lines and the persistent log are the evidence in that case.

# 0086 — GMU firmware into TCM (`sweetgpu=6`)

Firmware source: linux-firmware `qcom/a630_gmu.bin` (32768 bytes, SHA256
`da8d9b1b1f5c1a0b311f32567093b4828f3c80031dd8435f91ac13c664e173a6`, commit
`a2dcb924f0897368b0b4f305cbf9808cdda90ce0`), the image mainline Linux loads on
A618 (SM7150). It is not committed: `xnu/patches/0086-stage-gpu-firmware.sh`
downloads it at build time, checks the hash and generates
`bsd/dev/sweet_gpu_fw.h`. The phone's own `a618_gmu.bin` (Xiaomi downstream, in
the unbacked-up `super` partition) is not used; its protocol differs (register
HFI). The reference for everything after this is now **mainline**
`a6xx_gmu.c`/`a6xx_hfi.c` (v6.12 copies external, `gpu-fw/`), not downstream kgsl.

The image is headerless ("legacy" in mainline): the whole file is written to
`ITCM_START` (`0x1B400` -> GMU byte offset `0x3000`, ITCM 16 KiB then DTCM 16 KiB
contiguous). Mode 6 does that inside the mode-5 window, then reads every word
back. It writes only if `CM3_SYSRESET == 1` was just read; the CM3 is never
released. Report: `SWEET GPU: GMU fw ...` (size, FNV-1a, words written/checked/bad).
TCM contents are lost when CX collapses afterwards; nothing else is written.

# 0087 — read-only GPU SMMU inventory (`sweetgpu=7`)

Mode 7 = mode 6 plus, in the same window (needs the two GCC bus branches, which
are the SMMU's `mem_clk`/`mem_iface_clk` in the downstream DT), a read-only map of
the kgsl SMMU at `0x05040000` (`0x10000`, DT `qcom,kgsl-smmu-v2`):

- global: `sCR0 sCR1 sCR2 sACR IDR0 IDR1 IDR2 IDR7 sGFSR sGFSYNR0`;
- `SMR`/`S2CR` entries, count = min(IDR0.NUMSMRG, 8);
- `CBAR` and context bank 0 (`+0x8000`, DT gfx3d_user `gpu-offset 0x48000`):
  SCTLR, TTBR0, TCR, FSR, count = min(IDR1.NUMCB, 4);
- `+0x6000` (DT `qcom,micro-mmu-control`, the GMU micro-MMU).

Each global read is announced first. No writes. Purpose: learn whether ABL/hyp left
the SMMU in bypass, faulting or owned state before designing the GMU stream 4/5
mappings (HFI queue table and log memory must be visible to the GMU).

# 0088 — GMU stream context bank + ATOS check (`sweetgpu=8`)

Mode 8 = mode 7 plus, in the same window, a self-contained SMMU programming test:

- Preconditions (else nothing allocated or written): sCR0.CLIENTPD clear, at least
  4 stream groups and 4 context banks, and for group/CB **3**: `SMR3`=0, `S2CR3`=
  `0x000200ff` (ABL default), `CBAR3`, `CBA2R3`, `SCTLR`, `TTBR0`, `TCR` all 0.
- One 16 KiB contiguous kernel page (`kmem_alloc_contig`, PA must be < 2^36):
  4 KiB tables L1 @0, L2 @0x1000, L3 @0x2000, data page @0x3000, cleaned to the
  point of coherency. 32-bit VA (T0SZ 32): L1[1] -> L2, L2[256] -> L3, L3[0] ->
  data page: **IOVA 0x60000000 -> data page** (mainline's GMU dummy-page IOVA).
  Page attributes: AF, inner-shareable, AP RW, nG, XN, MAIR attr0 = 0x44 (normal
  non-cacheable), non-cacheable table walk.
- Context bank 3: CBA2R VA64, CBAR type 1 (stage 1, stage 2 bypass), TCR/TCR2
  (T0SZ 32, 4 KiB, PASIZE 36 bit, EPD1), TTBR0, MAIR0, TLB invalidate, SCTLR
  `M|TRE|AFE|CFRE` (no fault interrupt); then `S2CR3` = translate/CB3 and `SMR3` =
  valid | stream **5** (GMU kernel stream) last.
- Check with the SMMU's own ATOS (CB `ATS1PR` +0x800, `ATSR` +0x8f0, `PAR`
  +0x50): 0x60000000 and 0x60000fff must give the data page, 0x60001000 and
  0x20000000 must fault. No master (GMU/GPU) ever uses the context.
- Restore SMR3, S2CR3, SCTLR, TTBR0, TCR, TCR2, MAIR, CBAR3, CBA2R3 and flush the
  TLB; report the final register values. The 16 KiB page is kept (PERMANENT).

Host tests use an AArch64 walker model standing in for ATOS; only the phone
shows whether the real SMMU accepts these encodings. Report: `SWEET GPU: SMMU ctx ...`.

# 0089 — SMMU write transcript (`sweetgpu=8`, diagnostic)

0088 on the phone: ATOS gave all four expected results, but `S2CR3` stayed `0x3`
and `CBAR3` stayed `0x10000` after the restore writes (`SMR3` and `SCTLR` did
return to 0). 0089 changes only the diagnostics: every SMMU write now reads back
immediately and is reported (`SMMU ctx wr +off wrote=.. got=.. [MISMATCH]`); if the
ABL default is refused, `S2CR3` retries with `0x00020000` (type fault, CB 0) and
`CBAR3` with `0x20000` (stage 1, stage 2 fault); the final-state line and result
text now say when registers did not restore. State left behind is harmless
either way: `SMR3` invalid (group inactive) and `SCTLR`=0 (context disabled).

# 0090 — read-only RSC/PDC inventory (`sweetgpu=9`)

Mainline programs the GPU's RSC sequencer and PDC before the GMU boots
(`a6xx_gmu_rpmh_init`; for A618 PDC address offset 0x30090, TCS commands
0x30010/0x30000/0x30090). Before writing any of that, mode 9 reads, never
writes, in the mode-8 window:

- inside the GMU block: RSCC registers at `gmu+0x23000` (mainline dword indexes
  x4: RSC_STATUS0_DRV0, PDC_SEQ_START_ADDR, PDC_MATCH_VALUE_LO/HI,
  PDC_SLAVE_ID_DRV0, HIDDEN_TCS_CMD0_ADDR/DATA, OVERRIDE_START_ADDR, SEQ_BUSY_DRV0,
  SEQ_MEM_0_DRV0, TCS0/TCS3 DRV0 status) and `GMU_RSCC_CONTROL_REQ/ACK`
  (`0x24c1c`/`0x24c20`);
- `kgsl_gmu_pdc_cfg` `0x0b290000`: GPU_ENABLE_PDC (+0x4500), SEQ_START_ADDR
  (+0x4520), TCS0 control, TCS1/TCS3 CMD_ENABLE_BANK, TCS3 CMD0_ADDR;
- `kgsl_gmu_pdc_seq` `0x0b490000`: SEQ_MEM_0..4.

Every read is announced first; a protected region (bus error) would end the boot,
and then the announce lines in the persistent log are the evidence.
Report lines: `SWEET GPU: RSC ...`, `PDC ...`.

# 0091 — mainline RSC/PDC init (`sweetgpu=10`)

0090 on the phone (all reads fine, no faults): RSCC `PDC_SEQ_START_ADDR` 0x4520,
`PDC_MATCH_VALUE_LO/HI` 0x4510/0x4514 and `PDC_SLAVE_ID_DRV0` 1 were already set
(identical to mainline's values; `HIDDEN_TCS_CMD0_ADDR` 0x82204514), but the RSC
sequencer memory (`SEQ_MEM_0_DRV0`), every PDC register (ENABLE_PDC, TCS banks) and
the PDC sequence memory were all zero. `SEQ_BUSY_DRV0` 0, RSCC REQ/ACK 0.

Mode 10 runs mainline's `a6xx_gmu_rpmh_init` for A618 in order (47 writes, region
table in `gpu_rpmh_init[]`): RSCC init values and RSC uCode
`a7a506a0 a1e6a6e7 a2e081e1 e9a982e2 0020e8a8`; PDC uCode `febea1e1 a5a4a3a2 8382a6e0
bce3e284 002081fc`; PDC TCS1 (sleep: 0x30010<-1, 0x30000<-0, 0x30090<-0) and TCS3
(wake: 0x30010<-2, 0x30000<-2, 0x30090<-3; `pdc_address_offset` 0x30090 for A618);
`GPU_SEQ_START_ADDR`<-0, `GPU_ENABLE_PDC`<-0x80000001; then `a6xx_rpmh_stop`
(`GMU_RSCC_CONTROL_REQ`<-1, poll `RSC_STATUS0_DRV0` bit 16 up to 10 ms, REQ<-0).
Each write is read back at once; mismatches are counted and the first is reported.
Only if the 0090 state is unchanged (PDC disabled, sequencer memories empty, REQ 0,
SEQ_BUSY 0). The configuration is deliberately **left in place** (Android's driver
rewrites it at its next probe). 0x30000/0x30010 are the cx.lvl/mx.lvl ARC addresses:
the PDC TCS commands apply only on GPU RSC sleep/wake events, in the sleep/wake sets.
Report: `SWEET GPU: RPMH init ...`.

## 0093 — GMU buffers and per-page ATOS (`sweetgpu=11`)

Separate from GMU execution: keep CM3 in reset, replace the old single-page SMMU
probe in mode 11 with the full legacy GMU memory layout. Lower modes retain their
previous behavior; modes 0 and absent remain off. RSC/PDC init is still the
mainline sequence, including the nine diagnosed readback differences from 0092.

One 64 KiB contiguous, zeroed, permanent kernel allocation contains three 4 KiB
page-table pages followed by the 13 pages for dummy/debug/log/HFI. Physical
addresses must be 16 KiB aligned and the entire allocation fit below 2^36; every
16 KiB XNU page's physical address is checked for contiguity before SMMU writes.
Memory stays allocated for the temporary kernel's lifetime; no active mapping
survives the experiment. This bounds allocation to 64 KiB once per opted-in boot.

| Buffer | Allocation byte offset | GMU IOVA | Size |
| --- | --- | --- | --- |
| dummy | 0x3000 | 0x60000000 | 4 KiB |
| debug | 0x4000 | 0x60001000 | 16 KiB |
| log | 0x8000 | 0x60005000 | 16 KiB |
| HFI | 0xc000 | 0x60009000 | 16 KiB |

HFI header matches v6.12 `a6xx_hfi_init()` / `a6xx_hfi_queue_init()`: six table
words `{0,120,6,12,2,2}` (size is **bytes** in the actual initializer, despite the
header's dword comment), followed by two 12-word queue headers. Data queues are
at IOVA 0x6000a000 / 0x6000b000; type 0xa00 / 0xa04, capacity 1024 dwords,
status=1, rx/tx watermarks=1, rx_request=1, all other words zero. All tables and
buffers are cache-cleaned before enabling the context; no CPU accesses them while
ATOS uses the tables, and no GMU master ever runs. The SMMU mapping uses attr0
normal non-cacheable as in the previously measured single-page test.

Preconditions, each tested to issue zero SMMU writes on failure: CM3 reset=1 and
busy=0, full verified 32 KiB firmware; exact measured SMMU sCR0/IDR0/1/2 and
complete inventory/geometry; all five SMRs zero (so no other stream can use CB3);
S2CR3 either ABL fault 0x200ff or our previously measured inert 3, CBAR3 either 0
or 0x10000, CBA2R3=0, TTBR0=0, and all touched context control/attribute registers
zero. Allocation failure/null/alignment/range/discontinuity also refuse before
SMMU writes. Inert residual S2CR3/CBAR3 are accepted explicitly; their values alone
do not imply an active mapping.

Configure CB3 and exact SID5 match, with immediate readback of every programming
write; on mismatch restore immediately. Each 32-bit write readback is explicitly
masked with an ARM64 AND before promotion/comparison, because earlier GR0/GR1
read transcripts had dirty upper bits. Invalidate/sync the TLB with a 500 us bound
before enabling the context. Stop before enabling it if that sync fails. ATOS
checks both ends of all 13 pages, followed by faults at 0x5ffff000, 0x6000d000 and
0x20000000 (29 checks, each bounded by the existing 500 us ATOS helper).

Every exit after a SMMU write disables SMR3 first, disables SCTLR, invalidates /
syncs the TLB, clears TTBR/TCR/TCR2/MAIR/CBA2R and attempts the incoming
S2CR3/CBAR3 encodings. Log every write/readback plus final SMR/S2CR/SCTLR/CBAR,
FSR/sGFSR. Report `restored=1` only if incoming encodings were restored; separately
report `inactive=1` if all controls were cleared and the only differences are the
known inert S2CR3=3 / CBAR3=0x10000. A rollback TLB timeout is an error, even with
matching disabled. Then the existing clock/CX/ARC cleanup executes.

Host harness validates the complete HFI header and zeroed payload at the cache
clean, all 13 PTEs and 29 translations/faults; 38 refusal cases with write counting
and unchanged-MMIO checks; both inert starting states; refused ABL restore;
individual programming readback failures; ATOS/TLB timeouts; wrong mapped PAR /
unexpected successful out-of-range translation; lower-mode isolation and cached
replay without new writes or allocations. The inherited RSC SEQ_BUSY refusal
also now has its own test. Normal and ASan/UBSan suites and local arm64 compile
pass. Full CI 39293204273 subsequently passed with matching source artifacts;
0093 phone result remains pending.

## 0094 — pre-boot GMU register inventory (`sweetgpu=12`)

This is step 3, a separate measured patch after 0093's successful 29/29 ATOS
phone result. It adds a cached read-only inventory of 29 registers covering every
GMU control the first CM3 start will write, plus firmware-version and status words.
No wake request, start configuration, HFI trigger or CM3 release is added.

The table `gpu_preboot_regs[]` derives byte offsets directly from pinned v6.12
`a6xx_gmu.xml` dword indices multiplied by four. RSCC SEQ_BUSY includes the known
0x23000 base. The DTCM firmware-version word is 0x7000 + 0xff8*4 = 0xafe0, from
`a6xx_gmu_start()`. The table includes GENERAL_0/1/6/7 (the A6xx names explicitly
present in the XML); no guessed GENERAL_2..5 or A7xx-only offsets are read.

The dump runs after the buffer experiment disabled the mapping, still inside the
CX/GMU clock hold. Preconditions: buffer probe requested, no buffer error,
stage=3, passed=29, completed checks=29, inactive=1; then recheck live CM3 reset=1
and busy=0. Each condition has an independent refusal test with zero MMIO writes.
Each read is announced just before the access and cached for USB replay. Unknown
or unexpected values are printed as found; nothing is written to "fix" them.

Also normalize the narrow expected value in `gpu_buffer_set` with an explicit
ARM64 AND before the existing 32-bit store/comparison/log. On 0093, incoming
CBAR=0 promoted to a 64-bit diagnostic with dirty upper bits. The actual store
was already 32-bit zero; this fixes comparison/log width, not the MMIO value.
A regression test injects the exact observed `0xfffffe8f00000000` input and checks
that the expected diagnostic is 0 and the 32-bit store/readback remains 0.

Host checks compare all 29 offsets and snapshot values, prove no GMU/SMMU memory
changes or MMIO stores in the dump and every refusal, and cover mode-11 exclusion,
missing GMU/SMMU map, failed buffer gate, full mode-12 rollback and replay without
new allocations/writes. Normal and ASan/UBSan suites pass; local arm64 compile
passes. These are source/host results; full CI and phone inventory remain pending.
