# FP6 GPU continuation handoff

## Goal

Bring up the Fairphone 6 Adreno 810 GPU on this XNU port: GMU firmware and HFI,
bounded GPU memory execution, then the NativeAdreno/NativeMetal path. GMU firmware
startup and HFI controller initialization now succeed. No HFI message exchange,
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

- Patch 0159 adds a bounded HFI `CORE_FW_START` request/ACK exchange based on
  Fairphone Linux Gen8. CI `39766804611` passed and the packaged image booted
  once. The phone reported `irq=0x4 fw=0x900` after the request; bit 2 is DBGQ
  and `0xe00` is the firmware assertion mask. The bounded path reset CM3. The
  debug queue payload was not captured, so the assertion cause remains unknown.
- Linux sends warmboot scratch, perf/BW tables and optional feature/log
  controls before CORE_FW_START; patch 0159 did not. The phone reports HFI
  version `0x20070001` (2.7.1), selecting the `H2F_MSG_TABLE` format. Linux
  builds performance entries from the selected GPU pwrlevel bin plus live
  `gfx.lvl`, `cx.lvl`, and `mx.lvl` cmd-db ARC values, and its bandwidth table
  from DDR levels plus BCM metadata. Source those exact inputs and preserve the
  GMU debug queue on failure before the next build. The host harness's simulated
  ACK is not evidence of device firmware acceptance.

- Current source is commit `548673a33b397ef80cdbc701cd503903ab63118a` (patch
  0158), CI `39762347940` passed. The kernel was verified and packaged locally
  as `/tmp/ios-extra-run-39762347940/package/fp6-gmu-bootstrap-acv-width.img`,
  SHA256 `0c2e73788e98d3a0bbe768ee54e9f4989e3e88973cb2e82d7438ad76ae3f6c10`.
- One temporary phone boot accepted SH0/MC0 and fixed ACV width-zero votes;
  the DDR TCS acknowledged. CM3 firmware startup returned
  `FW_INIT_RESULT=0x100` and `HFI_CTRL_STATUS=1`. The bounded probe reset CM3
  successfully. Exact text and pcap hashes are in `NOTES.md` and `docs/GPU_LOG.md`.
- Patch 0154 adds the Linux-path minimum DDR vote before CM3 release: peak
  bandwidth `0x209a8e` kB/s, SH0/MC0 plus fixed ACV, with bounded RSC TCS
  completion and fail-closed reset behavior. Patch 0155 corrects the BCM address
  ID check. On hardware, SH0/MC0 metadata passes but ACV is not found. No vote
  command was issued in that run.
- Patch 0157's phone diagnostics found ACV at BCM ID 5 / address `0x00050068`
  with `unit=1`, `width=0`, `vcd=12`, length 8. Linux marks ACV fixed and ignores
  width; the old parser incorrectly required width nonzero. Candidate patch 0158
  permits zero width only for fixed entries, retains the SH0/MC0 check, and
  updates the host fixture to the measured record. ASan/UBSan, CI, and the phone
  test pass. This result validates the DDR vote and GMU/HFI controller startup,
  not HFI messaging or GPU execution.

## Prior build and phone evidence

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

## Next implementation step

Patch 0157's cmd-db dump identifies ACV at `0x00050068`, width zero, which is
valid because Linux treats ACV as a fixed vote. Patch 0158 allows zero width only
for that fixed request; the host test rejects zero-width SH0 while allowing fixed
ACV. Patch 0158 is validated by CI and on hardware. Do not relax fail-closed
behavior or guess a TCS vote.

The next source milestone is HFI queue setup and a bounded core-firmware start
message, then handling pre-mapped MEM_ALLOC requests with explicit cache
ownership. Mirror the Linux startup order and request/reply formats; keep CM3
reset as the failure containment path. Only after a measured HFI exchange should
the code attempt a tiny GPU memory write/readback. Rendering and NativeMetal
integration remain later milestones.
