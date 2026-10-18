# Recovering complete GPU boot inventory: patch 0081

The first phone test reached the home screen, but the captured UDP stream
started partway through the initial GPU report. The GCC readings and CX/GX
GDSCR values were missing. The exact early-stream loss mechanism is unknown.

Patch `0081-sweet-gpu-inventory-replay.patch` caches the inventory read by
0080 and reprints it later through the existing console/USB logging path.
It adds no additional MMIO accesses, clock writes, power votes or mappings.

## Behavior

- `sweetgpu=1` performs the same initial guarded GCC/GPUCC inventory.
- Values and the outcome (mapping failure, config clock unavailable, or
  complete GPUCC inventory) are saved before publication to the USB thread.
- Initial output is bounded by `BEGIN boot inventory report 0 (cached=0)`
  and `END boot inventory report 0` markers.
- With USB device logging enabled, the logger reprints the snapshot after
  roughly 5, 15 and 30 seconds of configured-loop time. These are reports
  1–3, marked `cached=1`, with their own BEGIN/END markers.
- Replayed values are the original boot measurements, not fresh samples.
  The configured-loop counter is bounded; it does not replay forever.
- With `sweetgpu` absent, zero or unsupported, no snapshot is published and
  the USB replay hook emits nothing. With `sweetusblog=0` or USB device mode
  disabled, the initial report is still available through the console, but
  the replay hook is not run.

The startup path publishes its immutable snapshot with a release store;
the USB logger uses an acquire load. The logger owns the replay counter.
No extra kernel thread or heap allocation is introduced. The current UFS
startup contract calls the probe once.

## Validation

The host test now reconstructs the GPU source by applying every patch that
changes it, in order, rather than testing only the original 0080 file.
It covers the prior 11 MMIO cases and three replay/cache cases:

- Disabled or unconfigured probing cannot trigger replay mappings/output.
- Changing the mock hardware after the initial sample does not change the
  replayed values, and the replay adds no mapping calls.
- A cached mapping failure is replayed as a failure without retrying MMIO.

All three unit tests pass, including these 14 MMIO/cache cases. Real arm64
Mach-O object compilation of `sweet_gpu.c` and `sweet_usb.c` passes against
XNU headers using the existing CI compile log (0 of 2 files failed).

## Full build and images

[CI run 39154941656](https://github.com/dipa-studio/ios-extra/actions/runs/39154941656)
passed in 7m25s, building source commit
`3fc1124684f2bcf1ac9eebb03f9d18fc5ba9d2e4`.
The downloaded kernel passes its supplied checksum:
`2f29b0bea5b143f61562417ca346a59896b2370f238a271bf9546de75aacf9c3`.
Both `_sweet_gpu_probe` and `_sweet_gpu_replay` are present. The CI copies
of the GPU source, USB source, UFS caller and BSD source list match the
isolated local build tree byte for byte.

Images under `shim/out/`, each 17,203,200 bytes:

| Image | Mode | SHA-256 |
| --- | --- | --- |
| `shim-boot-0081-default.img` | `sweetgpu=0` | `209b236842959fe3cfd0f71cb3715c9f2ef1c5920dfe69de0e8643c8c075053a` |
| `shim-boot-0081-probe.img` | `sweetgpu=1` | `ad262ff3670fd79b537108b7a2e539d36d49730abb067cd90e514d223cbcc297` |

The ADT was copied byte for byte from the validated 0080 high-memory ADT.
Both images use the established UFS-root arguments, `cpus=6`, `sweetusb=2`,
`sweetfb_noconsole=1` and `sweetfb_hz=30`. Each image was unpacked and its
ramdisk compared with the intended payload; embedded boot arguments match.
Manifest: `shim/out/manifest-0081.json`. Packaging script:
`research/package-0081.py`. Artifacts and scripts stay in ignored scratch.

Kernel and build-tree artifacts are in the external `ios-extra-work/`
workspace under `out-0081/` and `ci-0081/`; logs are
`logs/ci-0081.log` and `logs/boot-package-0081.txt`.

The linked kernel also passed a 30-second QEMU early-boot snapshot check:
`no_panic_observed`, zero undecodable glyphs, using the same QEMU ADT,
copied HFS ramdisk and single-CPU arguments as 0080. Evidence is under
`ios-extra-work/qemu-0081/boot-local/`; QEMU ran from a dedicated `/tmp`
directory for Unix socket support. This does not exercise Qualcomm USB,
the delayed replay hook or GPU hardware, and is not a completed iOS boot.

The live phone remains on the validated 0080 kernel while awaiting device
availability. 0081 requires a new temporary boot to exercise the replay
hook; it makes no root-image changes. The intended test is to capture one
full report with matching BEGIN/END markers and preserve the GCC plus both
GDSCR raw values.
