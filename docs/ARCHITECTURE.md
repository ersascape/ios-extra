# Source review of the imported baseline

Reviewed 2026-10-18 against upstream `347e190` (patches 0001–0079).
This describes code and existing engineering records. No new phone test or
kernel build was performed during this review.

## Boot and kernel

```text
Xiaomi ABL, fastboot boot
  -> Android boot.img v2: bare-metal shim + payload in ramdisk + stock FDT
  -> XNU Mach-O segments + generated Apple Device Tree + boot_args
  -> platform expert / CPUs / UFS root / HFS+
  -> dyld + shared cache -> launchd -> backboardd + SpringBoard
```

`tools/mkpayload.py` resolves Mach-O chained rebases ahead of time. The shim
loader copies segments, places the ADT and boot arguments after the kernel,
and jumps at EL1 with the MMU off. The shim reads ABL's FDT to locate the
payload; XNU receives the generated Apple tree from `tools/mkadt.py`.

The SWEET machine configuration builds plain arm64 with 16 KiB pages, without
Apple-specific CPU registers or pointer authentication. It uses a macOS-based
XNU configuration with compatibility additions for the iOS userland. That
configuration difference has already mattered: patch 0070 adds pid_hibernate
to avoid SIGSYS when an app leaves the foreground.

The upper RAM bank starts at `0x100000000`, with size `0xfcc00000`. Using it
avoids Qualcomm's protected regions in the lower bank. MMIO mappings, DMA
addresses above 4 GiB and cache maintenance are separate concerns.

GICv3 interrupts use nonsecure Group 1 IRQs. The phone's virtual timer INTID
is 19, unlike QEMU virt's 27. PSCI uses `smc` on the phone. Patches 0065 and
0078 implement secondary CPU startup, SGIs and up to eight CPUs. The six A55s
and two A76s are presented as one homogeneous SMP cluster; the code does not
yet give the scheduler a performance/efficiency topology. CPU suspend,
offline and frequency control are separate work.

Relevant sources are carried in patches 0004–0018, 0065 and 0078.

## Display and rendering

```text
CoreAnimation CPU rendering
  -> IOSurface user client (IOCoreSurfaceRoot)
  -> shared wired buffers, IDs, Mach ports and per-client mappings
  -> IOMobileFramebuffer user client (AppleCLCD), SwapEnd
  -> latest pending swap -> CPU copy into ABL framebuffer
  -> display hardware / panel already configured by ABL
```

Patch 0046 introduces `SweetSurface.cpp` and `SweetFramebuffer.cpp`. These
implement the subset of the iOS 16.7 user-client ABI needed for the GUI.
IOSurface has real buffer allocation, mappings and reference handling;
several optional selectors and synchronization features are accepted without
full semantics. Patch 0068 supplies the already-mapped lookup result expected
by userspace, which fixed a backboardd snapshot crash.

The physical panel buffer is at `0x9c000000`, 1080×2400, stride 4320, BGRA.
iOS sees an iPhone X canvas of 1125×2436 at scale 3. The driver crops the
centered physical viewport; touch applies the corresponding coordinate offset.
The logical size avoids UIKit layouts missing for the phone's native size.

Vsync notifications come from a nominal 60 Hz software timer. Panel copying
is throttled separately by `sweetfb_hz`; SwapEnd records the latest swap.
This is not hardware-vblank synchronization or GPU acceleration. Patch 0079
fades pixels to black for display-off; panel power remains on.

An accelerated renderer is a separate integration problem from display
scanout. There is no Adreno command submission, GPU address-space management,
firmware loading or Apple GPU service implementation in this baseline.
Changing scanout alone would not accelerate CoreAnimation.

## Input and power support

```text
RPMh vote for PM6150L L11C + TLMM power/reset
  -> GENI SE7 I2C -> Goodix GT9896 reports
  -> sweet_hid_touch -> SweetHIDTouch digitizer collections
  -> Apple IOHIDEventServiceUserClient / shared event queue -> backboardd

PMIC PON / GPIO -> SPMI observer reads
  -> sweet_hid_key -> SweetHIDButtons consumer events -> backboardd
```

The touch driver uses ABL-loaded GENI I2C firmware, configures FIFO operation
and packing, enables the rail, resets the controller and identifies it before
polling reports. It starts after a configurable delay, normally 45 seconds,
then polls at 10 ms. It supports the detected Goodix GT9896 Yellowstone
protocol and has a Focaltech 54:52 path. Supported code paths do not establish
that every panel variant has been tested.

The HID event/user-client/queue implementation incorporates Apple's
IOHIDFamily-1915.140.3, paired with the iOS userspace version. SweetHID supplies
the service base and hardware adapters. Patch 0071 marks contacts originating
near an edge for their lifetime so UIKit recognizes home/app-switcher gestures.

The RPMh client is a limited active-state regulator-vote implementation, not
a complete clock/regulator/sleep framework. Battery publication defaults to a
static source; `sweetbattery=1` enables read-only PMIC sampling and an
uncalibrated voltage-based state-of-charge estimate. Charger control and a
complete fuel-gauge algorithm are not implemented by that service.

Relevant patches: 0058, 0060, 0062, 0063, 0071.

## Storage, USB and diagnostics

The UFS driver takes over ABL's running host, uses one command slot and a
1 MiB contiguous bounce buffer, performs explicit DMA cache maintenance and
finds `userdata` by GPT partition name. It exposes BSD block/character devices
for the root; it is not a full IOKit storage stack. Access is serialized and
completion is polled. Writes require `ufsrw=1`.

The HFS+ root contains files copied from the iPhone X OS, SystemOS and AppOS
images. Cryptex contents and shared-cache links are placed where this boot
configuration expects them. It does not mount the original APFS volume layout.

The USB driver takes over powered/clocked DWC3 and PHY state left by ABL.
With `sweetusb=2`, it configures device mode, control transfers and CDC-ECM
endpoints. Events are polled. The kernel attaches Ethernet `ue0`, assigns
192.168.7.2/24 and can stream logs to 192.168.7.1:5140 over UDP. Existing notes
report successful host ping tests; iOS configd still lacks a corresponding
IONetworkInterface service. Kernel packet connectivity and iOS network
configuration are different completion criteria.

A 4 MiB console ring is written near the end of `userdata`, beyond the smaller
HFS root image, normally in 10-second batches. USB live logging is a second
consumer. Recovery-based extraction remains useful when USB never starts.
Other diagnostics include crash backtraces/reasons, IOKit lookup traces,
selected /dev/null output, heap-string scans and user stack samples.

Initialization is coupled: the UFS root initialization path starts persistent
logging, sampling, keys, touch and USB. A future driver must account for when
threads, services, clocks and rails become available; adding a C file alone
does not arrange its startup.

Relevant patches: 0028–0034, 0047–0055, 0069, 0072–0077.

## iOS compatibility and current limits

The Apple binaries run with a modified filesystem configuration and kernel
compatibility services. `sweet-root-tweaks.py` skips Setup, records migration
state, seeds activation preferences, removes CommCenter jobs, relaxes watchdog
behavior and disables media paths that crash with missing audio/GPU support.
The ADT supplies iPhone X identity and security-status properties used by
mobileactivationd's native Hactivation path.

AppleKeyStore is an unlocked/no-passcode compatibility service, with no SEP.
AMFI compatibility parses XML entitlements and grants platform status to root
filesystem binaries; sandbox handling is permissive. These support booting
the userland but do not implement the original security architecture.

No working GPU, Wi-Fi, Bluetooth, cellular, audio, camera, sensor or GPS
driver is established by this baseline. Existing notes distinguish crashes,
blocked synchronous XPC and missing filesystem behavior: a black app window
is not sufficient evidence that the framebuffer driver failed.

## Working in the playground

The versioned kernel source of truth is the patch series. The readable,
already-patched tree used for this review is under the reference checkout's
`research/bt28/xnu`; that directory is ignored and was not copied here.

The inherited CI fetches the pinned darwin-xnu-build tooling, stages libpthread,
HFS and BearSSL, applies patches, and uploads kernels plus a build-tree artifact.
The new repository adds a job guard for public visibility. Its initial run
39150033548 completed as skipped while private.

Before a first local hardware build here, stage the required local assets
without modifying the original checkout: stock DTB at `dtb/boot_unpacked/dtb`,
iPhone X product-tree template at `research/ipsw-x/d22ap.adt`, kernel artifact,
and recovery/root images as needed. Before local kernel edits, prepare a
separate build tree. The reference checkout's patch-order checker is ignored
and depends on its historical build trees; it is not a portable validator.

`tools/xnu-cc.py` currently embeds the original runner path
`/Users/runner/work/ios-sweet/ios-sweet/dxb`. It can replay the old logs;
support for the new repository's runner paths must be added before replaying
new ios-extra CI logs. This does not affect the CI kernel build itself.

For each experiment, distinguish successful source/compile checks, successful
CI linkage and a passing phone boot. QEMU helps with kernel behavior but
does not verify Qualcomm MMIO, power, DMA, the physical panel or touch.
