# ios-extra — current state

Last updated 2026-10-20 after adding the FP6 ADT profile. Read [HANDOFF.md](HANDOFF.md) for how to
continue and [AGENTS.md](AGENTS.md) for the rules. The per-step history (images,
hashes, CI runs, raw numbers) is [docs/GPU_LOG.md](docs/GPU_LOG.md); the hardware and
mainline reference is [docs/GPU_GMU_BOOT.md](docs/GPU_GMU_BOOT.md); the per-patch
design is [docs/GPU_CX_EXPERIMENT.md](docs/GPU_CX_EXPERIMENT.md).

## FP6 shim packaging (2026-10-20)

- Inspected user-selected successful CI run `39371823683` at `4e7fdf0`.
  Artifact `12242266868` contains `kernel.development.sweet`, SHA256
  `18f69070e456841cc4d400f6d6438b7ede02eb2e6b0429d4b231da88e7d9eddc`,
  and no FP6 ADT artifact. A source commit mentioning FP6 did not select FP6
  for this push build. Do not package that kernel for FP6.
- Dispatched run `39372737713` explicitly with `machine_config=FP6`,
  DEVELOPMENT, from main after `b08556b`. Result and artifacts are pending.

- Local LLVM build now links the shim and packages an unsigned Android v4 image.
  The local packaging check used placeholder payload bytes only: shim and ramdisk
  unpack byte-for-byte. This is not a tested XNU boot image or a phone observation.
- `tools/fp6-package.py` consumes a kernel and ADT from the same CI run, builds
  the FP6 shim, verifies packaged components and writes hashes/provenance.
  The new `fp6-boot` CI job uploads `fp6-fastboot-boot` after an FP6 kernel build.
  Its first CI execution remains pending. Pushes still use the repository's
  MACHINE_CONFIG variable (default SWEET); select FP6 for a manual run.
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
