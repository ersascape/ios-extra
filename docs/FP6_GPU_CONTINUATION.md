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

- Patch 0160 mirrors the bounded Linux Gen8 pre-start sequence:
  GPU performance table, BW vote table, HWSCHED and KPROF controls, then
  CORE_FW_START. The GPU row is the stock FP6 362 MHz point, BCM words contain
  both AB/X and IB/Y values, and ACV perfmode stays off for the reduced DDR
  table. Optional ACD/BCL/CLX/IFPC inputs still need source work. Host HFI
  protocol/table checks, including bad ACK sequence rejection, pass under
  ASan/UBSan; the broad GPU probe harness passes, and the changed XNU source
  compiles against CI buildtree `39766804611`.
  Commit `5243eb1f6e8b0590e580fd66e604ea34a5faa0f2` passed CI `39775328855`
  and the local header-v2 image package round-trip. Kernel SHA256 is
  `ddce0dae8fd220bcd9a238b3500cf5693af4c46bd72ee0d18dd123f1bfca4d14`; image
  `/tmp/ios-extra-run-39775328855/package/fp6-gmu-hfi-prerequisites/fp6-gmu-hfi-prerequisites.img`
  SHA256 `f63635017fa022319c4f6c6a6cb29224aec193edea49372eb4dc13ae85c2db8e`.
  No 0160 phone observation exists yet. The host responder synthesizes ACKs;
  it does not model firmware validation.
- Patch 0161 adds event-aware HFI handling: zero-offset counter registration
  replies and bounded refusal of F2H MEM_ALLOC. It passed CI `39779962789` and
  was packaged locally as documented in `NOTES.md`; it has no phone result.
- Current local candidate 0162 handles only non-secure GMU-only MEM_ALLOC with
  permanent kernel backing and a live SMMU page-table append/TLBI/sync. Host
  normal and ASan/UBSan tests cover a synthetic successful request and a
  GPU-access refusal. Arm64 object compile against buildtree `39775328855`
  reports 0/1 failures. The actual phone descriptor and firmware acceptance
  are unknown; no CI build or phone test exists. User is testing Android, so
  defer device commands.
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

Next: finish review and commit 0162, then run one CI build and package. Wait for
the user's Android work before any device test. Once the phone can be tested,
capture the real MEM_ALLOC descriptor and determine whether this GMU-only subset
is sufficient; widen it only for observed request types and flags. Then continue
to a bounded GPU memory write/readback. Rendering and NativeMetal integration
remain later milestones.
