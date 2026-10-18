# Continue here — 2026-10-18, 19:21 UTC

The user is switching AI because usage is nearly exhausted. **Stop current
work after saving this handoff.** Their ongoing goal is a full Adreno 618
driver for their iOS/XNU port. This repository is the independent playground;
working changes are ported to ios-sweet only when requested.

## Read first and boundaries

- Repo: `/home/dipa/ios-extra`, public GitHub `dipa-studio/ios-extra`, main.
- Read `AGENTS.md` and the top of `NOTES.md`. Detailed results are already
  recorded there and in `docs/`.
- **Other agents work in `/home/dipa/ios-sweet`. Do not edit that checkout,
  its source/build trees or its research outputs.** No subagents were used.
- Temporary `fastboot boot` only. No flashing/partition changes. Never use
  `fastboot getvar`. Suppress device serials in output and Git.
- Preserve other agents' log receivers. Our tcpdump captures are all stopped.
- Phone was left running validated **0081**. The user has NOT confirmed
  fastboot availability for 0082. A pending UI question asks them to put it
  in fastboot; elapsed time is not a response. Do not reboot unannounced.

## Immediate next action

**0082 is implemented, fully CI-built and packaged. It has not been booted
on the phone.** Once the user confirms fastboot availability, temporarily
boot `shim/out/shim-boot-0082-arc.img`, capture its cached ARC reports and
confirm UI/USB operation. No additional implementation is needed before
that measurement.

Image SHA256:
`7fca248b6c8af736aee7982388cb55fedf9d4d825f279ea602007be9fe9cccba`.
Image size 17,203,200 bytes. It uses **sweetgpu=2**, cpus=6, sweetusb=2 and
the established UFS-root arguments. `shim/out/manifest-0082.json` holds exact
arguments and hashes. The ADT is identical to phone-tested 0081.

Start these **before** fastboot boot, in separate exec sessions:

```sh
sudo -n tcpdump -U -n -i any -s0 \
  -w /run/media/dipa/android/ios-extra-work/logs/phone-0082-arc.pcap \
  'udp and src host 192.168.7.2 and dst port 5140'
python3 tools/phone-ecm-host.py --timeout 120
```

The helper matches the fixed ECM MAC and configures host 192.168.7.1/24.
It retries across usb0 -> enp... renames; this exact race caused an earlier
missed capture and the helper subsequently succeeded on a real reboot.
Sudo -n works. Do not replace/kill the existing other-agent UDP listener.

For fastboot, use Python subprocess to capture `fastboot devices`, require
exactly one device, hold its serial only in memory, recheck the image hash,
then `fastboot -s <serial> boot <image>`. Store sanitized output outside Git.
Never print the captured serial. Prior examples can be reconstructed from
the sanitized `logs/phone-0081-retry-fastboot.txt`; no flash is required.

After USB comes up, wait through all three report windows (~5/15/30 seconds
of configured logger-loop time). Decode/analyze with the prepared ignored
scripts:

```sh
python3 research/decode-probe-0082-pcap.py
python3 research/analyze-0082.py
ping -c 3 -W 1 192.168.7.2
```

The analyzer validates complete numbered reports, each resource's declared
entry count and identical cached ARC tables. It writes
`logs/phone-0082-inventory.json`. It accepts explicit resource/database errors
as observations. Report every raw level, including padding. Stop only our
own tcpdump by matching its exact `-w` path, then decode once more. Do not
claim home-screen confirmation solely from process-start log lines.

## Current commits and validation

- Main implementation **6f76e4f15e0f52c65b37d8cf98e647900d5825b0**:
  `0082-sweet-gpu-arc-inventory.patch`, tests and docs.
- Latest pushed commit **08b2c24** records successful build/images and the
  CX/GMU source audit. Working tree was clean at handoff preparation.
- CI **39157726409 PASSED**, 5m02s:
  https://github.com/dipa-studio/ios-extra/actions/runs/39157726409
- Kernel: external `out-0082/kernel.development.sweet`, SHA256
  `510f85c8df5a3bff369ab14db41ecc4d91547b28b897ca4c041b58e60aa1afa2`.
  Supplied checksum verified. Both probe/replay symbols linked.
- CI GPU/RPMh/USB sources and BSD source list byte-match the isolated tree.
- All 3 repository unit tests passed. Harness: 14 clock/cache cases,
  **30 ARC cases + 512 seeded malformed-header/entry mutations**. The same
  harness passed AddressSanitizer and UndefinedBehaviorSanitizer.
- Real arm64 object generation passed (0/1 failed). No 0082 phone test yet.
- The optional full CI log fetch stalled with no output and was stopped
  during handoff. `logs/ci-0082.log` may be empty/incomplete. Existing
  `logs/ci-0081.log` is complete and already suffices for local compilation.
  Kernel and build-tree downloads ARE complete and verified.

0082 modifies **only bsd/dev/sweet_gpu.c**. It introduces sweetgpu=2 to map
the known command DB locator `0x0c3f000c` and its validated reserved-RAM DB.
It reads gfx.lvl/cx.lvl/mx.lvl address, aux version, priority and up to 16
raw uint16 levels. Locator, header, slave/address type, ranges, duplicate
identities and lengths are checked. Odd auxiliary offsets are decoded using
aligned word loads. Failure results are cached too.

No RPMh RSC/TCS maps, voltage-helper calls, power votes, hardware writes or
GPU/GMU/SMMU core maps. Default/mode1 behavior is preserved. The existing
display RPMh implementation is unchanged. Metadata does not prove a valid
future vote, current owned rail state or firmware checksum integrity.

## Workspaces and repeatable commands

External scratch: `/run/media/dipa/android/ios-extra-work` (ample room).
The home filesystem has little free space; keep generated large files external.
`shim/out` is an ignored symlink to external `shim-out/`.

Isolated XNU: `ios-extra-work/buildtree/xnu`. Local git baseline **d818e18**
contains validated 0081; its uncommitted GPU change is exactly patch0082.
The baseline before0080 was 788ab36, before0081 e074f6c. Do not reset away
this source change. Generated headers are in adjacent build/fakeroot/sdk dirs.

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -v
XNU_CC_OBJDIR=/run/media/dipa/android/ios-extra-work/objects \
  python3 tools/xnu-cc.py \
  /run/media/dipa/android/ios-extra-work/logs/ci-0081.log \
  /run/media/dipa/android/ios-extra-work/buildtree bsd/dev/sweet_gpu.c
```

Repackage with ignored `research/package-0082.py`. All three modes 0/1/2
are already generated and unpack-verified; no need to rerun unless changed.
The CI buildtree archive is external `ci-0082/buildtree.tgz`.

## Hardware knowledge for the next implementation

0081's three complete cached reports measured **CX and GX GDSCR both
0x00222001** (PWR_ON clear, SW_COLLAPSE set). All nine GPUCC branches were
off. GCC config AHB=0x00000001, MEMNOC=0x80000220, SNOC DVM=0x80000001,
DDRSS AXI=0. DDRSS's clear halt bit does not establish an owned enable vote.
Full evidence: `docs/GPU_REPORT_REPLAY.md` and external phone0081 logs.

Pinned Xiaomi source **758bb7ef50af360e728662a1ed3b3a1b977a2f13** is downloaded
under ignored research/gpu-sources. A618 specifically requests a618_gmu.bin,
a630_sqe.fw and secure subsystem a615_zap. Exact firmware bytes unverified.

`docs/GPU_POWER_SEQUENCE.md` maps the dependencies. CX regulator has an MX
parent; CX GDSC parent is VDD_CX_LEVEL. GMU 200 MHz uses GCC GPLL0 divided
parent, selector6/HID2 at GPUCC RCG0x1120; shared GCC gate0x52004 bit16.
Linux consumer corner constants add 1; command DB stores raw values; ARC
requests carry a table INDEX. GMU needs SMMU-mapped HFI/log buffers before
reset release. CPU 16KiB pages do not establish the SMMU granule.

After obtaining 0082 data, design a separate opt-in, bounded CX/GMU power
experiment. Existing sweet_rpmh_vreg_enable accepts only ldoc11 in mV;
its VRM sender is not an ARC API. Future ARC transport must share apps-DRV
serialization and account for MX/CX dependencies and inherited votes.

## Metal / external driver research already completed

See `docs/GPU_API_RE.md` and `docs/GPU_EXTERNAL_DRIVERS.md`; do not redo RE.
Our iOS16.7.16 Metal loader enumerates IOAcceleratorES, reads MetalPluginName
and MetalPluginClassName, loads an Extensions bundle, checks _MTLDevice
subclassing and calls initWithAcceleratorPort:. Base implementation is
abstract; MTLIOAccelDevice adds IOAccel contracts. Actual custom iOS plugin
and compositor integration are not implemented.

External pinned references:
- NullMoth NVIDIA **637282334617d27bccf8aa2448497c0f19465dc8**: concrete
  MTLIOAccelDevice plugin uses that initializer and registry properties.
  Root license PolyForm Noncommercial; vendored translator LGPL separately.
- metal2vulkan **720ef1ce9ae2a2068999a8675717418b9416283e**: upstream0.2 has
  native AIR/metallib reader, SPIR-V pipeline compiler and Rust Metal-shaped
  Vulkan runtime. It is not an Objective-C drop-in framework. Dual license
  GPL2-or-later OR LGPL3-or-later. Needs actual iOS library/ABI coverage tests.
- Built upstream CLI with isolated Rust1.98.0 release and warnings-as-errors.
  **3 SPIR-V modules passed** CLI validation + spirv-val Vulkan1.2: compute
  copy and vertex/fragment pair, using upstream-owned synthetic AIR inputs.
  No phone GPU work/pixel comparison. vk12-floor is a reference profile,
  not measured Adreno capabilities. Evidence external metal2vulkan-smoke/.
  Rust toolchain `/home/dipa/.cache/ios-extra-rust/`; targets external
  metal2vulkan-target/. No shell startup files changed.
- Asahi contributes RE, asynchronous submission, lifetime/fence design;
  its AGX hardware backend is distinct from Adreno. Candidate future chain:
  iOS Metal plugin -> metal2vulkan -> Turnip/IR3 -> XNU transport -> SweetGPU.

Update NOTES.md after new results, keep Apple/device artifacts out of Git,
commit focused changes and use this repo's CI. Continue positively with
measured milestones; do not invent completion estimates.
