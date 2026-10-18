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
