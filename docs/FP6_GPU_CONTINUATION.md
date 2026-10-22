# FP6 GPU continuation handoff

## Goal

Bring up the Fairphone 6 Adreno 810 GPU on this XNU port: GMU firmware and HFI,
bounded GPU memory execution, then the NativeAdreno/NativeMetal path. The firmware
upload and HFI controller initialization previously succeeded, but no HFI message,
GMU DMA, GPU command, rendering or Metal work has succeeded yet.

## Repository and safety

- Worktree: `/home/ersa/Dev/ios-extra-main`, branch `main`, remote
  `ersascape/ios-extra`.
- Mainline/XNU experiment patches are in `xnu/patches/`; state/history are in
  `NOTES.md`, `HANDOFF.md`, `docs/GPU_GMU_BOOT.md`, and `docs/GPU_LOG.md`.
- Fairphone Linux source is local and read-only at
  `/home/ersa/Dev/android_kernel_fairphone_sm7635` and
  `/home/ersa/Dev/android_kernel_fairphone_sm7635-modules`.
- Use only temporary `fastboot boot`; no partition writes, GPT changes or
  `fastboot getvar`. Always recheck `fastboot devices`, redact serials, and use
  `tools/gpu-phone-test.py` so logs land under `/tmp`.
- Avoid needless full builds: use the repo CI for kernel builds and local
  cross-compiles/host tests for source iteration.

## Current source state

- HEAD `4f68fcb011d5cbec92485f5b076a470140560f59` changes patch 0154's cmd-db
  filter from slave ID 3 to ID 5. It passes CI `39752494051` and the targeted
  `tests/test_fp6_gmu_boot.py` ASan/UBSan host harness.
- Patch 0154 implements a Linux-equivalent bootstrap DDR BCM vote before CM3
  release. It reads the cmd-db at `0x81c60000`, requests the stock FP6 minimum
  peak DDR rate (`0x209a8e` kB/s = 2,136,718 kB/s), and sends SH0/MC0/fixed ACV
  via one idle ACTIVE RSC TCS. It bounds completion and keeps CM3 reset if any
  precondition or acknowledgment is uncertain.
- The first 0154 image used the wrong cmd-db slave ID 3 (ARC). ID 5 is BCM per
  Fairphone `include/soc/qcom/cmd-db.h` (`ARC=3, VRM=4, BCM=5`). Changing to 5
  did **not** fix lookup: the second phone log still says
  `bootstrap BCM metadata missing name=SH0`. No BCM writes occurred on either
  boot. Do not treat the active vote as hardware-validated.

## Latest build and phone evidence

- CI `39752494051`, commit `4f68fcb...`, passed. Kernel SHA256
  `1d67f88580dffa942cbc54e1b8b68c5d6f360de31dac6c16d8c3512b56eff9e8`.
- Header-v2 image (includes `fp6usb=2` for ECM):
  `/tmp/ios-extra-run-39752494051/package/fp6-gmu-bootstrap-ddr-vote-cmdb5.img`
  SHA256 `fe97c9fadae1388605b37124550677f596201c3f51bdc151afd6e80d4f835494`.
  It contains the verified local FP6 ADT and Volcano DTB; package round-trip
  passed. Full manifest is beside the image.
- One authorized temporary boot reached ping and captured 96 UDP packets,
  19,232 decoded log bytes. Decoded log:
  `/tmp/ios-extra-run-39752494051/logs/phone-0154b-bootstrap-ddr-vote.txt`,
  SHA256 `dc1eb8596dfaee7c70f0c8a40f056468c235fbf2b9f513361d10cd68aae2f602`.
  Pcap SHA256 `c94751cca1fbba39e8129d11d3e3da7ae9ff5bb782498d522cd0a652f918b4d9`.
- Observed before the refusal: SMMU software page-table walk passes, MX/CX
  floors and GMU clocks succeed, CX timer seeds, 159 persistent pages are
  checked, firmware upload returns 0, firmware version words are readable.
  The optional SCM `GPU_INIT_CX_REGS` service is unavailable as on previous
  boots. The code then refuses before CM3 release because SH0 metadata lookup
  fails. Thus this boot did not execute GMU firmware or test HFI/GPU DMA.

## Next debugging step

Inspect why the cmd-db lookup for BCM ID 5 cannot find `SH0`, without another
boot until source-based possibilities are exhausted. Linux `cmd_db_get_header()`
scans all slave headers and compares an 8-byte zero-padded resource ID. The XNU
reader currently assumes an 8-entry header at byte 8, 24-byte entries starting
at byte 144, and BCM slave ID 5. Existing `fp6_arc_level()` succeeds on the
phone using the same header/entry offsets for ARC ID 3, so the base mapping and
ARC layout are real. Compare actual BCM enum/ID, entry alignment, DB version and
reserved-memory mapping against Linux and the stock DT. If another phone dump is
needed, add a bounded read-only diagnostic that logs header fields and names;
do not relax the fail-closed guard or send a guessed TCS vote.

Once metadata lookup is verified, run the targeted host test and compile,
commit/push one focused patch, wait for CI, package with the known local ADT/DTB,
then perform one temporary boot. After an acknowledged vote, the next source
milestone is HFI table/start-message exchange with pre-mapped MEM_ALLOC handling
and explicit cache ownership. Only then implement a tiny GPU memory write and
readback. Rendering/Metal is later; no display change is expected from the
current vote patch.
