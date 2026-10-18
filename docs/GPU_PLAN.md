# Adreno 618 driver plan

Goal: accelerate iOS rendering on sweet, including the system compositor and,
eventually, graphics APIs used by applications. Work lives in ios-extra; the
other agents' ios-sweet checkout is read-only reference material. Coordinate
shared-phone access before hardware experiments. No GPU probe or phone boot
has been performed as part of this plan.

## What we can build on

The saved live device tree identifies chip `0x06010800` and these blocks:

| Block | Physical base | Size |
| --- | --- | --- |
| GPU | `0x05000000` | `0x40000` |
| GPU SMMU | `0x05040000` | `0x10000` |
| GMU | `0x0506a000` | `0x31000` |
| GPU clock controller | `0x05090000` | `0x9000` |

These are device-tree declarations, not proof that registers are accessible
after ABL hands control to XNU. GPU clock/power state must be checked before
touching a potentially gated block.

Linux has a matching SM7150 entry with SQE/GMU firmware names, hardware setup
tables and a 4 GiB GPU-VA quirk. Reference snapshot:
[`a6xx_catalog.c` at Linux 32c52ec](https://github.com/torvalds/linux/blob/32c52ec87d6245ee2d12ed5dd509e40062939b50/drivers/gpu/drm/msm/adreno/a6xx_catalog.c).
The matching entry names `a630_sqe.fw`, `a630_gmu.bin` and `a615_zap.mbn`.
Confirm the phone's actual firmware files and secure initialization sequence
against the downstream driver before choosing artifacts or implementing it.
Firmware stays out of Git.

[Mesa Freedreno](https://docs.mesa3d.org/drivers/freedreno.html) supplies an
existing Adreno GL/GLES implementation; Turnip supplies Vulkan support.
[IR3](https://docs.mesa3d.org/drivers/freedreno/ir3-notes.html) supplies Adreno
shader-compiler infrastructure. These are starting points for reuse, not
drop-in Darwin/iOS drivers. Their kernel transport and platform assumptions
must be adapted.

## Two interfaces to establish

```text
iOS compositor / applications
  -> graphics API and driver integration       [research the exact boundary]
  -> Adreno shader compilation + command generation
  -> XNU SweetGPU: buffers / submission / synchronization
  -> SMMU + SQE + GMU + clocks / power
  -> Adreno 618

rendered IOSurface -> existing AppleCLCD output path -> panel
```

Hardware execution and iOS API integration each need an explicit proof.
Keep the working display output path during initial GPU bring-up; render to
offscreen buffers first, then connect them to IOSurface.

The local iOS 16.7.16 shared-cache inventory includes Metal, OpenGLES,
IOAccelerator, AGXMetalA11 and AppleMetalGLRenderer. Inspection of Mach-O load
commands found AppleMetalGLRenderer depends on Metal; AGXMetalA11 depends on
Metal, IOGPU and IOSurface. This proves dependency presence, not which renderer
CoreAnimation selects or whether a replacement GLES backend can serve it.

Trace renderer selection and the driver loading boundary early. Evaluate a
Mesa-backed GLES integration and a Metal driver integration from that evidence.
Full Metal support also needs a viable shader-input/compiler path: IR3 alone
does not provide an Apple shader-library/AIR frontend. Registering an AGX-like
IOKit service cannot translate Apple GPU commands or shader machine code.

## Milestones and acceptance criteria

| Stage | Work | Evidence required |
| --- | --- | --- |
| 0: map dependencies | Pin downstream and upstream sources; inventory clocks, rails, SMMU contexts, firmware and secure calls; trace iOS renderer/driver entry points | Source-backed initialization map and an identified or explicitly unresolved API boundary |
| 1: probe | Add an opt-in GPU state probe, using only audited accessible registers; log through the existing USB path | Repeated boots report power/clock state; unavailable blocks are skipped without hanging |
| 2: execution | Implement minimal power/GMU/SQE setup, GPU mappings, one command queue, bounded waits and fault logging | Command processor writes a known value into a mapped buffer; CPU reads it after completion; repeat successfully |
| 3: rendering | Submit an offscreen clear, then a triangle with known shaders and a textured draw | Correct pixel readback, completed GPU work and repeatable results; display through the existing output path |
| 4: userspace | Add buffer handles, queue submission, fences and a userspace transport for selected Mesa components | A native test process renders through the userspace stack with correct resource lifetimes |
| 5: iOS compositor | Implement the selected iOS API/driver boundary, IOSurface sharing and synchronization | SpringBoard actually submits GPU work; correct composition, blending, clipping, textures and effects |
| 6: full operation | Expand API/shader coverage, process isolation, scheduling, recovery, power management and performance | Application workloads and stress tests pass; reset/sleep/wake and failure handling are measured |

Stages 0 and 1 should also reduce uncertainty about stage 5. Do not postpone
all API research until hardware rendering works. A memory-write test proves
command execution; a triangle proves rendering; neither proves iOS integration.

## First implementation target

After the source audit, add tentative patch
`0080-sweet-gpu-probe.patch` with an opt-in `sweetgpu=1` mode. Audit which
clock/power registers can be read before reaching GPU/GMU/SMMU registers. The
probe should report why it skips a block and leave rendering on the existing
CPU path. Publish it as SweetGPU diagnostics rather than advertising an Apple
accelerator ABI before one is implemented.

Before compiling, stage a separate build tree here or in dedicated external
scratch space; never edit `ios-sweet/research/bt28`. Adapt the single-file
compile helper for this repository's CI paths. The user approved publication
on 2026-10-18; public macOS CI builds are now available.

For execution bring-up, start with one queue/context and explicit cache
maintenance. Audit GPU virtual-address limits separately from physical RAM
above 4 GiB. XNU's 16 KiB CPU page size does not establish the SMMU page-table
granule. Add mapping and fault diagnostics before arbitrary rendering commands.

The next concrete deliverables are the initialization dependency map, the
renderer-entry-point trace, and a reviewable opt-in probe patch. Progress is
measured by completed hardware and API tests; no completion date is inferred
from the earlier homescreen milestone.
