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

The live phone remains on the validated 0080 kernel during development.
0081 requires a new temporary boot to exercise the replay hook; it makes no
root-image changes. The intended test is to capture one full report with
matching BEGIN/END markers and preserve the GCC plus both GDSCR raw values.
