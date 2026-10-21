# ios-extra — current state

## FP6/SWEET launch diagnostics and USB logger (2026-10-21)

- Patch 0111 replaces the kernel logger's routed UDP socket sends with complete
  Ethernet/IPv4/UDP frames addressed to the fixed USB-ECM host. This bypasses
  XNU route and ARP resolution, which were in the previous send path. It waits
  for the ECM data alternate setting, reports a full transmit queue as
  `ENOBUFS`, and keeps the ring cursor unchanged on failure so the chunk is
  retried. A clean replay of patches 0099–0112 applied successfully; the
  resulting `sweet_usb.c` passed syntax compilation against the CI build tree.
  CI run `39537652816` passed for patches 0111–0112. Its full artifact is a
  pre-Sandbox-registration build; phone delivery remains unverified.
- Patch 0112 adds `sweet_noconsole=1` as an alias for
  `sweetfb_noconsole=1`. Both mute framebuffer console drawing after the first
  GUI swap; persistent logging and panic drawing are preserved.
- Patch 0113 fixes a real FP6 gap: `sweet_amfi.c` includes the permissive
  `Sandbox` MAC policy for FP6, but the prior `bsd_init.c` call-site guard was
  SWEET-only, so FP6 never registered that policy. Patch 0113 widens the call
  guard to FP6 before root mount/process startup. A clean replay of 0099–0113
  passed. This registers the policy but does not synthesize individual
  sandbox profiles or container metadata; the next CI build is pending.
- Updated `tools/sweet-root-tweaks.py` to change any launchd stdout/stderr
  override from `/dev/console` to `/dev/null`; the diagnostic-only
  `tools/patch-launchd-plist.py` uses `/dev/null` as well. The current local
  Tegu HFS image was inspected directly: `backboardd` has neither explicit
  path, and no launchd job points either stream to `/dev/console` (two WebKit
  jobs use `/dev/null`). Therefore the old confirmed spawn failure is not
  present in this root image; no rootfs rebuild is needed for that fix.
- Existing SWEET patches already capture a `backboardd` abort: 0043–0044 log
  crash registers/backtrace, 0051/0053 scan writable heap text for exception
  reasons, 0048 tees selected `/dev/null` output, and 0049/0054 trace IOKit
  lookups and opens. These hooks are SWEET-only; the README SWEET profile uses
  their defaults. For the FP6 image, patch 0111 supplies the USB kernel logger
  but the current SWEET-only crash/IOKit hooks are not enabled.
- ADT audit: the local D22AP IPSW tree supplies the 61 usable `/product`
  properties copied by `tools/mkadt.py`; no Apple-format SWEET ADT was found.
  The generated SWEET ADT currently describes all eight CPUs as homogeneous,
  while the SWEET Linux DT describes six efficiency and two performance cores.
  This is a topology metadata gap, not an identified cause of the present
  `backboardd` exception. Qualcomm peripheral nodes require matching XNU
  drivers and should not be copied wholesale from the iPhone tree.

## FP6 watchdog/framebuffer boot-argument package (2026-10-21)

- The earlier USB-log UFS boot image omitted `wdt=-1`,
  `wdt_test=no_user_checkin`, `sweetfb_noconsole=1`, and `sweetfb_hz=30`.
  Repacked the same CI kernel (run `39472658322`, commit
  `698cc43ed79a9f8e3c53af4b436872bd764dfa60`), D22AP-product ADT, and stock
  FP6 DTB. The new arguments also disable the SWEET touch/button drivers and
  retain USB debug. `cpus=8` is retained for FP6's eight-core topology.
- `wdt=-1` is an XNU boot argument; `wdt_test=no_user_checkin` is read by
  watchdogd from the boot arguments. They were already used by the SWEET
  profile; their effect on this FP6 boot is not yet device-verified. This does
  not establish that a physical SoC watchdog has been disabled.
- Image `shim/out/fp6-wdt-fb-39472658322/fp6-shim-ufs-root-wdt-fb.img`, SHA256
  `f2ca0c938d9dc86a9a4dcc01d28e48700e2fcaf71481cf55186d37902be04b5a`.
  Header-v2 package validation passed, including embedded kernel shim and
  stock DTB checks. It has not been booted; the current phone boot was left
  untouched. USB log delivery remains unverified; the host capture was empty.

## FP6 Tegu-style iOS 16 root image (2026-10-21)

- Rebuilt the iOS 20H392 root from the locally extracted OS, SystemOS, and
  AppOS images using a Tegu-style Linux guest copy (`rsync -aH --numeric-ids`).
  `/dev/kvm` is unavailable here, so QEMU used TCG; the OS copy took about 22
  minutes. The earlier host-built image with invalid HFS index/thread records
  remains rejected and must not be flashed.
- Applied `tools/sweet-root-tweaks.py` through Tegu's isolated guest. Readback
  confirmed the Setup skip, launchd crash-policy rename and CommCenter removal,
  migration marker, audio/recorder disables, SpringBoard settings, containers,
  and ownership/mode requirements. The image has no mobileactivationd system
  container yet, so the tweak script warned that it skipped the data ark; FP6
  activation still depends on the ADT `/chosen` security-status properties.
- Tegu's read-only verifier passed for launchd, dyld, SystemVersion, all 44
  shared-cache aliases (matching inode numbers to the cryptex copies), the two
  trampoline libraries, cryptex symlinks, log directories/owners, and the
  system keybag. Linux `fsck.hfsplus -fy` repaired the volume; subsequent
  `-fn` reports only the documented journaled-volume-header minor-repair
  warning (status 8), with catalog, multi-linked-file, hierarchy, extents,
  attributes, and bitmap checks clean. Tegu's temporary local check accepts
  only this specific header-only warning.
- Linux HFS+ still does not set Apple's hard-link chain bit on these links;
  XNU can log/repair that bit at lookup, and patch 0041 only limits repeated
  diagnostics. The Tegu check proves the cache paths share inodes, not that the
  HFS catalog contains Apple's chain-bit metadata. This is the known Linux HFS+
  limitation and was also present in the earlier successful Tegu path.
- Raw image: `research/fp6-rootfs-tegu-20261021/fp6-ios-root-tegu.hfs`, SHA256
  `574cbad62a794a5e8f69cb118a37c0cf915ffe4e66ab1a5a296175c1a216296d`.
  Fastboot sparse image: `research/fp6-rootfs-tegu-20261021/fp6-ios-root-tegu.simg`,
  SHA256 `a1c6f7da616520841c4d56ac2a147940c5c93a0b4406cb1c9ae6832d64338f7c`;
  sparse header is v1, 4 KiB blocks, 4,194,304 blocks. Neither image has been
  flashed or booted on the phone.

## FP6 `mount[3]` boot-task panic (2026-10-20)

- The latest phone photo shows `mount[3] exited -- no exit reason available --
  (signal 0, exit status 1)`. The backtrace resolves in the exact CI kernel
  (`39468219112`, text base `0xfffffe0007004000`) through
  `proc_prepareexit`/`proc_handle_critical_exit`; this is launchd panicking
  because the required `mount -P 1` task returned failure, not a SweetFB or
  SweetSurface fault. Those services registering confirms matching only.
- The known SWEET `mount -P 1` failure was fixed by supplying a writable HFS
  root; the FP6 launchd-fix package omitted `ufsrw=1 rootrw=1`. The exact
  mount subcommand failure is not in this photo, so read/write root is the
  leading source-based diagnosis, not confirmed phone evidence. The packaged
  IPSW-product ADT does contain `/chosen/boot-manifest-hash`, so the earlier
  missing-hash failure is not explained by that ADT omission.
- Repacked the same CI kernel, D22AP-product ADT, and stock DTB, changing only
  boot arguments to add `ufsrw=1 rootrw=1 fp6usb=2 launchd_unsecure_cache=1`
  while retaining `unentitled_ios_sim_launch=1`. Header-v2 package:
  `/tmp/fp6-mount-fix-39468219112/fp6-shim-d22ap-product-ufs-rw-mount-fix.img`,
  SHA256 `af8e26a51deded4c1d14e5996fa73735be85553fea69a7ff8e0e8c4cf2a1f528`.
  Package construction passed; it has not been booted. `ufsrw=1 rootrw=1`
  permits writes to the existing userdata HFS volume.

## FP6 CPU cluster topology (2026-10-20)

- Source review confirms the Volcano DTS uses MPIDRs `0x000` through `0x700`,
  with efficiency CPUs 0–3 and performance CPUs 4–7 arranged as 4/3/1 clusters.
  The generated ADT preserved those MPIDRs and cluster IDs, but set every
  `cluster-type` to integer 0.
- XNU's parser in patch 0099 recognizes ASCII `E`/`P` values for those types.
  Updated `tools/mkadt.py` to emit `E` for CPUs 0–3 and `P` for CPUs 4–7. This
  corrects the topology metadata. Patch 0108 now defines `__ARM_AMP__` in the
  FP6 header so XNU builds its AMP/Edge scheduler and forms E/P scheduling sets.
  With `HAS_CLUSTER` unset, the 4/3/1 physical layout is represented to the
  scheduler as one E set (CPUs 0–3) and one P set (CPUs 4–7).
- The ADT was generated locally; CI build and phone validation are pending.
  User previously reported eight CPUs up, but did not provide the startup log
  that would verify each per-core PSCI and IPI message. Scheduling on P cores
  and a measured performance improvement remain unverified.

## FP6 boot log repetition (2026-10-20)

- The user's latest FP6 observation is only AKS calls from `backboardd`; there
  is no confirmation yet for other AKS clients, SpringBoard, or UI startup.
  The separate MediaTek-device screenshot is not FP6 evidence. AKS is the
  AppleKeyStore interface; this tree already provides a built-in no-passcode
  compatibility implementation without SEP-backed protection. `backboardd`
  reaching it indicates the request path is present, but does not identify
  whether the returned state is sufficient for display startup.
- Repeated HFS hardlink messages and daemon-spawn output were seen earlier.
  HFS patch 0041's limiter only caps diagnostic output and does not repair
  catalog metadata. The user asked to defer that cap for now, so the FP6 guard
  is removed from patch 0041 for the next build; SWEET's existing cap remains.

## FP6 SWEET userspace-enablement patch audit (2026-10-20)

- Correction from the 2026-10-21 clean replay: patch 0099 makes
  `sweet_amfi.c` (including the permissive `Sandbox` MAC policy) compile for
  FP6, but the replayed `bsd_init.c` registration call remains guarded by
  `ARM64_BOARD_CONFIG_SWEET` only. Patch 0035's current copy contains the FP6
  guard, but that change is absent from the source state after replaying the
  existing patch baseline. Patch 0113 widens the call-site guard to FP6, so
  `sweet_amfi_policy_register()` actually runs on that board. This registers
  the permissive stand-in; it does not supply the individual sandbox profile
  files or container metadata that some services may request.
- The FP6 `MASTER.arm64.fp6` config introduced by patch 0099 already omits
  `config_ext_resolver`, matching the effective SWEET configuration from
  patch 0057. Patch 0108 enables the AMP scheduler. Its CI build passed; phone
  testing is pending. The FP6 HFS diagnostic limiter was deferred for that
  scheduler build, then re-enabled in the follow-up HFS patch comparison below.
- Patch 0108 enables the AMP scheduler. Its CI build passed; phone testing is
  pending. The FP6 HFS diagnostic limiter was deferred for that scheduler
  build, then re-enabled in the follow-up HFS patch comparison below.

## D22AP product metadata recovery and FP6 boot package (2026-10-20)

- Located the iPhone X iOS 16.7.16 IPSW locally and extracted its D22AP device
  tree to the ignored `research/ipsw-x/` directory. The FP6 ADT generator copied
  all 61 non-placeholder `/product` properties; a parsed comparison confirmed
  they match the IPSW tree exactly and syscfg placeholders are excluded.
- Packaged `/tmp/fp6-ipsw-product-boot/fp6-shim-d22ap-product-ufs-root.img`
  with the existing AMP kernel from CI run 39461451126 (source commit
  `590b4bc05bfa574f4bfdb3fa4f101308c5ce5548`), stock FP6 DTB and the prior
  UFS-root command line. Header v2 packaging and embedded kernel/DTB/payload
  checks passed. Image SHA-256:
  `2cb4f1b8cbe2bd46a6771c648897931d0efc0e8b462a4dcb644c94e3878c0579`.
- No fastboot device was connected when checked, so this image has not been
  booted. The GitHub workflow still lacks the local D22AP ADT input; its normal
  generated ADT omits `/product` until that input is provisioned there.
- The current FP6 userdata root image is not available locally. The IPSW is
  present, but this work only extracted its device tree; it did not inspect the
  phone's userdata or validate its current HFS volume.

## FP6 HFS patch comparison and root image status (2026-10-20)

- Shallow-cloned SWEET at `11da58b` for read-only comparison. FP6 already has
  the relevant HFS support: staged Apple OSS HFS (0026), unsealed-root handling
  (0029), read/write root support (0031), rename-swap (0052), and UFS performance
  work (0069). FP6's 0106 enables `SWEET_HFS` in its own master config; SWEET's
  generic `config/MASTER` change is therefore not needed.
- SWEET's 0041 patch already limits repeated hardlink-catalog diagnostics to
  eight messages. Re-enabled that behavior for FP6 as well, per the user's new
  request to bring in SWEET's HFS patches. It suppresses repeated log output;
  it does not repair catalog records or filesystem corruption.
- No FP6 root image or extracted OS/SystemOS/AppOS images are present in the
  available local paths, so the current userdata HFS volume could not be
  inspected here. Earlier notes record a pre-boot `fsck.hfsplus -fy` as OK;
  that is not a check of the volume after the phone mounted it read-write.
- The user's Nord 2 report is separate: Apple userland and eight CPUs were
  already running there before the MediaTek framebuffer handoff was added. It
  does not establish the integrity of FP6's root volume.

## FP6 IOSurface and framebuffer enablement (2026-10-20)

- Patch 0109 enables the existing `SweetSurface` and `SweetFramebuffer`
  implementations for the FP6 build and adds the FP6 IOKit personalities for
  `IOCoreSurfaceRoot` and `AppleCLCD`. The FP6 ADT already publishes
  `/arm-io/disp0` as `sweet,display`; the shim supplies `PE_current_console`
  video fields from the bootloader FDT's `0xe3940000` framebuffer node.
- Replayed syntax compilation for `SweetSurface.cpp`, `SweetFramebuffer.cpp`,
  and `KernelConfigTables.cpp` against the prior CI build tree with clang 23;
  all three passed. The repository helper's pinned Swift clang path is absent
  on this host, so the replay used the installed clang. Full CI build and phone
  presentation test are pending.
- The image packaged before patch 0109 does not contain this driver enablement.
  The new code only copies CPU-rendered IOSurface frames to the framebuffer ABL
  left active; no FP6 DSI/panel initialization is added here.
- CI initially rejected 0109 because its context-free hunks used stale line
  numbers after patches 0101 and 0107. Added surrounding context in commit
  `3a500436979d8c3debbe07ed8d58f5ccfc5f55de`; patch application and the full
  XNU build then passed in Actions run `39468219112` (5m42s).
- Packaged that run's kernel with the verified stock FP6 DTB and an FP6 ADT
  carrying all 61 non-placeholder `/product` properties from the local D22AP
  IPSW ADT. Image:
  `/tmp/fp6-display-build-39468219112/fp6-shim-d22ap-product-ufs-root.img`,
  SHA-256 `84aad4e03bc396e684dcd45219200a744745dd1681219a80c71d2276c7c4865a`.
  Header-v2 unpack/metadata checks passed. CI's automatic phone-image packaging
  skipped because `FP6_STOCK_DTB_URL` is unset; this local package uses the
  verified DTB. It has not been booted on the phone.

## FP6 watchdogd service discovery (2026-10-20)

- The FP6 DT/ADT does not expose a verified APSS/MSM watchdog resource, so do
  not map or write Qualcomm watchdog MMIO. The user's ADSP/WPSS `wdog` IRQs
  belong to those remote processors and are unrelated to the AP watchdog.
- Added patch `0107-fp6-dummy-iowatchdog.patch`: it compiles the existing
  watchdogd-facing `IOWatchdog` user-client for FP6 and registers its IOKit
  personality in the FP6 kernel table. It preserves the known dummy behavior,
  including the `IOPMUPrimary` marker, but explicitly logs that hardware
  watchdog control is disabled. This is an interim service-discovery fix, not
  a hardware watchdog driver.
- First CI attempt `39455499092` exposed context failures in patch 0107 before
  compilation; the new patch had guessed source line positions from earlier
  hunks. Reworked the hunks to include surrounding exact context. The corrected
  commit `9c3c2f7b49c908840fc46108c6db12628e27e779` passed CI run
  `39456160901` (XNU build and FP6 packaging job). CI skipped image upload
  because `FP6_STOCK_DTB_URL` is unset. The matching kernel and ADT were
  downloaded locally and their SHA256 values verified; the known matching
  stock DTB was reused (`16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`).
- Locally packaged and header-v2 validated a UFS-root image preserving the
  prior iOS userspace boot arguments:
  `/tmp/fp6-watchdog-39456160901/ufs-root/fp6-shim-ufs-root-watchdog.img`,
  SHA256 `e31d60c0b1323f70829a3aab41ad31ad16a2dc3d8bf230a8833ecfcda61e2680`.
  It embeds kernel SHA256
  `e2c08fa79086456dfc5d24bf4c519895a1246237f7f0e50a92812fe26db40fbc` and ADT
  SHA256 `9f6030208a39700f508f34fd01c6ec5f95376fa1efb25dbdeeeb202e9322496d`.
  The command line retains `rd=ufsroot0 ufsrw=1 fp6usb=2
  unentitled_ios_sim_launch=1 launchd_unsecure_cache=1`. Header-v2 checksum,
  unpacked payload and embedded DTB checks pass. This is package validation;
  the new dummy watchdog personality has not yet been observed on the phone.

## FP6 unsealed HFS root authentication (2026-10-20)

- The user reports that the HFS root mounted, then XNU panicked with
  `rootvp not authenticated after mounting` at `bsd_init.c:947`. This advances
  past the prior journal-write failure; it is the sealed-root authentication
  check, not evidence of an HFS mount failure.
- The existing patch 0029 already permits an unauthenticated HFS root on the
  unsigned SWEET development boot. Extended that original patch's guard to
  include FP6, where the unsigned shim boot also has no Image4 trust chain and
  the development HFS root is unsealed. It now reports the auth error and
  continues through this check. This does not authenticate the volume or prove
  later userspace startup.
- A follow-on patch 0107 failed in CI because it targeted `bsd_init.c` after
  prior patch edits shifted the context. Removed it and folded the same one-line
  board guard into patch 0029, which introduces this block early in the series.
  Commit `11e3311dec6aebdcdf40f167c05316fc29601169` passed CI run
  `39444642284` (both XNU build and FP6 boot job). The workflow's generic boot
  image was skipped because `FP6_STOCK_DTB_URL` is unset.
- The intended next test image should retain `rd=ufsroot0 ufsrw=1` to allow the
  journal/root writes required by this image, and USB diagnostics. No device
  action has been run from this workspace. Locally packaged and header-v2
  validated the matching CI kernel and ADT with the verified local stock DTB:
  `/tmp/fp6-unsealed-394446/ufs-root/fp6-shim-ufs-root-rw.img`, 23,396,352
  bytes, SHA256 `e0143993d89b656cdb7094bc323d57ce32941c59c7e8b5f3bab6f2f8e0596bee`.
  Kernel SHA256 `e9568a5aa790b88c2a773483e4717d7c1ba307d91ba79f7a32c62b08e7c80750`,
  ADT SHA256 `5f273d7248d288e77f0cde2cfd118acd39f5008502e8f8b4d0db52dfee3a4a84`,
  stock DTB SHA256 `16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`.
  Command line is `debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress rd=ufsroot0
  ufsrw=1 fp6usb=2`. This opts in to writes to userdata for the HFS journal;
  The user boot-tested it and confirmed root authentication was passed far
  enough to reach launchd; launchd then failed with the wrong-platform reason
  below.

## FP6 launchd platform rejection (2026-10-20)

- On the first `fp6-shim-ufs-root-rw.img` test, the user reports that root mount
  progressed to launchd, then panicked:
  `unexpected SIGKILL of launchd (CS_KILLED) with reason namespace 9 code 0xe`.
  XNU `bsd/sys/reason.h` maps namespace 9 to `OS_REASON_EXEC`; code 14 (`0xe`)
  is `EXEC_EXIT_REASON_WRONG_PLATFORM`. This is the macOS-targeted kernel
  rejecting the iOS platform binary, not a code-signature validation failure.
- Reused the DEVELOPMENT boot argument
  `unentitled_ios_sim_launch=1` from the existing SWEET iOS userspace bring-up
  and locally repackaged the same CI kernel/ADT/stock DTB. New image:
  `/tmp/fp6-unentitled-394446/ufs-root/fp6-shim-ufs-root-rw-unentitled.img`,
  SHA256 `ae4b86c91208e56a28d9230a80b6262f6a824431b41ff25d74e2daafe0628b82`.
  It retains `rd=ufsroot0 ufsrw=1 fp6usb=2`; header-v2 packaging completed.
  This development bypass has not yet been tested on the phone.

## FP6 boot-task platform classification (2026-10-20)

- The user booted the unentitled image and reports a new panic:
  `boot task is not a platform binary /sbin/fsck`. The iOS platform rejection
  was bypassed and launchd advanced to its boot-task sequence.
- Source inspection found patch 0035 registers the built-in AMFI MAC policy
  from `bsd_init.c` only under `ARM64_BOARD_CONFIG_SWEET`. Patch 0099 compiles
  the AMFI implementation for FP6, but does not register its MAC policy there.
  As a result, its `vnode_check_signature` hook never marks root-filesystem
  binaries `CS_PLATFORM_BINARY`; the boot-task check rejects `/sbin/fsck`.
- Extended patch 0035's policy-registration guard to include FP6. This is the
  targeted source fix. Commit `8c423bf0bd8917e0a49787eac2b40bfb5385625f`
  passed CI run `39447341232` (XNU build and FP6 boot job).
- `launchd_unsecure_cache=1` is also included, as in the known-good SWEET
  userspace boot args; it lets launchd use its job cache without AMFI's
  trust-cache service. Packaged and header-v2 validated the matching kernel and
  ADT plus verified stock DTB as
  `/tmp/fp6-platform-394473/ufs-root/fp6-shim-ufs-root-amfi.img`, SHA256
  `34ac69fbdef9e3d32d4d0dbb6dc0b28ba4264590a1b71dca026a4aa347509c0a`.
  Kernel SHA256 `38c525fe8753ee2a456ad684bd38264d70e582846a12e17bc04d30d500bc3cb4`,
  ADT SHA256 `f228d71be97a8f6525819282745dd92d1ef7fecbd26a86aaaa6c4d8f8f46b35b`.
  Command line retains UFS writes and USB diagnostics and adds both
  `unentitled_ios_sim_launch=1 launchd_unsecure_cache=1`. Phone validation is
  pending.

## FP6 MKB/keybag initialization (2026-10-20)

- After the AMFI/platform image, the user reports `hfs: set hardlink bit` lines,
  then a fatal keybag error during `MKB_INIT`, followed by
  `Halt/Restart Timed Out @IOPlatformExpert.cpp`. HFS's link-chain repair is
  informational here; the fatal MKB init is the active blocker. The restart
  timeout is secondary: this FP6 bring-up does not yet provide a working
  platform restart implementation.
- Source audit found the existing built-in `AppleKeyStore`/libaks test service
  is compiled and registered only for SWEET. FP6 therefore has no service to
  satisfy keybagd's `aks_get_system` path. The ADT builder already sets
  `/defaults/no-effaceable-storage`, and `mkiosroot.sh` adds the plain system
  keybag plist; those are the established SWEET keybag prerequisites.
- Extending the built-in no-passcode AppleKeyStore service and IOKit match entry
  to FP6. This is a development stub, not SEP-backed keybag security. CI and
  phone validation are pending.
- First CI run `39449649400` failed before compilation because the modified
  patch 0099 hunk count was short by one line (`corrupt patch at line 696`).
  Corrected its hunk header; retry pending.

Last updated 2026-10-20 after adding the FP6 ADT profile. Read [HANDOFF.md](HANDOFF.md) for how to
continue and [AGENTS.md](AGENTS.md) for the rules. The per-step history (images,
hashes, CI runs, raw numbers) is [docs/GPU_LOG.md](docs/GPU_LOG.md); the hardware and
mainline reference is [docs/GPU_GMU_BOOT.md](docs/GPU_GMU_BOOT.md); the per-patch
design is [docs/GPU_CX_EXPERIMENT.md](docs/GPU_CX_EXPERIMENT.md).

## FP6 panic from probe image (2026-10-20)

- User tested image `fp6-shim-touch-ufs-probe.img` from CI run 39423526775, SHA256
  `f5abf0c8697aebef950f1d1fa6d997d6eae1d3a770caacd3b3377b0d26928198`. The phone
  displayed a kernel data abort. Photo state: PC `0xfffffe0007948c14`, LR
  `0xfffffe000793efc4`, ESR `0x96000005` (translation fault, level 1), FAR zero.
- Symbolication against that run's exact `kernel.development.fp6` resolves PC to
  `IOUserResources::resources()` and LR to `IODTMapInterruptsSharing`. This occurs
  during IOKit device-tree interrupt mapping, before the optional UFS/GPIO/touch
  probes in `IOKitBSDInit` run; those probes are not implicated by this trace.
- Source inspection found FP6's generated GIC node had an `AAPL,phandle` and was
  referenced by SPI0/TLMM interrupt-parent properties, but omitted `#interrupt-cells`.
  XNU only indexes interrupt-controller phandles that provide that property, so
  interrupt-parent resolution can return null and fault at address zero. Added
  `#interrupt-cells = 3` to the FP6 GIC profile. The corrected ADT serializes and
  dumps that property; a rebuilt image and phone retest are still pending. This is
  a source-based diagnosis until the corrected build reaches the same boot stage.

## FP6 root panic and USB debug path (2026-10-20)

- A second phone photo's backtrace was symbolicated against the exact kernel
  from CI run 39423526775. `IOFindBSDRoot` reaches its explicit panic branch:
  `QCOM UFS root %s unavailable: %d`; the visible panic-stack `Assert` frame is
  secondary. This identifies the failure as UFS root selection. The photo is
  cropped before the formatted error number, so the specific UFS init/GPT error
  remains unknown. This differs from the earlier GIC interrupt-cell panic.
- Source inspection found the SWEET DWC3 ECM gadget and UDP log sender already
  exist, but their controller power/clock probe uses SWEET-only GCC offsets.
  Patch 0101 adds an opt-in FP6 entry (`fp6usb=1` for DWC3 handoff diagnostics,
  `fp6usb=2` to start the ECM gadget and UDP console log at
  `192.168.7.1:5140`). The FP6 path does not read or write SWEET GCC offsets or
  change SMMU registers. USB DMA/IOMMU operation is not yet measured.
- Patch 0101 also hooks the existing 4 MiB in-memory console ring for FP6 from
  the first serial-console output, before UFS root setup can panic. This gives
  the USB log sender access to root-selection diagnostics. A separate USB
  debug boot image uses `fp6usb=2`; the ordinary RAM-disk image keeps USB
  disabled. Both use `debug=0xc keepsyms=1` for runtime diagnostics.
- CI run 39427603634 confirmed the patch series applied and the FP6 ADT
  generated, but the compile failed in seven existing `DEBUG`-profile units
  (DTrace `MUTEX_HELD`, ARM `bad_page_cnt`, scheduler `max_unsafe_rt_quanta`,
  and VM `uple_create_btref`). No errors were reported from the USB changes.
  The workflow default is restored to `DEVELOPMENT`, which has built previously;
  the diagnostic boot flags and USB debug image remain enabled.
- CI run 39428369953 passed for commit `207b1d8f3ee632c3cc3c3404007230752473ca0d`.
  It built `kernel.development.fp6` (SHA256
  `ea460a064820ac507e202e82ab26c1ba87d3174d2cd3b948a0662dbc82e1336e`) and the
  corrected FP6 ADT (SHA256
  `cc7891f4b863eaea02343c5624e4f9249010e6010641f03149ad23d9775be3fa`). The
  kernel compiled with `DEVELOPMENT`; runtime debug args are enabled. CI's boot
  packaging step skipped because `FP6_STOCK_DTB_URL` is unset.
- Packaged `/tmp/fp6-usb-394283/usb-debug/fp6-shim-usb-debug.img` locally using
  that run's kernel and ADT plus the existing stock DTB (SHA256
  `16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`). The
  header-v2 unpack check verified payload, shim and embedded DTB. Image SHA256
  is `81de2706d9094cc9f539a45fcaae60ffae2e346702d748c408319db18d3d7eb5`; boot
  args are `debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress rd=md0 fp6usb=2`.
  `hardware_tested` is false: USB enumeration, DMA and log delivery have not
  been observed on the phone. The host can listen with
  `tools/sweet-usbnet.sh /tmp/fp6-usb-394283/usb-debug/fp6-usb.log`.

- The user subsequently confirmed that the SWEET USB gadget appeared on the
  host. Packaged a second image from the same CI kernel/ADT and local stock DTB
  with `rd=ufsroot0 fp6usb=2`, so the existing UDP log sender starts before
  UFS root selection. Header-v2 validation confirmed the image payload, shim
  and embedded DTB. Image:
  `/tmp/fp6-ufs-usb-debug/fp6-shim-ufs-usb-debug.img`, 22,900,736 bytes,
  SHA256 `f0a8cadcd3e717fc819605db518dbfcd0e8e77dcbb356ec5719ebf8565366e05`.
  It has not been booted. The UFS initializer defaults to read-only without
  `ufsrw`; it does not flash or modify userdata. No UFS panic log has been
  captured yet, so the numeric initializer error and failing stage remain
  unknown. `fastboot devices` returned no device at packaging time.
- The user ran the host logger with the UFS-root image: the USB Ethernet
  interface appeared, but no UDP log arrived. Likely limitation: the UFS-root
  panic occurs before the background log thread gets a chance to transmit; this
  is not proof of the underlying UFS fault. Packaged a read-only UFS probe
  image that continues into the known RAM-disk init, allowing the UDP logger to
  stay alive after the same UFS initialization path. Image:
  `/tmp/fp6-ufs-probe-usb-debug/fp6-shim-ufs-probe-usb-debug.img`,
  22,917,120 bytes, SHA256
  `1a6831822a695c88e3537b48a71ec7c3a176bdd150d3ffc587153743e2764e8f`.
  Header-v2 payload/shim/DTB validation passed. It has not been booted; this is
  a diagnostic image, not a UFS-root fix.
- The user clarified that the probe logs are not files on `md0`; correct. The
  intended destination is the host-side UDP capture, which remained empty.
  The latest panic photo confirms `EIO` (errno 5), but does not distinguish
  request-list takeover from a failed SCSI completion. Patch 0102 records the
  failing UFS stage and command/status detail and adds them to the panic text,
  so the next UFS-root attempt can identify the underlying failure without a
  working UDP stream. This is diagnostic instrumentation, not yet an UFS fix;
  it still needs a CI build and phone boot.
- Patch 0102 CI run `39431367035` succeeded on commit
  `cd38bdead498c0dd7e687aa169490ad723f781a5`. Kernel SHA256:
  `cc1462c718fa2c8280c8426b0cca4eb87cac2a35a01a74437ac5558b003df334`;
  matching FP6 ADT SHA256: `2a9500cfffd003771621b6ea0afbea573f3e43eabff748f2777c2032b49b76ff`.
  CI boot packaging skipped because `FP6_STOCK_DTB_URL` is unset. Locally
  packaged and header-v2 validated a temporary UFS-root image using those
  artifacts and local stock DTB:
  `/tmp/fp6-ufs-stage-394313/fp6-shim-ufs-stage-debug.img`, 22,900,736 bytes,
  SHA256 `3b9100a82b7576f8f9ebf6d4c7ea66593e9ce0cf3e88f3fcfed383d5e37825c5`.
  Command line includes `rd=ufsroot0 fp6usb=2`. The user booted it and reported
  `SCSI completion detail 0x2102` and panicked task pointer
  `0xfffffe1b4109ec10`.
- The reported `0x2102` detail decodes to response UPIU `0x21` and SCSI status
  `0x02` (CHECK CONDITION); OCS is zero and the command was TEST UNIT READY.
  Because the reported stage is still `SCSI completion` on the 0103 image, its
  earlier guard also saw nonzero response byte `resp[6]`, which the packed
  detail omits. The UFS transport completed, but the response byte and sense
  values remain unknown. The panicked-task pointer is not a fault diagnosis.
  Linux's UFS definitions confirm that sense data is embedded in the response
  UPIU, so a separate REQUEST SENSE command is unnecessary.
- Patch 0103 decodes the embedded sense key/ASC/ASCQ and reports them in the
  panic detail. It retries TEST UNIT READY for up to 3 seconds only for UNIT
  ATTENTION or NOT READY / becoming ready; other SCSI errors remain failures.
  CI run `39433706325` built successfully on commit
  `be6b8d176a83426b12697bc0c0a27d8fc4374744`. Packaged and header-v2 unpack
  validated `/tmp/fp6-sense-394337/ufs-root/fp6-shim-ufs-sense-debug.img`,
  SHA256 `1a55b0261c102fff887dfb9fd33c97d0c4705a9d59b56e054c0bf7d5fab6cf55`.
  It uses `rd=ufsroot0 fp6usb=2`, is read-only with respect to UFS by default,
  and was subsequently booted; it reproduced the SCSI completion panic below.
- The user then booted the 0103 image and still saw
  `ufsroot0 unavailable 5 at SCSI completion detail 0x2102`. The 0103 kernel
  binary contains the new check-condition path, so the reported stage means its
  earlier completion guard rejected a nonzero response byte (`resp[6]`) before
  sense decoding. The packed detail retains UPIU `0x21` and status `0x02` but
  omits that response byte. Linux's completion path consumes SCSI status from a
  response UPIU and copies the embedded sense for CHECK CONDITION; patch 0104
  now follows that flow and reports both response and sense. Exact values still
  await phone retest.
- Research against the local stock FP6 DTB found its UFS host node at
  `0x1d84000`, using two lanes, the Qualcomm UFS PHY, ICE, MCQ, and an SMMU
  stream (`iommus` stream ID `0x60`) with `qcom,iommu-dma = "fastmap"`. It also
  sets `qcom,broken-ahit-wa`. Linux's QCOM driver disables the auto-hibernation
  idle timer while commands are active on that quirk path; the current XNU
  handoff driver does not. This is a platform-confirmed candidate to address,
  though it does not by itself explain the TUR CHECK CONDITION. The existing
  TUR has no PRDT, so its completion has not validated data-buffer DMA through
  the SMMU; actual GPT/data reads remain untested.
- The QCOM Linux host also owns PHY initialization, regulators/clocks, link
  startup, device-init queries, and recovery. XNU currently assumes ABL leaves
  those initialized and takes over only the UTRL. Since TUR returns a UFS
  response with OCS zero, the live link and a response DMA work at least once;
  this does not validate post-handoff power-state handling or data DMA. No
  Apple-specific iPhone UFS host source was found in Apple's public XNU tree.
- Patch 0104 CI run `39435664153` succeeded on commit
  `0ff825a8f143aff1926e8071342ccba708057ad3`. Locally packaged and header-v2
  validated `/tmp/fp6-ufs-audit-394356/ufs-root/fp6-shim-ufs-response-debug.img`,
  SHA256 `6a61741e1c8a1853a6362f5ac7b2258ab65e91be869d4441612b42045e7e154b`.
  It uses `rd=ufsroot0 fp6usb=2`; it has not yet been booted. CI's own boot
  packaging was skipped because `FP6_STOCK_DTB_URL` is unset.
- Patch 0105 implements the FP6 UFS/SoC handoff basics using NativeUfs and the
  cloned SM7635 Linux sources: disable/restore the DT-confirmed broken AHIT
  timer around each completed transfer; read `bCurrentPowerMode`, wake a
  non-active device with START STOP UNIT on WLUN `0xD0`, then retry TUR for a
  bounded 3 seconds; decode fixed and descriptor sense; inspect FP6 SMMU stream
  `0x60` and preserve its live mapping, or configure only that stream through a
  checked Linux Qualcomm pass-through context when no mapping exists. The FP6
  ADT now carries the stock SMMU range `0x15000000..0x150fffff` and stream ID.
  Patch application and ADT generation were checked locally. The local XNU
  compile could not run because this Linux workspace lacks the Xcode kernel SDK
  clang expects; CI build and phone validation are pending. No device was
  touched, and this patch has not yet been committed.

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
- SMP source review: LineageOS `qcom/volcano.dtsi` has eight CPU nodes with MPIDRs
  `0x000` through `0x700` and a 4+3+1 cpu-map. The generated FP6 ADT matches those
  IDs. Existing PSCI CPU_ON, secondary reset entry, redistributor lookup and SGI
  startup path are present in patch 0099; enabled its ceiling for all eight CPUs
  and changed the generated FP6 image command line to `cpus=8`. This is source
  inspection only until the next CI result and a phone boot; each secondary must
  report initialized/SGI-ready before XNU publishes all CPUs initialized.
- Separate boot observations reported by the user: XNU waits for
  `IOProviderClass IOMedia AppleHFS`, and the boot picker failed to write its
  reason to NVRAM. Neither observation verifies secondary CPU startup. Root media
  publication and NVRAM persistence remain separate issues. The wait is emitted
  by `IOFindBSDRoot`'s fallback HFS-media matcher when no `rd=` root was selected.
  For the next FP6 image, package a minimal Mach-O init as the existing virtual
  `RAMDisk`/`rd=md0` root. This deliberately bypasses UFS; it does not implement or
  validate the FP6 UFS host driver. The CI packager now builds and includes that
  init. The known header-v2 packaging path still requires the local stock DTB.
- Correction after reviewing the earlier FP6 boot notes: the known on-device path used
  Android boot header v2 with the stock DTB embedded. CI run `39414717734` uploaded a
  5,626,548-byte compressed artifact, but that artifact expands to a 16,203,776-byte
  header v4 image without a DTB; it is not the previously tested packaging format.
  Repacked that run's successful kernel and matching ADT with `/tmp/fp6-stock.dtb`
  using `tools/fp6-package.py --dtb`, which selects header v2. The resulting image is
  22,896,640 bytes, SHA256 `3dcc03f79b4fb6b775ebbb1612509a772e54b78d45301e20bdd72ce95861e59e`;
  unpack validation confirmed the 192,512-byte shim kernel, 16,003,456-byte XNU
  payload and embedded DTB exactly match their inputs. This rebuilt v2 image has not
  been booted. CI run `39417320648` repeated the same v4/no-DTB mistake. The user
  tested its image and ABL rejected it with `Failed to load/authenticate boot image:
  Invalid Parameter`. Confirmed the header version at offset 40 is 4 and there is no
  embedded DTB. Repacked this run's eight-CPU kernel and matching ADT with the local
  stock DTB and RAM-disk init: `/tmp/fp6-repack/fp6-shim-boot.img`, 22,913,024 bytes,
  SHA256 `4a528a4cec90f772685fd740484636b2fc8c61b23d0d840e825872e4c8a896e0`.
  Package validation confirms header v2 and exact kernel, payload, and DTB bytes.
  `tools/fp6-package.py` now requires a DTB and rejects header v4. CI publishes a
  fastboot image only when repository variable `FP6_STOCK_DTB_URL` is configured;
  without it, the workflow warns and skips the image artifact. The corrected local
  image was then booted on the phone; the user reports that all 8 CPUs came up.
  The exact image SHA and boot log have not yet been provided, so this observation
  is not attributed to a particular package.

## FP6 iOS userspace image and Qualcomm subsystem audit (2026-10-20)

- Built a local iOS 16.7.16 (`20H392`) HFS+ root image from the user-provided
  iPhone X IPSW. The raw image is 16 GiB; `img2simg` produced a 12 GiB Android
  sparse image. The final `fsck.hfsplus -fy` reported the volume appeared OK;
  `file` recognized the output as Android sparse v1. This is host-side image
  construction only. It has not been flashed or mounted by FP6 XNU.
- Do not flash this image to `userdata` yet. That operation overwrites the
  phone's existing userdata, while the current FP6 image boots a tiny `rd=md0`
  RAM-disk init and has no FP6 UFS block driver/root-media path. The iOS HFS+
  image therefore cannot yet be used by the running kernel. Raw and sparse
  images remain under Downloads and are not tracked.
- User clarified that the current debugging goal is USB debugging. Source review
  confirms FP6's Qualcomm DWC3 wrapper at `0xa600000`, generic DWC3 core at
  `0xa600000`, eUSB2 PHY at `0x088e3000`, EUD registers at `0x088e2000` and
  `0x0c278000`, and QMP USB/DP combo PHY at `0x088e8000`. It uses OTG/role
  switching, extcon/EUD and PDC interrupts. Existing CDC-ECM/live-log patches
  0072–0077 are SWEET/SM7150-specific and cannot simply be enabled for FP6.
  See [FP6 Qualcomm subsystem audit](docs/FP6_QUALCOMM_SUBSYSTEMS.md).
- Source review also finds the next practical subsystem priorities: FP6 UFS
  block/root support for iOS userspace, USB CDC-ECM for debug logs, then the
  board-specific power/regulator path and touch input. The bootloader framebuffer
  is separate from a live panel driver; Adreno 618/740 code is not a drop-in for
  FP6's Adreno 710. Wi-Fi, Bluetooth, audio, camera and cellular depend on more
  firmware/DSP and transport work.
- No FP6 USB code was changed or tested in this audit, and no new CI run or phone
  boot was started. The next USB code change should first gather a read-only
  FP6 DWC3/clock/PHY state report, then test endpoint-zero enumeration before
  adding CDC-ECM. The new root image must not be presented as a phone-tested
  result.


## FP6 Qualcomm UFS and GPIO ADT (2026-10-20)

- Started `0100-fp6-qcom-ufs-root.patch`: enables the existing UFSHCI driver
  for FP6, labels its output QCOM UFS, keeps Sweet-only log/GPU/USB/touch/key
  startup behind the SWEET board guard, rejects failed controller MMIO maps,
  and adds an idempotent initializer with a read-only probe entry point. The
  probe ignores `ufsrw`; root mode honors it only when explicitly requested.
- `IOKitBSDInit.cpp` gains an opt-in `fp6ufsprobe=1` hook and FP6 `rd=ufsroot0`
  routing. The probe image retains `rd=md0`; the root image omits the RAM disk
  and leaves the existing Android `userdata` untouched. At the initial source
  change, neither image had been built or booted; follow-up CI/package results
  are recorded below.
- Corrected `tools/mkadt.py` to match the FP6 stock DTB's Cliffs TLMM:
  physical base `0x0f000000`, 16 MiB range, SPI 208, 179 GPIOs, reserved 56–60.
  This replaces an incorrect Volcano-compatible/reserved-pin guess.
- The FP6 bugreport identifies the touch controller as ESWIN EPH86xx on SPI0.0
  at QUPv3 SE0 `0xa80000`; the Fairphone SM7635 modules contain its SPI driver.
  The matching FP6 SKU overlay includes the Volcano MTP touch description:
  SPI mode 3 at 2 MHz, IRQ TLMM GPIO 19, reset GPIO 20, SPI pins 94–97, L22B
  and L9B supplies, plus `EPH86XX_fw.bin`. Linux's GPIO number 364 corresponds
  to the source reset pin in that overlay, although XNU must use the TLMM-local
  pin number 20.
- Updated the generated FP6 ADT to mark QUPv3 SPI0 and its ESWIN touch child
  present, with the overlay's GPIO and panel metadata. The controller still
  needs a GENI driver, pinmux/clock/regulator support and a HID event service;
  marking the ADT node present does not turn on the physical bus.
- Added opt-in `fp6gpio=1` and `fp6touch=1` passive probes to the UFS-probe
  image. They sample Cliffs GPIO input states (skipping reserved pins 56–60)
  and report the ESWIN touch ADT node. They do not access SPI MMIO or write pin
  mux, clock, reset, or SPI command registers.
  The successful build contains these paths; no phone observation exists yet.
  They are diagnostics, not a touch event driver.
- The corrected workflow run `39423526775` succeeded on source commit
  `d50bbff0304a365ee2972e3c041b2a9936e53591`. CI kernel SHA256:
  `2736519b29b5b6737aa40ddbf2377affea27d3a0adc5db7279677bc90a061181`; FP6
  ADT SHA256: `da9a1f5881207ac946db3f64cbd4165b8828a899019a049a04bb49081d3529f4`.
- The CI `fp6-boot` job skipped packaging because `FP6_STOCK_DTB_URL` is not
  configured. Using the verified CI kernel/ADT and local matching stock DTB
  (`16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`),
  locally packaged Android boot header-v2 images in
  `/tmp/fp6-ci-39423526775/images/`. The recommended read-only probe image is
  `touch-probe/fp6-shim-touch-ufs-probe.img`, 22,917,120 bytes, SHA256
  `f5abf0c8697aebef950f1d1fa6d997d6eae1d3a770caacd3b3377b0d26928198`; its
  command line keeps `rd=md0` and enables `fp6ufsprobe=1 fp6gpio=1 fp6touch=1`.
  Baseline and `rd=ufsroot0` images are alongside it. Package validation
  confirmed embedded kernel/payload/DTB and all SHA256SUMS; no image has been
  booted. Current Android `userdata` is not the iOS HFS+ root image.
- FP6 USB gadget/debug transport and active EPH86xx SPI/HID input remain
  unported; Sweet's SM7150 implementations are still guarded from FP6.

## FP6 Qualcomm UFS SOC bring-up (2026-10-20)

- Added and pushed commit `b1d8734` (`feat(fp6): initialize UFS power and SMMU
  handoff`). Patch `0105-fp6-ufs-soc-basics.patch` adds FP6-only handling for
  the UFS SMMU stream, the Qualcomm `broken-ahit-wa`, UFS power-mode query and
  wake-up, fixed/descriptor sense parsing, and bounded readiness retries. The
  FP6 ADT now includes SMMU base `0x15000000`, size `0x100000`, and UFS stream
  ID `0x60`. The SMMU path preserves a pre-existing stream mapping and only
  creates a bypass context for this stream when it is unmapped; it does not
  alter global SMMU settings or other streams.
- GitHub Actions run `39439447885` built the FP6 kernel successfully (build
  job `118685115137`, 6m57s) and generated/uploaded the matching ADT. The
  `fp6-boot` packaging step skipped because repository variable
  `FP6_STOCK_DTB_URL` is unset.
- Downloaded CI kernel SHA256
  `9f7b6335a4d377779618832b22a49d8f69685ad1f133481218af11c61ecef3c7` and ADT
  SHA256 `9d9957b903bb091d91ab688788facee0432f2ddc8ade82081ad48239d65bc467`.
  Reused the exact stock FP6 DTB from the previous verified v2 boot image;
  its SHA256 `16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`
  matches that image's manifest. Locally packaged the header-v2 UFS-root image
  at `/tmp/fp6-soc-39439447885/ufs-root/fp6-shim-ufs-root.img`, 22,917,120
  bytes, SHA256
  `3f557a3bbe16056d8e53a67dba70de89ba7aa693659be74946c77e33f41be2ad`.
  Its command line is `debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress
  rd=ufsroot0`; packaging verified the embedded kernel, payload and DTB.
- Source/build/package results only. The new SMMU/UFS path has not been booted
  on hardware; the image leaves userdata and all partitions untouched. Next
  step is the user's temporary `fastboot boot` test, then use the resulting
  console/panic or root mount observation to tune the stream mapping and UFS
  command path.

## FP6 UFS root HFS mount fix (2026-10-20)

- User tested the UFS-root image from run `39439447885`. Phone output reported
  `userdata` on LUN 0, first block `0x666d88`, 213586 MiB, read-only, and an
  enabled SMMU stream entry for SID `0x60` (`SMR=0x80000060`). The selected
  `ufsroot0` device was then followed by root mount failure `errno 19`
  (`ENODEV`). This confirms discovery and root-device selection; SMMU mapping
  was already present and preserved.
- Traced the mount failure to FP6's generated master config: patch 0026 builds
  and registers the Apple OSS HFS implementation only when `SWEET_HFS` is
  enabled, but the new `MASTER.arm64.fp6` config omitted that option and the
  `sweet_hfs` filesystem selection. Added patch
  `0106-fp6-enable-hfs-root.patch` and pushed commit `4ce0c16`; it enables both
  for FP6 so `vfs_mountroot` registers HFS.
- CI run `39441508260` built successfully (build job `118692265513`, 7m30s).
  As before, automated boot packaging skipped because `FP6_STOCK_DTB_URL` is
  unset. Locally packaged the matching kernel/ADT and verified stock DTB as a
  header-v2 UFS-root image:
  `/tmp/fp6-hfs-39441508260/ufs-root/fp6-shim-ufs-root.img`, 23,396,352 bytes,
  SHA256 `ed7d3aeaa163215c375f1eb11b7068e3399f3c263831c5a9013533f41d2f19fd`.
  The manifest records kernel, ADT and DTB hashes and `rd=ufsroot0`; package
  validation confirmed the embedded components. This HFS-enabled image has
  not yet been booted on the phone.
- Follow-up phone output shows HFS finds an in-filesystem journal at offset
  `0x800000`, but journal-header update fails with `EINVAL` while the UFS
  device was initialized read-only. The root mount path deliberately defaults
  to read-only unless `ufsrw=1` is passed; HFS journal replay/update needs the
  custom userdata partition writable. Packaged a follow-up image with that
  explicit opt-in:
  `/tmp/fp6-hfs-rw-39441508260/ufs-root/fp6-shim-ufs-root-rw.img`, SHA256
  `74dda22095553a68ebd8cb61b2836b896440cb3908c728c02554fc075f839d30`.
  Its write path remains bounded to the GPT partition selected by `ufsroot`
  (`userdata` by default); it cannot address other UFS partitions. This
  read-write image has not yet been tested on the phone.

## UniXNU repository review (2026-10-20)

- Shallow-cloned the UniXNU build repository to `/home/ersa/Dev/UniXNU` with
  its shallow driver/kit submodules, the device repo to
  `/home/ersa/Dev/UniXNU-sheng` with its shallow touch/preflight submodules,
  and firmware repo to `/home/ersa/Dev/uefi-sheng`. Main repo commits at
  review: UniXNU `5725f11`, UniXNU-sheng `b409de2`, uefi-sheng `329b473`.
  All these checkouts were clean after cloning. Source review only: no build,
  tests or phone run was done.
- UniXNU-sheng targets Xiaomi Pad 6S Pro / SM8550 and boots through its own
  Mu-Silicium UEFI plus DarwinBoot flow. FP6 currently boots through the
  existing fastboot shim, so the UniXNU boot chain is a separate architecture
  choice; its driver repos can still be referenced or selectively ported.
- Most transferable source is at the interface/algorithm level: ARM CPU/GIC/
  timer, ADT matching, UFSHCI command handling, SMMUv2 4 KiB table code,
  framebuffer copy/present, GENI SPI transport, HID event publication and
  root-manifest verification. None should be assumed board-ready for FP6.
- Confirmed board-specific limits: NativeUfs matches `qcom,sm8550-ufshc` and
  hardcodes sheng GCC/UFS physical ranges and stream setup; NativeAdreno and
  AdrenoPM4 are A740-specific; NativeNovatekTouch is for the sheng NT36532E;
  NativeMobileDisplay uses firmware GOP/framebuffer scanout and has no hardware
  vblank. NativeMetal's demonstrated GPU path depends on the Adreno/Turnip stack.
- `kits/VerifiedRoot` implements an owner-key RSA-3072/SHA-256 block-manifest
  format; it is not Apple's Image4/APFS sealed-root authentication. NativeAES
  and NativeKeyStoreEvents do not implement QTEE communication or SEP-backed
  AppleKeyStore. Check each module's own license before copying; the collection
  mixes BSD-2-Clause-Patent, BSD-2-Clause, MIT, and Apache-2.0 code.
- The UniXNU organization page showed three top-level repositories at review;
  the build repo additionally pins 21 driver/kit submodules, and the sheng
  device repo adds two submodules. See the checked-out READMEs and source under
  `/home/ersa/Dev/UniXNU*` for exact per-module commits.
