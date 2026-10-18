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
