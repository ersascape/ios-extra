# Fairphone 6 platform audit

This is the initial source audit for the Fairphone (Gen. 6), device name
`FP6`. Fairphone identifies its platform as Snapdragon 7s Gen 3 / SM7635.
It is not QCM6490; QCM6490 is used by Fairphone 5.

## Source findings

- Fairphone publishes kernel and device-tree references for Gen. 6 under its
  `odm/rc/target/15/fp6` source branch. Fairphone notes that the full ODM tree
  cannot be built from source because it depends on proprietary toolchains and
  components.
- Mainline Linux has a `milos-fairphone-fp6.dts` board file with compatible
  strings `fairphone,fp6` and `qcom,milos`. The platform therefore differs from
  this repository's SM7150 / Sweet-Phoenix machine support.
- Fairphone's published specifications list a 1116x2484 display with adaptive
  10-120 Hz refresh. This repository's ADT generator currently constructs a
  Sweet/Phoenix-era memory, CPU, framebuffer, and storage profile; those values
  cannot be reused as FP6 facts.
- The current experimental GPU driver and phone measurements are specific to
  SM7150 / Adreno 618. They do not establish support for SM7635 or its GPU.

## Current status

Source inspection only. No FP6 XNU machine config, ADT profile, kernel build,
CI run, or device boot has been added or validated. The mainline board DTS and
Fairphone's ODM sources are references, not an XNU boot tree. Boot-time memory
ownership, CPU topology, GIC/timer setup, storage handoff, framebuffer
ownership, and the SM7635 GPU/GMU sequence remain unverified for this XNU port.

## References

- [Fairphone Gen. 6 specifications](https://www.fairphone.com/the-one-that-lasts)
- [Fairphone Gen. 6 kernel repositories](https://code.fairphone.com/projects/fairphone-gen-6/kernel.html)
- [Fairphone Gen. 6 ODM source instructions](https://code.fairphone.com/projects/fairphone-gen-6/odm.html)
- [Mainline Fairphone 6 device tree](https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/7711f4417f1870e4bfbee1a7d501f789255bc7aa/arch/arm64/boot/dts/qcom/milos-fairphone-fp6.dts)
- [Fairphone 6 kernel source repository](https://github.com/fp6-aosp/android_kernel_fairphone_sm7635)
