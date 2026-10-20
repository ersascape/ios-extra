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
uses the `MACHINE_CONFIG` repository variable if set; otherwise the existing
SWEET default applies. CI has not run this workflow for FP6 yet.

Source references inspected from LineageOS repositories at device-tree commit
`f32428a`, device configuration commit `564f00b`, and kernel commit
`9535e0f08` (all cloned to `/tmp`; no source was copied into this repository).

## References

- [Fairphone Gen. 6 specifications](https://www.fairphone.com/the-one-that-lasts)
- [Fairphone Gen. 6 kernel repositories](https://code.fairphone.com/projects/fairphone-gen-6/kernel.html)
- [Fairphone Gen. 6 ODM source instructions](https://code.fairphone.com/projects/fairphone-gen-6/odm.html)
- [Mainline Fairphone 6 device tree](https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/7711f4417f1870e4bfbee1a7d501f789255bc7aa/arch/arm64/boot/dts/qcom/milos-fairphone-fp6.dts)
- [Fairphone 6 kernel source repository](https://github.com/fp6-aosp/android_kernel_fairphone_sm7635)
