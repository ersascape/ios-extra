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

## Phone measurements: 2026-10-18

Both temporary boots used the exact probe image above; no image was flashed.

The first boot started at 18:56:07 UTC and fastboot returned success in
0.569s. The user confirmed the home screen. USB ping returned 3/3 packets.
Our host setup encountered a `usb0` to `enp...` rename while running nmcli;
after manual configuration, the captured stream contained no GPU report.
There were 164 captured packets and no tcpdump kernel drops. The capture
contained framebuffer swaps and no kernel panic marker; it also contained
fitcored and PosterBoard process crashes. Their cause is unestablished.

Added `tools/phone-ecm-host.py` to retry interface discovery and configuration
by the fixed phone ECM MAC after rename failures. It was checked against the
live interface, then used for a second user-authorized boot.

The second boot started at **19:03:45 UTC**; fastboot completed in **0.563s**.
The helper configured `enp0s20f0u3u1` automatically. Ping returned 3/3 packets,
0% loss, average 0.780ms. Reports **1, 2 and 3** were captured with matching
BEGIN/END markers. Every report contained four GCC values, both GDSCR values
and nine GPUCC clock values; all three tables match exactly. They are
**replays of one boot measurement**, not three independent samples.

| Boot register | Raw value |
| --- | --- |
| GCC config AHB | `0x00000001` |
| GCC MEMNOC | `0x80000220` |
| GCC SNOC DVM | `0x80000001` |
| GCC DDRSS AXI | `0x00000000` |
| GPUCC CX GDSCR | `0x00222001` |
| GPUCC GX GDSCR | `0x00222001` |
| GPUCC AHB | `0x80000001` |
| GPUCC CX APB | `0x80000000` |
| GPUCC CX GMU | `0x80004220` |
| GPUCC CXO | `0x80000001` |
| GPUCC CX GFX3D | `0x80000000` |
| GPUCC CX slave | `0x80000000` |
| GPUCC GX GFX3D | `0x80004220` |
| GPUCC GX CXO | `0x80000001` |
| GPUCC GX GMU | `0x80000000` |

Both GDSCRs have `PWR_ON` clear and `SW_COLLAPSE` set. All nine GPUCC
branches report bit 31 set (off). The DDRSS value has halt bit 31 clear but
software enable bit 0 clear too; this alone does not establish a held host
clock vote. GPU/GMU/SMMU remained unmapped, and the probe performed no
hardware writes. The complete inventory closes 0081's measurement target;
it does not prove GPU execution or future core-register accessibility.

The retry capture contains 537 packets and 180,786 decoded bytes, with
zero tcpdump kernel drops. It shows SpringBoard/backboardd startup and
16 framebuffer swaps, no kernel panic marker or crash of those processes.
driverkitd and PosterBoard crashes are present, with unestablished cause.
The explicit user home-screen confirmation applies to the first 0081 boot;
the second boot's UI activity here is observed in the log. Only our own
capture was stopped; the phone remains running and the existing UDP logger
was preserved.

Evidence remains outside Git under `ios-extra-work/logs/`:
`phone-0081-fastboot.txt`, `phone-0081-probe.pcap/.txt`,
`phone-0081-retry-fastboot.txt`, `phone-0081-retry-probe.pcap/.txt` and
`phone-0081-retry-inventory.json`. Existing UDP receivers were preserved.
