# Fairphone 6 platform audit

This is the initial source audit for the Fairphone (Gen. 6), device name
`FP6`. Fairphone identifies its platform as Snapdragon 7s Gen 3 / SM7635.
It is not QCM6490; QCM6490 is used by Fairphone 5.

## Source findings

- The LineageOS device-tree source has `qcom/fp6.dts`, which includes the
  Volcano SoC description and Fairphone switch/hall-key nodes. Its SKU overlays
  cover 600 and 603–608. The SoC DT describes eight cores across three clusters
  (4/3/1). Its memory node has a zero placeholder and the reserved-memory node
  is empty; bootloader/vendor data supplies information missing from this
  source tree.
- LineageOS's `BoardConfig.mk` identifies the target platform as `volcano`,
  uses boot header v4, includes the DTB in the boot image, and expects a DTBO
  image. Those are Android packaging settings, not a verified XNU boot recipe.
- Mainline Linux has a `milos-fairphone-fp6.dts` board file with compatible
  strings `fairphone,fp6` and `qcom,milos`. The downstream LineageOS tree uses
  Volcano naming. Both distinguish FP6 from this repository's SM7150 targets.
- Fairphone publishes additional kernel and device-tree references under
  `odm/rc/target/15/fp6`; it notes that the full ODM tree cannot be built from
  source because it depends on proprietary toolchains and components.
- Fairphone's published specifications list a 1116x2484 display with adaptive
  10-120 Hz refresh. This repository's ADT generator currently constructs a
  Sweet/Phoenix-era memory, CPU, framebuffer, and storage profile; those values
  cannot be reused as FP6 facts.
- The current experimental GPU driver and phone measurements are specific to
  SM7150 / Adreno 618. They do not establish support for SM7635 or its GPU.

## Build target status

An experimental `FP6` XNU machine config has been added for a kernel compile.
It uses a conservative ARM64 instruction baseline and records the source CPU
count/cluster count. `tools/mkadt.py --device fp6` now emits an FP6 ADT profile
with the Volcano CPU affinity IDs/topology, GICv3 and UFS register ranges, and
Fairphone identity. It includes the upstream FP6 simple-framebuffer address,
dimensions and stride. The LineageOS Volcano DTS has `reg = <0 0 0 0>` for
RAM; the FP6 ADT therefore carries zero RAM fields as a build-time template.
The shim reads the bootloader's runtime FDT, selects a contiguous RAM range
excluding its reserved regions and boot assets, then patches the ADT and XNU
boot arguments before entering the kernel. The upstream board source reserves
the splash area containing the framebuffer.

Generate the build-time ADT template:

```sh
python3 tools/mkadt.py /tmp/fp6.adt --device fp6
```

This is an ADT generation profile, not a boot-ready image. Runtime memory map
selection and framebuffer handoff still need validation against an FP6
bootloader FDT; the exact timer/interrupt handoff, CPU startup and storage
handoff also remain unverified.
The FP6 XNU machine config has not yet been validated by CI, and this profile
must not be used for a phone boot until those inputs are confirmed.

The `xnu` GitHub Actions workflow accepts `FP6` as a machine config and
publishes the generated `fp6-adt` template separately. On push, the workflow
uses the `MACHINE_CONFIG` repository variable if set; otherwise FP6 is the
default. Run 39414717734 built and packaged the FP6 kernel; its boot image was
not the previously used header v2 format, so it is not a verified device image.

Source references inspected from LineageOS repositories at device-tree commit
`f32428a`, device configuration commit `564f00b`, and kernel commit
`9535e0f08` (all cloned to `/tmp`; no source was copied into this repository).

## References

- [Fairphone Gen. 6 specifications](https://www.fairphone.com/the-one-that-lasts)
- [Fairphone Gen. 6 kernel repositories](https://code.fairphone.com/projects/fairphone-gen-6/kernel.html)
- [Fairphone Gen. 6 ODM source instructions](https://code.fairphone.com/projects/fairphone-gen-6/odm.html)
- [Mainline Fairphone 6 device tree](https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/7711f4417f1870e4bfbee1a7d501f789255bc7aa/arch/arm64/boot/dts/qcom/milos-fairphone-fp6.dts)
- [Fairphone 6 kernel source repository](https://github.com/fp6-aosp/android_kernel_fairphone_sm7635)

## Temporary boot image packaging

For a completed FP6 CI run, download `fp6-fastboot-boot`. It contains
`fp6-shim-boot.img`, `SHA256SUMS`, and a manifest with source and input hashes.
The packaging job uses that run's kernel and ADT. It requires a successful FP6
kernel build; a SWEET run does not produce this artifact.

Local packaging uses LLVM clang, lld, llvm-objcopy, llvm-readelf and llvm-nm:

```sh
python3 tools/fp6-package.py --kernel /path/to/kernel.development.fp6 \
  --adt /path/to/fp6.adt --dtb /path/to/fp6-stock.dtb \
  --out shim/out/fp6 --commit SOURCE_SHA --ci-run RUN_ID
```

For the tested FP6 boot path, use Android boot header v2 and embed the matching
stock FP6 DTB. `--dtb` is required and selects header v2. Header v4 without an
embedded DTB was rejected by the phone's bootloader with `Invalid Parameter`.
The layout follows [AOSP's boot image header definition](https://android.googlesource.com/platform/system/tools/mkbootimg/+/refs/heads/main/include/bootimg/bootimg.h).
The runtime loader accepts an aligned SWEETXNU payload following vendor ramdisks.
A missing framebuffer or rejected memory map halts the FP6 loader. The v2 image
repackaged from CI run 39417320648 is structurally verified but has not itself
been booted on the phone. CI only publishes this boot artifact when the repository
variable `FP6_STOCK_DTB_URL` points to a direct download of the matching stock DTB;
otherwise it skips the artifact instead of producing an unusable image.

After verifying SHA256SUMS, a temporary device test uses `fastboot devices`
(exactly one phone) and `fastboot boot fp6-shim-boot.img`. Record the displayed
shim status and bootloader response. The FP6 CI packager builds a tiny signed
init executable and appends it as a RAM disk, then boots with `rd=md0`. That
exercises kernel-to-userspace startup without depending on the current missing
UFS/IOMedia root path. It is a minimal bring-up init, not the iOS root
filesystem. The FP6 UFS host driver and HFS root-media path are still
unimplemented for this profile. Repackage with the stock FP6 DTB for the known
header v2 boot path. Do not use the Sweet GPU phone-test helper for FP6.
