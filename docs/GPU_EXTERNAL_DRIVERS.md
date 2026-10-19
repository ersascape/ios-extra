# Asahi, NullMoth and metal2vulkan: reuse for sweet

The user suggested Asahi and the NVIDIA Metal driver after the 0081 phone
boot. The useful split is an Apple-facing Metal plugin, reusable shader/API
translation, and an Adreno backend with its own kernel transport.

## Pinned references

| Reference | Inspected version | What it contributes |
| --- | --- | --- |
| [NullMoth NVIDIA macOS driver](https://github.com/nullmoth/nvidia-macos-driver/tree/637282334617d27bccf8aa2448497c0f19465dc8) | `637282334617d27bccf8aa2448497c0f19465dc8` | Objective-C Metal plugin, accelerator service properties, Vulkan integration and a vendored AIR translator |
| [metal2vulkan](https://github.com/steelbrain/metal2vulkan/tree/720ef1ce9ae2a2068999a8675717418b9416283e) | `720ef1ce9ae2a2068999a8675717418b9416283e` | Current AIR/metallib frontend, SPIR-V pipeline compiler and Rust runtime on Vulkan |
| [Asahi Mesa documentation](https://docs.mesa3d.org/drivers/asahi.html) | Documentation read 2026-10-18 | IOKit tracing and AGX command decoding methodology |
| [Asahi UAPI and synchronization design](https://asahilinux.org/2023/03/road-to-vulkan/) | Published 2023-03-20 | Buffer lifetime, asynchronous jobs, explicit fences and sharing contracts |
| [Mesa Freedreno documentation](https://docs.mesa3d.org/drivers/freedreno.html) | Documentation read 2026-10-18 | Adreno command generation, Turnip Vulkan backend and IR3 shader compiler |

Source checkouts are separate under the external
`ios-extra-work/references/` directory. No driver from these projects has
been installed on the phone.

## What the NVIDIA source establishes

[`plugin/NVMTLDevice.m`](https://github.com/nullmoth/nvidia-macos-driver/blob/637282334617d27bccf8aa2448497c0f19465dc8/plugin/NVMTLDevice.m#L140)
defines `NVMTLDevice` as an `MTLIOAccelDevice` subclass. Its
`initWithAcceleratorPort:` calls the superclass, checks the selected
accelerator, initializes its Vulkan backend and initializes device limits.
The accelerator's
[`Info.plist`](https://github.com/nullmoth/nvidia-macos-driver/blob/637282334617d27bccf8aa2448497c0f19465dc8/kexts/NVRM/accel/Info.plist#L37)
publishes `MetalPluginName` and `MetalPluginClassName`.

These are the same property names and initializer observed independently
in our iOS 16.7.16 cache. This supports the plugin direction with concrete
third-party implementation evidence. It does not verify that the macOS
plugin's inherited IOAccel contract matches our iOS image. Its build script
targets x86_64 macOS, while sweet needs arm64 iOS and the local framework ABI.
Its kernel accelerator depends on IOAcceleratorFamily2 and resource/surface
machinery that our minimal service does not yet provide.

The source's Vulkan adapter selects vendor backends and loads an ICD; the
Metal layer is not intrinsically a translator into NVIDIA machine code.
That makes its division of responsibilities relevant to an Adreno backend.
NVIDIA-specific SASS/NVVM paths, PCI/BAR handling, GSP firmware and display
setup do not implement sweet's GMU, SMMU or command processor.

The inspected root [LICENSE](https://github.com/nullmoth/nvidia-macos-driver/blob/637282334617d27bccf8aa2448497c0f19465dc8/LICENSE)
is **PolyForm Noncommercial 1.0.0**. Its vendored translator has an LGPL
notice. Keep those component licenses distinct when considering reuse;
public source availability alone is not a uniform license for the tree.

## The current shader/API component is further along

The independently inspected upstream metal2vulkan revision has a different
API and layout from the NVIDIA tree's vendored 0.1 translator. Upstream's
0.2 workspace separates:

- `metal2vulkan-air`: metallib containers, AIR bitcode, typed IR and metadata.
- `metal2vulkan`: device-profile-driven compute/render pipeline compilation
  into SPIR-V, resource layouts and binding plans.
- `metal2vulkan-runtime`: Rust devices, queues, encoders, resources and
  synchronization executed through Vulkan.

The current libraries read bitcode without launching external compiler
tools. Their runtime requires Vulkan 1.2 and timeline semaphores. It is a
Rust API following Metal's object model, **not an Objective-C implementation
of Apple's binary framework interface**. Connecting the real compositor
still needs a device plugin and compatible IOSurface/resource contracts.
See the pinned [README](https://github.com/steelbrain/metal2vulkan/blob/720ef1ce9ae2a2068999a8675717418b9416283e/README.md)
and [runtime README](https://github.com/steelbrain/metal2vulkan/blob/720ef1ce9ae2a2068999a8675717418b9416283e/crates/metal2vulkan-runtime/README.md).

Its license is `GPL-2.0-or-later OR LGPL-3.0-or-later`. Exact revision pinning
matters: the NVIDIA wrapper's 0.1 calls do not establish compatibility with
this 0.2 API. Actual iOS 16 system metallib coverage remains to be tested
offline; host tests of synthetic inputs cannot establish it.

## What to take from Asahi

Asahi supplies Apple AGX hardware support for Linux graphics APIs. It is not
the Apple-facing Metal device implementation needed on sweet. Its AGX
instruction encodings, firmware structures and page tables are for another
GPU architecture.

Useful transferable techniques are IOKit call tracing, submitted-buffer
capture/decoding, small offscreen experiments and a deliberate split between
kernel memory/submission and userspace command generation. Its documented
sync design also shows why buffers must remain alive until queued work
finishes and how cross-process sharing carries completion dependencies.
Apply those contracts to IOSurface sharing rather than copying Linux
DMA-BUF interfaces into an iOS service without an adapter.

## Candidate integration and next proofs

```text
iOS Metal.framework
  -> Sweet Metal device plugin (iOS Objective-C and IOAccel contracts)
  -> metal2vulkan AIR/pipeline translation, optionally its Vulkan runtime
  -> Turnip + IR3 (Adreno commands and machine code)
  -> Darwin buffer / GPU-VA / submission / fence transport
  -> SweetGPU: CX/GMU/GX, firmware, SMMU and SQE

shared rendered IOSurface -> existing framebuffer output
```

This is an engineering candidate, not a running stack. In particular:

1. Use the now-complete clock/domain report to implement bounded hardware
   initialization, mappings and a command-processor memory-write test.
2. Extend the host-owned AIR fixture smoke tests to selected local iOS
   libraries offline, retaining
   all Apple inputs/derived artifacts outside Git.
3. Exercise a custom plugin in an isolated iOS test process. Verify the
   actual device initializer and required selectors before advertising it
   to the compositor.
4. Adapt the Adreno userspace transport, query real enabled Vulkan features
   and pass that device profile to the translator. A desktop NVIDIA profile
   cannot describe A618 capabilities.
5. Demonstrate IOSurface sharing and completion ordering, then opt into
   compositor integration with measured feature coverage.

This research identifies a concrete existing AIR frontend and API component.
It reduces the amount of compiler work we may need to write, while the
hardware bring-up and iOS ABI proofs remain separate milestones.

## Host build and translation results

Built the pinned upstream 0.2 CLI on Linux with Rust 1.98.0, release mode
and `RUSTFLAGS=-Dwarnings`; the build passed in 3m36s. Cargo target output
is external at `ios-extra-work/metal2vulkan-target/`. Rust uses a dedicated
`/home/dipa/.cache/ios-extra-rust/` directory; no shell PATH files were changed.
The initial external-drive rustup attempt failed on symlink creation before
toolchain installation, so the small toolchain lives on the local filesystem.

Two translation cases passed using upstream-owned synthetic fixtures and
the upstream `vk12-floor` reference profile:

| Case | Output | Result |
| --- | --- | --- |
| `kernel_copy_word.ll` | 872-byte compute SPIR-V | CLI verified PASS; `spirv-val` Vulkan 1.2 PASS |
| `vertex_varying_triangle.ll` + `fragment_varying_color.ll` | 776-byte vertex and 5,472-byte fragment SPIR-V | Both modules verified PASS; `spirv-val` Vulkan 1.2 PASS |

LLVM 22's C API parsed the fixtures and wrote AIR bitcode without
optimization; the render case linked both modules and supplied an explicit
two-float2 vertex descriptor plus BGRA8 output. The CLI read these AIR
inputs through its native frontend. Each worker had a 20-second process-group
deadline and a 500 MiB address-space limit. Observed wall times were 0.017s
and 0.010s; cumulative child RSS high-water was 40,724 KiB. This is a tiny
host smoke test, not a compiler coverage or performance benchmark.

No Adreno GPU work or pixel comparison was performed. The Vulkan reference
profile is not a measurement of the phone's capabilities, and these inputs
are not iOS system metallibs. The result establishes an actually built and
exercised AIR-to-SPIR-V path, while iOS library/ABI and hardware execution
coverage remain open.

Evidence: `logs/metal2vulkan-build.txt`, `logs/metal2vulkan-Cargo.lock`,
`metal2vulkan-smoke/manifest.json`, per-case translation/metrics files and
the ignored `research/metal2vulkan-smoke.py` runner. All are under the
isolated ios-extra workspace. The built CLI SHA-256 is
`d7ab8295f3617e831540b6ccb1ebe504606a33d16c2aa8cec4fa0824cad45bfb`.

## apple-silicon-anyos-project (source review, 2026-10-19)

User-supplied [repository](https://github.com/medfa12/apple-silicon-anyos-project),
pinned at `59fd73aac4ae386939bc69dc58dffbce1b2167b2`. Selected files inspected via
GitHub API; external copies under `ios-extra-work/anyos-review`. No code imported,
compiled or run here.

Its [README](https://github.com/medfa12/apple-silicon-anyos-project/blob/59fd73aac4ae386939bc69dc58dffbce1b2167b2/README.md)
reports macOS 26 Welcome/Language screens on an Axion ARM Linux KVM host, using
the guest's built-in AppleParavirtGPU driver, a QEMU device and a Metal-to-Vulkan
renderer. The reported Vulkan implementation is CPU lavapipe/llvmpipe, so that
result does not establish Adreno acceleration. These are the project's claims,
not a reproduced result on sweet or evidence about our missing wallpaper.

Concrete reusable candidates from inspected source:

- Vendored [metal2vulkan API](https://github.com/medfa12/apple-silicon-anyos-project/blob/59fd73aac4ae386939bc69dc58dffbce1b2167b2/vendor/metal2vulkan/src/lib.rs)
  exposes translate/translate_reflected and native LLVM-IR-to-SPIR-V paths.
  This revision uses external llvm-dis/spirv-val tooling; its pipeline comment
  targets Vulkan 1.3 validation. It differs from the separately pinned upstream
  translator above. Actual A618 feature requirements and iOS metallib coverage
  need offline tests, not an assumption of compatibility.
- The [shader cache](https://github.com/medfa12/apple-silicon-anyos-project/blob/59fd73aac4ae386939bc69dc58dffbce1b2167b2/vendor/pvg-vulkan/crates/pvg-vulkan/src/runtime/m2v_cache.rs)
  calls that translator and couples SPIR-V with reflection/resource bindings.
  Useful design/code candidates for a later Vulkan-backed Metal layer.
- The [graphics host](https://github.com/medfa12/apple-silicon-anyos-project/blob/59fd73aac4ae386939bc69dc58dffbce1b2167b2/vendor/pvg-vulkan/crates/pvg-vulkan/src/lib.rs)
  has explicit macOS/Linux target gates and a QEMU ABI. Its Cargo manifest uses
  ash for Vulkan and a local translator dependency. It is not currently an iOS
  Metal plugin or an Adreno kernel driver.

Assessment: useful later shader/Metal interoperability research, with a different
Apple-facing paravirtual transport to evaluate. It supplies no measured shortcut
for sweet's current GMU/GX/SQE bring-up. Our iOS image's paravirtual-driver presence
and ABI are unverified; do not infer macOS 26 guest support transfers to iOS 16.
Continue the measured hardware ladder before selecting a userspace integration.
