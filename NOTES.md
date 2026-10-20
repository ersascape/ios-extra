# ios-extra — current state

Last updated 2026-10-20 after adding the FP6 ADT profile. Read [HANDOFF.md](HANDOFF.md) for how to
continue and [AGENTS.md](AGENTS.md) for the rules. The per-step history (images,
hashes, CI runs, raw numbers) is [docs/GPU_LOG.md](docs/GPU_LOG.md); the hardware and
mainline reference is [docs/GPU_GMU_BOOT.md](docs/GPU_GMU_BOOT.md); the per-patch
design is [docs/GPU_CX_EXPERIMENT.md](docs/GPU_CX_EXPERIMENT.md).

## FP6 hardware bringup and pthread/gPanicBase fixes (2026-10-20)

- On-device observation with packaged header v2 boot image (containing stock DTB):
  ABL booted successfully into shim, simple-framebuffer splash activated at 0xe3940000 (1116x2484).
  XNU initialized console, IOKit matched platform and boot CPU ("1 of 1 CPUs initialized"),
  entered BSD, and halted with:
  `panic pthread kernel extension not loaded pthread_shims.c:318`.
  Also observed:
  `debug_log_init: Error!! gPanicBase is still not initialized` and
  `Serial requested, consistent debug disabled or debug boot arg not present`.
- Root causes:
  1. Built-in libpthread was guarded by `CURRENT_MACHINE_CONFIG == SWEET` and `ARM64_BOARD_CONFIG_SWEET`.
     `sweet_pthread_register` was never compiled or registered during early boot on FP6.
  2. `gPanicBase` was uninitialized because no `pram` node exists in the bootstrap ADT, causing
     `check_for_panic_log` to return early.
  3. `kdp_udp.c` fell back to serial KDP warning because `PE_consistent_debug_enabled()` returned false.
- Fixes staged in patch 0099:
  1. Enabled `sweet_libpthread` and `sweet_hfs` for `FP6` in `bsd/conf/Makefile.template`,
     `bsd/sys/pthread_internal.h`, `bsd/pthread/sweet_pthread_*.c`, `bsd/kern/sweet_amfi.c`,
     and `iokit/Kernel/IOService.cpp`.
  2. In `pexpert/arm/pe_init.c`, provided a 256 KiB static panic buffer fallback when `pram` is absent,
     initializing `gPanicBase` and `panic_info` cleanly.
  3. In `pexpert/arm/pe_consistent_debug.c`, provided a static debug registry fallback for FP6, and in
     `osfmk/kdp/kdp_udp.c`, bypassed serial KDP when serial is not explicitly requested.
  4. Registered `QcomPlatformExpert` and `QcomCPU` classes in `SweetPlatformExpert.cpp` and `SweetCPU.cpp`
     and added corresponding entries in `KernelConfigTables.cpp`.
  5. Verified patch 0099 applies with zero errors against the baseline.

## FP6 shim packaging (2026-10-20)

- Patch audit: Phoenix edits to 0016 broke later patch contexts. Restored 0016
  and placed board integration in 0099. A clean xnu-8796.141.3 replay applied
  all 99 local patches and four selected Ventura harness patches (103/103).
- Added explicit FP6/Phoenix MASTER configs and FP6 header export; FP6 shares
  portable crypto/RNG and architecture CPU/GIC code with a one-CPU limit.
  Sweet hardware driver registration remains disabled for FP6. These source
  changes await full CI compilation and hardware validation.
- Build preparation now selects the four applicable upstream patches, aborts
  on every patch failure, stages portable dependencies for FP6/Phoenix and
  defaults the workflow to FP6. Different targets have separate concurrency.

- Inspected user-selected successful CI run `39371823683` at `4e7fdf0`.
  Artifact `12242266868` contains `kernel.development.sweet`, SHA256
  `18f69070e456841cc4d400f6d6438b7ede02eb2e6b0429d4b231da88e7d9eddc`,
  and no FP6 ADT artifact. A source commit mentioning FP6 did not select FP6
  for this push build. Do not package that kernel for FP6.
- FP6 build run `39373440958` at `24370bb` generated the ADT, then failed during
  XNU compilation; the `fp6-boot` job was skipped, so no matching kernel/boot
  image exists. The failed compile pulled in SWEET HFS and pthread features
  through the shared master config, and the portable BearSSL include paths were
  only enabled for SWEET.
- Corrected the config scope: SWEET HFS is machine-specific; FP6 no longer
  enables Sweet HFS or its bundled pthread provider. FP6 still stages the
  portable crypto implementation, with compiler include paths enabled for
  FP6. Run `39374822879` reached patch 0031, which requires staged HFS source
  even when that filesystem is disabled. Restored HFS source staging for FP6;
  this stages files for later patch contexts but does not enable HFS in its
  machine config. Retry CI after this fix. Full build and phone boot are pending.
- Inspected failed CI run `39375193145` at `552b6b2`. All compilation units
  succeeded; the final link `kernel.development.fp6.unstripped` failed on two
  undefined symbols: `_sweet_sample_task` from `sweet_sample.o` (unconditionally
  compiled by bsd/conf/files while its implementation in osfmk/kern/exception.c
  was guarded by ARM64_BOARD_CONFIG_SWEET) and `_sweet_secondary_entry` from
  `SweetCPU.cpo` (PSCI CPU_ON stub in osfmk/arm64/start.s was guarded by SWEET).
  In patch 0099, guarded `bsd/dev/sweet_sample.c` under ARM64_BOARD_CONFIG_SWEET
  and added FP6 guards to `osfmk/arm64/start.s` for `sweet_secondary_entry`, MPIDR
  Aff1 extraction, TLB/cache invalidation and SCTLR check bypass. Patch 0099
  verified to apply cleanly against baseline `b097596`. Ready to commit and push.

- Local LLVM build now links the shim and packages an unsigned Android v4 image.
  The local packaging check used placeholder payload bytes only: shim and ramdisk
  unpack byte-for-byte. This is not a tested XNU boot image or a phone observation.
- `tools/fp6-package.py` consumes a kernel and ADT from the same CI run, builds
  the FP6 shim, verifies packaged components and writes hashes/provenance.
  The new `fp6-boot` CI job uploads `fp6-fastboot-boot` after an FP6 kernel build.
  Its first CI execution failed before packaging. Pushes now use the FP6 target
  by default; select other targets explicitly for manual runs.
- FP6 shim failures halt instead of entering Sweet diagnostic probes. Missing
  runtime framebuffer leaves the display untouched. The loader searches aligned
  payload headers after possible vendor ramdisks and validates segment extents.
- Header v4 relies on the installed vendor_boot/DTBO and ABL for the runtime FDT.
  Acceptance by FP6 ABL, live framebuffer availability and XNU handoff remain
  unmeasured. No flashing or phone commands were performed.
- User wants the new run's matching kernel/ADT, followed by driver bring-up one
  kext at a time after a working initial boot. Do not use the older kernel run.

## Fairphone 6 platform audit (2026-10-20)

- Began a source-only audit for Fairphone (Gen. 6), device name `FP6`.
  Fairphone identifies it as Snapdragon 7s Gen 3 / SM7635. Mainline Linux has
  `milos-fairphone-fp6.dts` with `fairphone,fp6` and `qcom,milos` compatibles.
- QCM6490 is Fairphone 5, not Fairphone 6. No QCM6490 code or FP5 target was
  added as part of this work.
- An experimental `MACHINE_CONFIG=FP6` compile target exists in patch 0004,
  using an ARMv8.2+crypto baseline and the sourced 8-core / 3 cluster counts.
  `tools/mkadt.py --device fp6` now generates an FP6 ADT profile with sourced
  CPU affinity/topology, GICv3 and UFS ranges, Fairphone identity, and the
  upstream Linux FP6 framebuffer address and dimensions. It requires
  no RAM arguments: the shim will read the bootloader FDT, exclude reserved
  ranges, initrd, framebuffer and its own image, then patch `dram-base` and
  `dram-size` in the ADT and boot args. The LineageOS DTS leaves RAM as
  `<0 0 0 0>`. The XNU workflow accepts `MACHINE_CONFIG=FP6` and emits the
  profile ADT artifact. Host syntax/serialization checks passed, but there has
  been no FP6 XNU build, CI run, FP6 shim image, or phone observation. See
  [docs/FAIRPHONE6.md](docs/FAIRPHONE6.md).
- Persistent LineageOS source checkouts are available under `/home/ersa/Dev`:
  `android_kernel_fairphone_sm7635` and
  `android_kernel_fairphone_sm7635-modules`. The device tree and vendor DTS
  reference remain under `/tmp/lineage-fp6-device` and
  `/tmp/lineage-fp6-devicetrees`.

## POCO X2 / Phoenix support (2026-10-20)

- Inspected `aospa-phoenix/android_kernel_xiaomi_phoenix` at
  `c01153e9ba446642640749077a19467e7e0094f5` in `/tmp` (source only; clone is
  not part of this repository). It confirms the shared SM7150 platform and
  Adreno 618 family. Phoenix and Sweet both have 1080x2400 panels with 120 Hz
  maximum timing; the Phoenix source describes WLED and 30–120 Hz modes, while
  Sweet uses OLED and 60/120 Hz modes.
- Added a `PHOENIX` XNU machine config that reuses the existing SM7150 board
  definition, platform expert and GPU path. Added `--device phoenix` to
  `tools/mkadt.py`; generated Phoenix trees use the `xiaomi,phoenix` compatible
  and a distinct synthetic ECID. The iOS-facing D22AP / iPhone10,3 identity is
  retained for the bundled iPhone X userland.
- This is source inspection and code editing only. No tests, XNU build, CI run,
  phone boot, or display observation was performed. The XNU/platform changes
  and Phoenix ADT have not yet been built or tested on hardware. See
  [docs/PHOENIX.md](docs/PHOENIX.md).

## What this repo is

Driver playground for the XNU/iOS 16 port to the Redmi Note 10 Pro (`sweet`,
SM7150, Adreno 618). The target is a real Adreno driver; the display today is
CPU-rendered. Public repo `dipa-studio/ios-extra`, branch `main`. The user made it
private overnight, then authorized restoring public visibility on 2026-10-19;
GitHub now confirms public. Kernel builds use this repo's GitHub Actions
(`.github/workflows/xnu.yml`, macOS runner, ~6 min).
`/home/dipa/ios-sweet` belongs to other agents: read-only for us.

## Where the GPU bring-up stands (all measured on the phone unless noted)

| Patch | `sweetgpu=` | What it does | CI run | Phone |
| --- | --- | --- | --- | --- |
| 0080 | 1 | read-only GCC/GPUCC clock + GDSC inventory | 39152959124 | ok |
| 0081 | 1 | cache that inventory, replay it over USB | 39154941656 | ok |
| 0082 | 2 | command-DB ARC level tables (`gfx/cx/mx.lvl`) | 39157726409 | ok |
| 0083 | 3 | MX+CX LOW_SVS votes via RPMh ARC, CX GDSC on/off, rollback | 39159151996 | ok |
| 0084 | 4 | GMU clock tree (GPLL0/2 gate, RCG 200 MHz, cx-gmu branch), rollback | 39161422925 | ok (first build refused: wrong precondition) |
| 0085 | 5 | GCC memnoc/ddrss-axi branches + first GMU register reads | 39162789741 | ok |
| 0086 | 6 | GMU firmware (`a630_gmu.bin`, staged at build) into ITCM/DTCM, readback | 39164168730 | ok, 0/8192 mismatches |
| 0087 | 7 | read-only GPU SMMU inventory | 39165446245 | ok |
| 0088-0089 | 8 | stream 5 -> CB3, tiny 4 KiB page table, ATOS check, restore (+ write transcript) | 39167833774 / 39168706195 | translations correct; S2CR3/CBAR3 refuse restore |
| 0090 | 9 | read-only RSC/PDC inventory | 39169517724 | ok |
| 0091 | 10 | mainline A618 RSC/PDC init (48 writes, readback), RSC stop handshake | 39170396365 | handshake ok, 9/48 writes did not read back |
| 0092 | 10 | same, logs every mismatch + reads the table first | 39171199100 | stop handshake ok; all 9 mismatches identified |
| 0093 | 11 | 13 GMU buffer pages, mainline HFI layout, 29 ATOS checks | 39293204273 **passed** | 29/29 ATOS; inactive=1, restored=0 |
| 0094 | 12 | read-only inventory of 29 pre-boot GMU registers | 39297388718 **passed** | 29/29 registers read; home screen confirmed |
| 0095 | 13 | bounded TCM retention + RSC wake/stop, CM3 reset | 39300239967 **passed** | wake/stop and full sampled state restore; home screen |
| 0096 | 14 | read-only GMU IRQ masks/status, fence and RPMH state | 39303111412 **passed** | 6/6 reads; home screen |
| 0097 | 15 | GMU interrupt mask/restore | 39305068882 **passed** | AO reads 0x3f; guard stops, restored; home screen |
| 0098 | 15 | exact measured AO readback; continue mask test | 39307039113 in progress | not tested; no image yet |

The user confirmed the home screen after every boot up to 0097. Each stage runs
inside the previous one's window (`sweetgpu=N` includes all lower modes) and undoes
itself except: SMMU `S2CR3`/`CBAR3` (left inert: `SMR3` invalid, `SCTLR` 0), the
GMU RCG (left at `0x602`), and the RSC/PDC configuration of 0091 (left in place).

**The GPU core (GX) has never been powered and nothing has executed on the GPU.**
Rendering is still CPU. The GMU processor has never been released from reset.

## Immediate next action

0095 phone test passed: RSC wake ACK=3 (bit 1 set), SEQ_BUSY=0, stop
STATUS=0x01010006, all six sampled control/state words restored. Retention 1->0,
CM3 reset remained 1 and GX GDSCR stayed 0x00222001. User confirmed home screen.
Raw values in GPU_LOG. No firmware execution or GPU command yet.

0096 (mode 14) passed at 18:39:28 UTC, user confirmed home screen. Both GMU
interrupt mask words=0, both status words=0, AO fence control=0, RPMH power
state=0x0f; raw values in GPU_LOG. All lower probes/cleanup still pass. Full CI
39303111412 built edd2b796ed7ff02434c42942c490543c17f95456 and artifacts match the
local source. 0097 separately tested the first mask with CM3 still reset (result below).
0097 (mode 15) reached the readback guard at 18:53:52 UTC: wrote AO mask
0xffffffff, got 0x3f, restored 0; second mask untouched. All sampled state/lower
cleanup restored, reset=1 and GX off. User confirmed the home screen. Green CI
39305068882 built 01dbc6e5571eacdca32f7c0d60bc34ce0d77ab00; artifacts matched.
0098 implements only that exact AO tuple exception, retaining mode 15 and the
mainline all-ones write. Normal and ASan/UBSan suites pass, including 42 rejected
alternative AO/HFI readbacks, all 20 zero-write refusals and failure/rollback tests;
arm64 compile 0 of 1 failed. Baseline c242eb7 (measured 0097); isolated diff equals
0098 patch, committed/pushed at edab65c998a917d5e450b730aa4d0ff2e8e6032e. CI 39307039113
is in progress at handoff; verify it succeeds and verify/package its artifacts before
the phone test. No 0098 image or phone result exists at this handoff.

An unvalidated first-start draft is external only (`ios-extra-work/gmu-first-start-draft.patch`),
based on 0095; do not apply it unchanged. It still needs IRQ-mask/clear gates,
complete host failure tests and reconciliation with 0096–0098 measurements before
full CI or phone use. It also needs SMMU global-fault interrupt containment: measured
sCR0=0x00200626 has GFIE/GCFGFIE set. No sCR0 write has been made. See GPU_GMU_BOOT
and the first-start review in HANDOFF. No first-start image exists.

## User-visible iOS observation (2026-10-19)

The user reports missing wallpaper and some white Settings/widgets in this image;
a separate image assembled from ios-sweet patches reportedly has working wallpaper
and widgets (still only three apps). The comparator build/root/assets have not
been identified or reproduced here; cause and relationship to GPU experiments
are unestablished. Home-screen arrival does not mean the UI is fully working.
The user asked to continue GPU bring-up; no userland repair or upstream-tree
changes are being made as part of this work.

## Additional source reference

The user supplied apple-silicon-anyos-project. Pinned source review at
59fd73aac4ae386939bc69dc58dffbce1b2167b2 is in GPU_EXTERNAL_DRIVERS: candidate
AIR/SPIR-V/Vulkan reuse for later integration, but a QEMU/macOS paravirtual
transport and no demonstrated sweet/Adreno path. No code imported or executed.

## Hard constraints (unchanged)

- Always check `fastboot devices` (serials redacted) before asking for fastboot.
  If exactly one device is already there, announce and run the authorized pending
  temporary test; ask only when none is present, stop if multiple are present.
- Temporary `fastboot boot` only. No flashing, no partition/GPT changes, keep
  bootloaders, recovery, modem, persist and the backups. Never `fastboot getvar`.
  The user must put the phone in fastboot; never reboot it unannounced.
- Keep serials, device dumps and Apple artifacts out of Git. The GMU firmware is
  downloaded at build time (`xnu/patches/0086-stage-gpu-firmware.sh`), never committed.
- Report source reading, a green build and a phone result as three different things.

## Workspace map (outside Git)

`/run/media/dipa/android/ios-extra-work/`: `buildtree/xnu` (isolated XNU tree; local
git commits mark each CI-validated baseline, `sweet_gpu_fw.h` is untracked there),
`out-NNNN/` + `ci-NNNN/` (latest CI kernel and build tree), `gpu-fw/` (linux-firmware
clone `lf/`, mainline v6.12 sources, register xml), `logs/` (`phone-*.pcap/.txt`,
`ci-0081.log` which `tools/xnu-cc.py` needs, sanitized fastboot output), `objects/`,
`shim-out/` (symlinked as `shim/out`). Keep only the latest image/kernel; old ones are
reproducible from the manifests. 136 GB free on the external drive; the home disk is
small, so keep large files external.

## Tools (all tracked, `tools/`)

`gpu-package.py` (kernel -> temporary boot image + manifest), `gpu-phone-test.py`
(capture, boot once, replay window, decode), `gpu-decode-pcap.py` (UDP log from a
pcap), `phone-ecm-host.py` (host side of the USB ECM link), `xnu-cc.py` (single-file
arm64 compile against the CI build tree). Host tests: `python3 -W
error::ResourceWarning -m unittest discover -s tests` (also with
`IOS_EXTRA_CFLAGS="-fsanitize=address,undefined -fno-sanitize-recover=all -g"`).

## FP6 Actions failure review (2026-10-20)

- Reviewed failed FP6 run `39412735706` at `83a712822ef0855bf653f00ee2938b8845766352`.
  The compile reached the XNU build and reported an undefined `kDbgIdTopLevelHeader`
  in the FP6 consistent-debug fallback, plus missing staged `sweet_libpthread/kern/*.c`
  includes. Downloaded that run's `xnu-buildtree` artifact and confirmed XNU 8796's
  `consistent_debug.h` documents the top-level record field but does not define that
  symbol. The fallback now supplies a local CDBG-HDR record ID. The libpthread staging
  script now stages the immutable matching provider for FP6, consistent with patch
  0099 compiling its provider sources. Pending a new Actions result.
- Reviewed FP6 Qualcomm constants in patch 0099 and the generated ADT: FP6 uses
  GIC redistributor stride `0x40000`, virtual timer INTID 27, one CPU for initial
  bring-up, and SM7635/Volcano compatible strings. Patch 0099 corrects the initial
  FP6 header's placeholder stride. No device or display driver behavior is inferred
  from these build definitions; the framebuffer splash is bootloader-provided.

- Follow-up run `39413914090` at `6da7325` staged pthread successfully and compiled all
  XNU objects, then failed at final link: `sweet_amfi.o` referenced seven
  `sweet_entitlements_*` functions absent from `SweetEntitlements.cpp` because that
  implementation was SWEET-only. Expanded its build guard to FP6 in patch 0035;
  this preserves XML entitlement support and resolves the specific undefined symbols.
  New CI build pending.
- Run `39414717734` at `48b58a5948a7c23e46022406eb5134e0da7f314d` completed successfully:
  both the FP6 XNU build and `fp6-boot` packaging job passed. The run uploaded
  `fp6-fastboot-boot` (shim boot image, SHA256SUMS and manifest), plus `xnu-kernel`
  and `fp6-adt`. This confirms a kernel build and temporary-boot-image package only;
  no phone boot has been performed for this image.
- The user expanded the FP6 port goal to staged XNU support for CPU/SMP, timer/GIC,
  display console, UFS storage, graphics/software rendering and USB/DWC3 networking
  or serial. Work these subsystems one at a time; distinguish bootloader-provided
  framebuffer splash from an XNU display driver. Fairphone 6 is SM7635 (Snapdragon
  7s Gen 3), so the user's table's SM7450 label should not be used for this target.
- Correction after reviewing the earlier FP6 boot notes: the known on-device path used
  Android boot header v2 with the stock DTB embedded. CI run `39414717734` uploaded a
  5,626,548-byte compressed artifact, but that artifact expands to a 16,203,776-byte
  header v4 image without a DTB; it is not the previously tested packaging format.
  Repacked that run's successful kernel and matching ADT with `/tmp/fp6-stock.dtb`
  using `tools/fp6-package.py --dtb`, which selects header v2. The resulting image is
  22,896,640 bytes, SHA256 `3dcc03f79b4fb6b775ebbb1612509a772e54b78d45301e20bdd72ce95861e59e`;
  unpack validation confirmed the 192,512-byte shim kernel, 16,003,456-byte XNU
  payload and embedded DTB exactly match their inputs. This rebuilt v2 image has not
  been booted. The current CI packaging job still needs a reproducible way to obtain
  the stock DTB before it can publish this corrected format.
