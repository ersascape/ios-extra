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
- Patch 0156 mirrored Linux `cmd_db_get_header()` but the 39758346968 phone run
  still reports ACV missing. Candidate patch 0157 adds bounded read-only header
  summaries and ACV/A-name entry and aux diagnostics on lookup failure. The
  ASan/UBSan host test verifies a missing ACV cannot submit an RSC vote. Patch
  0157 is not built or phone-tested yet.

## Latest build and phone evidence

- CI `39758346968`, commit `8c8c00233ce086caf4ef840f02948d8e9520153c`, passed
  the XNU build and FP6 boot job. CI packaging was skipped because
  `FP6_STOCK_DTB_URL` is unset. Kernel SHA256
  `72a9a9d0166fd390caf96beeec39d4e08671f3285e18acadbbb58b0229cd5683`.
- Locally packaged with verified product ADT and stock Volcano DTB. Header-v2
  round-trip passed. Image:
  `/tmp/ios-extra-run-39758346968/package/fp6-gmu-cmdb-linux-lookup.img`, SHA256
  `1cf437c943cb94edbaaa5e0a0f6e62709f57c2d61bab4f9e3a2e2065c55f97fa`.
- One temporary boot reached USB ECM and captured 93 UDP packets. Decoded log
  `/tmp/ios-extra-run-39758346968/logs/phone-0156-cmdb-linux-lookup.txt`, SHA256
  `b40b04abf1a055af6b0906434b68b1550f1978b2b6914edbd1f67fc9621a3e84`; pcap
  SHA256 `2d44cac32e7e86131ea4fea5ac735d1b4510278acc1866b6229bc838d237e0e4`.
- SMMU walk, floors, clocks, timer, persistent-page checks, and firmware upload
  succeeded as in prior runs. Linux-style cmd-db lookup still reports missing
  ACV metadata and stops before CM3 release. Thus this boot did not execute GMU
  firmware or test HFI/GPU DMA. Optional SCM `GPU_INIT_CX_REGS` remains unavailable.

## Next debugging step

Patch 0156 mirrored Linux's ordered cmd-db name search but the phone still
reports ACV missing. Candidate patch 0157 adds bounded read-only summaries of
cmd-db headers and ACV/A-name entry/aux data on lookup failure. Its host test
checks missing ACV cannot submit an RSC command. Patch 0157 needs CI and phone
validation. Do not relax fail-closed behavior or guess a TCS vote.

Patch 0156 has passed host/source checks. Commit and push this focused candidate,
wait for CI, package with the known local ADT/DTB, then perform one temporary boot
to learn whether the live ACV lookup and bus vote are accepted. After an acknowledged vote, the next source
milestone is HFI table/start-message exchange with pre-mapped MEM_ALLOC handling
and explicit cache ownership. Only then implement a tiny GPU memory write and
readback. Rendering/Metal is later; no display change is expected from the
current vote patch.
