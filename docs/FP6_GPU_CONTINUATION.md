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

- Baseline HEAD `8462f999359f501ec523daaf1852693e3f384db6` (patch 0155) passed
  CI `39755620038`; targeted `tests/test_fp6_gmu_boot.py` passes with
  ASan/UBSan. CI kernel SHA256:
  `72a9a9d0166fd390caf96beeec39d4e08671f3285e18acadbbb58b0229cd5683`.
- Patch 0154 adds the Linux-path minimum DDR vote before CM3 release: peak
  bandwidth `0x209a8e` kB/s, SH0/MC0 plus fixed ACV, with bounded RSC TCS
  completion and fail-closed reset behavior. Patch 0155 corrects the BCM address
  ID check. On hardware, SH0/MC0 metadata passes but ACV is not found. No vote
  command was issued in that run.
- Candidate patch 0156 mirrors Linux `cmd_db_get_header()` by scanning populated
  slave headers in order and tracking the selected header ID. It requires SH0/MC0
  to resolve as BCM ID 5 and validates address/header consistency and auxiliary
  data. Host fixture places ACV in the following ARC header. ASan/UBSan passes;
  patch dry-run passes against the exact CI 39755620038 buildtree. Patch 0156 is
  not built or phone-tested yet.

## Latest build and phone evidence

- CI `39755620038`, commit `8462f999359f501ec523daaf1852693e3f384db6`, passed
  the XNU build and FP6 boot job. CI packaging was skipped because
  `FP6_STOCK_DTB_URL` is unset. Kernel SHA256 is recorded above.
- Locally packaged with verified product ADT and stock Volcano DTB. Header-v2
  round-trip passed. Image:
  `/tmp/ios-extra-run-39755620038/package/fp6-gmu-bcm-address-id.img`, SHA256
  `0d4ff5ab9ee7aef5a1139841bcf6a909ed20d0be7ac73c65b43cf7899bbbf24a`.
- One temporary boot reached USB ECM and captured 93 UDP packets. Decoded log
  `/tmp/ios-extra-run-39755620038/logs/phone-0155-bcm-address-id.txt`, SHA256
  `6a7bb87ec85d75558f95e9b1e81e6ec5d75e13657054ce097c0ed47a56e7ca0e`; pcap
  SHA256 `d437f9b66424434075057c7951f4fa7a40967c6f57f2f1e9e78d3d99b72b2ea7`.
- SMMU walk, floors, clocks, timer, persistent-page checks, and firmware upload
  succeeded as in prior runs. The log then reports missing ACV metadata and
  stops before CM3 release. Thus this boot did not execute GMU firmware or test
  HFI/GPU DMA. The optional SCM `GPU_INIT_CX_REGS` service remains unavailable.

## Next debugging step

Patch 0155 corrected post-lookup address validation; the phone shows SH0/MC0
pass and ACV missing. Linux `cmd_db_get_header()` searches populated slave
headers in order, but the old parser filtered to ID 5. Candidate patch 0156 now
mirrors Linux name lookup, records the selected header ID, requires SH0/MC0 to
be BCM ID 5, and validates address/header consistency and aux data. Its host
fixture places ACV in ARC header 3; ASan/UBSan passes and the patch dry-runs on
CI buildtree `39755620038`. Patch 0156 is not yet built or phone-tested. Do not
relax fail-closed behavior or send a guessed TCS vote.

Patch 0156 has passed host/source checks. Commit and push this focused candidate,
wait for CI, package with the known local ADT/DTB, then perform one temporary boot
to learn whether the live ACV lookup and bus vote are accepted. After an acknowledged vote, the next source
milestone is HFI table/start-message exchange with pre-mapped MEM_ALLOC handling
and explicit cache ownership. Only then implement a tiny GPU memory write and
readback. Rendering/Metal is later; no display change is expected from the
current vote patch.
