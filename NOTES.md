# ios-extra — current state

## FP6 GPU texture repeat test: a persistent failure, not a cold start (2026-10-23)

**Phone measured:** CI `40000677292` (head `54369bceec0805d1ed195001cc27205c4b6c64fb`, patch 0216)
passed. Image `/tmp/ios-extra-run-40000677292/package/fp6-texrepeat-0216.img` (SHA256
`5a13dc0c6bd837687a32cf61f66b993437c0cd59895019465bf5227995189773`; cmdline adds
`fp6gpureplayonly=tex fp6gpureplayrepeat=3`) booted once via `fastboot boot`; no flash, EDL or `getvar`.
Log `/tmp/ios-extra-run-40000677292/logs/phone-0216-texrepeat.txt`. Each of texlinear, texdouble and
texture ran three times in fresh address spaces; all reached their fence.

Differing samples per run: texlinear 24, 21, 21; texdouble 21, 22, 22; texture 21, 21, 24. Drawing the
quad twice (texdouble) did not help, so it is not a cold start of the first draw. The failing set is
nearly the same each time (18 to 21 pixels common to all three runs, 22 to 26 in the union), so the
failure is mostly deterministic with a small variable part. Still unexplained. Next candidates, in order:
compare Turnip's bindless texture path with Snapintosh's `CP_LOAD_STATE6_FRAG` indirect T#/S# path on
the same descriptor, and bisect the draw state register by register against the oracle
(`tools/fp6-pm4-state.py`).

## FP6 GPU: fitting the sysmem layout into 576 KiB did not fix texture sampling (2026-10-23)

**Phone measured:** CI `39998754954` (head `39e5063b7bf9e576c304900b8768850b29e69bc8`, patch
0215) passed. Image `/tmp/ios-extra-run-39998754954/package/fp6-scenes-0215.img` (SHA256
`d349997d0371527f6f13168a1b880422c5325815ac3c26a52b769e65178b8018`) booted once via
`fastboot boot`; no flash, EDL or `getvar`. Log
`/tmp/ios-extra-run-39998754954/logs/phone-0215-fit.txt`. All 13 replays reached their fence.

With the scene captures remade on a layout that ends exactly at the 576 KiB GMEM end (0214's cache
cleans kept): `texture` 20 and `texlinear` 21 samples differ (unchanged from the old layout), `vertexbuf`
still matches, `blend` now has 12 differing samples (was 0), and `depth` draws nothing (71 differ, 0 lit;
was 24 differ). So the 608 KiB layout overrunning GMEM is not what breaks texture sampling, and the
smaller sysmem VPC buffers are worse for depth. The GMEM-fitting Mesa change stays in
`tools/mesa-a810-sysmem-vpc.patch` as an experiment only; patch 0216 returns the scene captures to the
original layout (`TU_GMEM=622592`).

The remaining texture failures are confined to texel rows 0 and 1 (rows 2 and 3 are always right) and are
partial inside those texels: 20 of 256 samples, black (the clear colour), at nearly the same pixels in
`texture` (staging blit) and `texlinear` (host-written texture), but not exactly the same (for example
texel (0,0) 3 of 9 against 4 of 9). Same place and almost the same set for two different upload paths
suggests an effect of timing or of early pixels, not of the data. Patch 0216 adds
`fp6gpureplayonly=PREFIX` and `fp6gpureplayrepeat=N` to run selected captures several times, and a
`texdouble` scene (the same quad drawn twice) to separate a cold start from a persistent failure.

Source reading of the Snapintosh files (`SnapMetal/AdrenoMetal/AdrenoDrawCommands/*.m`,
`compat/adreno-ib-command.h`, `compat/adreno-submit.h`) for the PM4 builder: the emitter is a port of
Turnip's A8XX sysmem path (`fd6_emit_restore`, `emit_flushes`, 2D clear) with the X2-90's GMEM and CCU
constants written inline, and register fields come from a header generated from Mesa's A8XX registers.
`tools/gen-a8xx-regs.py` from that repository ran against our pinned Mesa (`6a7d302`) and produced the
same 8763-line header. Its kernel side (user IB package with relocations, allowlist validator) is the
design to follow for AdrenoGPU. `tools/fp6-pm4-state.py` is a new oracle that walks a Turnip capture and
returns the register state at the draw (350 registers for the flat scene).

## FP6 GPU cache clean changed results, and the CCU/VPC layout overran GMEM (2026-10-23)

**Phone measured:** CI `39997038633` (head `4de8492913561d2ebfbafa3879a3077242a2fcb5`, patch
0214) passed. Image `/tmp/ios-extra-run-39997038633/package/fp6-scenes-0214.img` (SHA256
`ce23ec192e6a94919cb676130fbc6f5bbe5b1ee4019a9d8e48dc11a1a3391d04`) booted once via
`fastboot boot`; no flash, EDL or `getvar`. Log
`/tmp/ios-extra-run-39997038633/logs/phone-0214-flush.txt`.

With `CCU_CLEAN_COLOR`, `CCU_CLEAN_DEPTH` and `CACHE_CLEAN` before the fence, `vertexbuf` now matches
(0 of 256 differ, 81 lit), `texture` improved from 78 to 20 differing samples, `texlinear` stayed at 22,
and `depth` got worse (1 to 24 differing). The 200 ms re-read changed nothing (no "after 200 ms" line),
so these are not late writes. 7 of 10 scenes match. Results that depend on which caches are cleaned
point at CCU/GMEM state, not at the data or the descriptors.

Source inspection and host work (no phone yet):
- The captured texture descriptor decodes to a 4x4 `FMT6_8_8_8_8_UNORM` 2D linear T# with identity
  swizzle, `TEX_LINE_OFFSET` 2048 (256-byte rows) and `ARRAY_SLICE_OFFSET` 1; this is the layout
  SnapMetal's `AdrenoLinearViewWords` builds, so the descriptor is not the problem.
- Mesa's A810 profile (`freedreno_devices.py`, `num_ccu = 1`) overrides only the `gmem_vpc_*` buffer
  sizes; its sysmem layout uses the gen1 defaults (VPC attr 128 KiB, pos 64 KiB, BV pos 32 KiB, CCU
  colour 128 KiB, depth 256 KiB), 608 KiB in total, hence the `TU_GMEM=622592` workaround. In every
  capture so far the in-stream state put the BV position buffer at `0x93000..0x98000`, past the end of the
  576 KiB GMEM (`0x90000`).
- `tools/mesa-a810-sysmem-vpc.patch` gives the A810 the GMEM-mode sizes (16384/12288/20480) for sysmem
  too. A Turnip rebuilt with it and `TU_GMEM=589824` emits a layout ending exactly at `0x90000`
  (`RB_CCU_CACHE_CNTL` depth offset `0x40000`, colour `0x80000`, VPC base `0x84000`..). Whether the
  hardware accepts these smaller VPC buffers is not yet known.
- Patch 0215 swaps the ten scene replays to captures made that way. Not yet built or run on the phone.

## FP6 GPU replay: UCHE/CCHE invalidation did not change the texture and vertexbuf results (2026-10-23)

**Phone measured:** CI `39994550223` (head `a86f8b4d7d3d4cba2f82f58dbe5e99613a7db456`, patch
0213) passed. Image `/tmp/ios-extra-run-39994550223/package/fp6-scenes-0213.img` (SHA256
`6042cbe2b1bb22bb06c10ce91c09b20c006f4896f1b216034e638cbeb9bf0d12`) booted once via
`fastboot boot`; no flash, EDL or `getvar`. Log
`/tmp/ios-extra-run-39994550223/logs/phone-0213-inv.txt`. Patch 0213 adds `CACHE_INVALIDATE7`,
`CP_CCHE_INVALIDATE` and a wait-for-idle before every replay IB (`fp6gpureplaynoinv=1` skips it).

Result: identical to patch 0212. 7 of 10 scenes match; texture (78 differ), texlinear (21) and
vertexbuf (81, nothing lit) fail exactly as before. So stale UCHE/CCHE lines from the previous
scene's address space are not the cause.

Source observation for the next test: in texture the wrong samples read `0x00000000` (the
zero-initialised result page, never written), in texlinear `0xff000000` (the clear colour). The
replay fence is a plain `CP_MEM_WRITE` after a wait-for-idle, which flushes no cache, whereas Linux
ends a submit with `CACHE_FLUSH_TS`. Patch 0214 cleans CCU colour/depth and the UCHE
(`CACHE_CLEAN`) before the fence and re-reads a mismatching result after 200 ms, to separate a missing
flush from a late write. Not yet run on the phone.

## FP6 GPU diagnostics measured: fetch paths work alone, two combinations still fail (2026-10-23)

**Phone measured:** CI `39992573473` (head `70253f55e0dd6f25088ebc4898d879132bd01248`, patch
0212) passed. Image `/tmp/ios-extra-run-39992573473/package/fp6-scenes-0212.img` (SHA256
`eb390e8e01407a555a97d251715a5445f575207d0bb8a36b85628e7190c713de`; same cmdline as 0211)
booted once via `fastboot boot`; no flash, EDL or `getvar`. Log
`/tmp/ios-extra-run-39992573473/logs/phone-0212-diag.txt`. All 13 replays reached their fence.

- `idxonly` (index buffer, no vertex buffer): 0 of 256 differ. `vbufdraw` (vertex buffer, no
  index buffer): 0 differ. So each fetch path works on its own.
- `vertexbuf` (both together, indexed draw with vertex input): still nothing drawn, 0 lit.
- `texlinear` (host-written linear texture, no upload blit): 21 differ (texture with blit: 78).
  The blit is therefore not the cause; sampling a texture is.
- flat, varying, ubo, blend, depth still match; the run reports 7 of 10 scenes matching.

Source inspection of the texlinear capture: texel rows sit 256 bytes apart in one mapped page
and the descriptor base `0x2e000` points at it, so missing data is not the explanation. No
cause established for either failure.

## FP6 GPU scene batch measured: 5 of 7 Turnip renders match lavapipe on the Adreno 810 (2026-10-23)

**Phone measured:** CI `39990503899` (head `a5fe62960adbc51ed9b7e3589b03818537f280ed`, patch
0211) passed. Image `/tmp/ios-extra-run-39990503899/package/fp6-scenes-0211.img` (SHA256
`36d4787e9054a6aaeb3cf92286a3abee0269a4c9019ddcc1c4e6305cc1cb0905`; cmdline adds
`fp6gpureplay=1 fp6gpureplaycb=1`) booted once via `fastboot boot`; no flash, EDL or
`getvar`. 92 packets; log `/tmp/ios-extra-run-39990503899/logs/phone-0211-scenes.txt`.
The ADT differs from the previous run's only in one 64-byte random field.

Seven scenes from `tools/fp6-vk-scenes.c` (64x64 RGBA8, Mesa Turnip A810 captures with
`TU_GMEM=622592 TU_DEBUG=sysmem,noubwc`, CONCURRENT_BIN_DISABLE cleared) were replayed at
their original IOVAs and each result's 16x16 sampled grid compared with lavapipe within 6 per
channel. Every replay reached its fence with `CB0_FSR=0x400` and no dropped packets; the
earlier `buf_init` (8/8) and `draw` (512 + 512 pixels) captures still pass.

| scene | result |
|---|---|
| flat, varying (interpolated colours), ubo (uniform colour) | 0 of 256 samples differ |
| blend (src-alpha over a clear colour) | 1 differs, edge pixel |
| depth (LESS test, overlapping triangles) | 1 differs, edge pixel |
| texture (sampled 2x2 checker) | **78 differ**: the top half of the quad (rows 2 to 7) reads `0x00000000`, the bottom half is right |
| vertexbuf (vertex buffer attributes) | **81 differ**: nothing drawn, 0 pixels lit |

Not yet explained: why the sampled texture returns zero for the upper half, and why a draw
fed from a vertex buffer draws nothing. Both replays map every captured BO page; suspects are
the texture upload path (the capture holds the staging copy and the image in one submit) and
vertex fetch from a BO the generator stores as data. Source inspection only so far, no cause
claimed. The grid comparison is lavapipe-based, so rasteriser edge pixels are tolerated up to
12 of 256.

## FP6 display level 3 measured: the panel is refreshed at 60 Hz during XNU boot 0210 (2026-10-23)

**Phone measured:** CI `39984929368` (head `4165fa338717a55306ce4348c93e3101c651a44d`)
passed; source matched. Image
`/tmp/ios-extra-run-39984929368/package/fp6-dpusnap3-0210.img` (SHA256
`e5a3325f883871ba13960032c674f2227b7d732387c868aa5cc762565ba8cdd0`; `fp6dpusnap=3`)
booted once via `fastboot boot`; no flash, EDL or `getvar`. 103 packets; log
`/tmp/ios-extra-run-39984929368/logs/phone-0210-dpusnap3.txt`. Reads only; no hang.

Eight samples 250 ms apart of INTF_1 `FRAME_COUNT`: `0x22627, 0x22636, 0x22645,
0x22654, 0x22663, 0x22672, 0x22681, 0x22690`, i.e. exactly +15 per 250 ms (105 frames in
1750 ms, 60.0 per second). So the DPU keeps pushing frames at 60 Hz while XNU boots, and
a write to the scanout framebuffer reaches the panel on the next transfer without any
DPU programming. INTF_1 `LINE_COUNT` over the same samples: `0x1d4, 0x1ae, 0x190, 0x150,
0xfc, 0xae, 0x61, 0x01` (varies; its semantics are not interpreted here). Pingpong 0 at
`+0x6a000` reads all zero (`TEAR_CHECK_EN`, `SYNC_*`, `RD/WR_PTR_IRQ`, `LINE_COUNT`,
`AUTOREFRESH`, `DSC_MODE`) and CTL0 `START`/`FLUSH` read zero at every sample, so the
60 Hz transfers are not coming from PP0's autorefresh and not from a CTL start seen at
these sample times. Not established: what triggers the transfers (another pingpong, a
hardware auto-refresh, or something the bootloader left running), whether that
persists after XNU's display code runs, and the TE source. This supports the
firmware-framebuffer display path and gives a free vblank-like source (INTF_1 frame
count, readable without writes).

## UniXNU-sheng package reference list (2026-10-23)

Source reading only (`github.com/UniXNU/UniXNU-sheng`, `package/`, 99 files; the sheng
board is an SM8550-class Adreno 7xx phone, so details differ from the FP6). Files
fetched read-only into scratch: `ShengGmuCommandDb.c` (RPMh command-db parser for GMU
vote inputs: ARC `gfx.lvl`/`mx.lvl`/`cx.lvl`/`gmxc.lvl` on slave 3, BCM `SH0`/`MC0`/
`ACV`/`CN0` on slave 5; checks address alignment, slave id in address bits `[18:16]`,
bounds, overlap and duplicates; its comment records that every slave type must be
searched and the table ends at the first zero slave id, the behaviour we adopted in
patch 0156), `OriginalMetalAsyncDiagnostic.mm` (six lines that set
`OFFLINE_RENDERBOX_ENABLE_ASYNC`, `OFFLINE_METAL_FENCE_DIAGNOSTIC` and
`OFFLINE_METAL_ASYNC_DIAGNOSTIC` and include `OriginalMetalLayerDiagnostic.mm`; a
harness running Apple's own Metal against their device with a drawable and GPU events),
`ShengDpuObservation.c/.h` (read-only DPU observation: MDSS/MDP versions, IRQ
status, and per DSI interface status `0x26c`, timing enable `0x0`, count enable
`0xa8`, command trigger `0x84`, frame `0xac`, line `0xb0`, hsync `0x08`, vsync period
`0x0c`; takes two samples and accepts them only if configuration and frame counters
agree, up to three attempts). Our level-2 interface offsets match theirs. Not fetched
but listed as relevant: `ShengGmu.c`, `ShengGmuVotes.c`, `GpuPowerProbe.cpp`,
`GpuPowerBoard.h`, `ShengGpuSmmu.c`, `LegacyDisplayProbe.cpp`,
`MobileDisplayProviderProbe.cpp`, `OfflineMetalSharedEvents.mm`,
`OfflineMetalSharedSurfaces.mm`, `AdrenoPM4Probe.c`, `AdrenoCompilerProbe.c`.

## Brightness reference: UniXNU-sheng AppleARMBacklight.cpp (2026-10-23)

Source reading only; nothing implemented or measured. The file the user pointed to
(`github.com/UniXNU/UniXNU-sheng/blob/main/package/AppleARMBacklight.cpp`, 384 lines;
absent from the local `/home/ersa/Dev/UniXNU-sheng` clone at `2a1b2f6`, fetched
read-only into scratch) drives the sheng phone's LCD backlight and shows exactly what
iOS expects from a backlight service. Hardware half (not reusable on FP6): two Kinetic
KTZ8866 chips on GENI I2C (address `0x11`, 11-bit level in registers `0x04`/`0x05`).
iOS-facing half (reusable pattern):
- CoreBrightness (backboardd) looks for a service with `backlight-control = true`,
  reads min/max from `IODisplayParameters` -> `brightness` {min, max, value} and sets
  `{brightness, FadePeriod}` through `setProperties` (`FadePeriod` is 16.16 seconds; the
  file clamps it to 5 s and steps the fade every 16 ms on its own work loop).
- The class cannot be named `AppleARMBacklight` (AppleARMPlatform already defines it;
  a duplicate panics at class registration), yet CoreBrightness only takes the service
  for the built-in display if `IOObjectConformsTo(service, "AppleARMBacklight")`
  holds, and backboardd's sandbox allows setting the brightness keys on that class
  only. The file copies its own vtable and overrides `getMetaClass` to answer
  AppleARMBacklight's metaclass; a kernel patch (`zzwb-native-sandbox-grant-set-properties`)
  lets backboardd alone set its properties. Publishing `backlight-control` without the
  conformance made the screen stop updating (their int-236: the libEDR server never
  started and QuartzCore's synchronous send blocked).
- `setProperties` must not block on the service work loop (their int-277/278): it
  stores the newest request atomically and arms a timer; a newer request replaces one
  not yet taken.
For the FP6 AMOLED the transport would be a DCS `WRDISBV` (`0x51`, 12-bit, big-endian
two bytes; the init sequences contain `51 0D BB`, `51 0F FE`, `51 09 D9`) sent to the
NT37705 over DSI, which is a panel write: it needs explicit user approval of the exact
step, a conservative cap well below the panel maximum (the dtsi gives
`peak-brightness = <14000000>` and the meaning of the upper range is not established),
and no static bright image. Not established: how to send a DCS command through the
FP6 DSI controller (command DMA path, clocks, LP mode) and which level the bootloader
left.

## FP6 display level 3 and brightness sources (2026-10-23)

Source/host only for level 3; no phone result yet. Patch 0210 adds `fp6dpusnap=3`:
the level-2 reads, a one-time dump of pingpong 0 (`+0x6a000`, offsets from mainline
`dpu_hw_pingpong.c`: TEAR_CHECK_EN, SYNC_*, RD/WR_PTR_IRQ, LINE_COUNT, AUTOREFRESH,
DSC_MODE), then eight samples 250 ms apart of INTF_1 `FRAME_COUNT`/`LINE_COUNT`, PP0
line counters and CTL0 `START`/`FLUSH`, to see whether the display is still being driven
after XNU takes over. Reads only; the host test asserts no register writes anywhere in
the probe. Host tests and arm64 compile pass; CI and phone pending.

Brightness (nothing implemented yet): the local UniXNU and UniXNU-sheng sources have no
brightness or backlight code (`drivers/NativeMobileDisplay` is a firmware-framebuffer
presenter whose README says "Display vblank is not implemented"; the only backlight
mention is a Linux reference-boot script for the sheng LCD). The FP6 panel dtsi shows
brightness as the standard DCS `WRDISBV` (`0x51`, 12-bit) written over DSI: the init
sequences contain `51 0D BB`, `51 0F FE` and `51 09 D9` (3515, 4094, 2521), and
`qcom,mdss-dsi-panel-peak-brightness = <14000000>`. That is a panel write; per the
display safety rule it needs explicit user approval for the specific step and a
conservative cap.

## Display safety constraint and panel confirmation (2026-10-23)

The user confirmed the panel is the BOE NT37705 (the `dsi-panel-nt37705-boe-amoled-cmd.dtsi`
file above is the right one, closing the "exact panel" caveat), and instructed: "don't
burn the display up!". The panel is AMOLED, so burn-in and damage are irreversible.
Rule going forward (also in `HANDOFF.md`): display probes stay read-only unless a
specific write is approved; no long holds of static images, no full-white or
max-brightness patterns, and no panel on-commands, panel reset, brightness/backlight
or DSI/DPU timing changes without explicit confirmation. The earlier scanout test
wrote one 512x512 patch (dark blue with an orange triangle) once during boot, for
seconds; it did not hold the image. A proposed 20-second hold patch was declined by
the user and is not in the tree.

## FP6 panel description found: downstream devicetrees (2026-10-23)

Correction to the previous entry: the panel node *is* available. The Lineage kernel
checkout `/home/ersa/Dev/android_kernel_fairphone_sm7635` has
`arch/arm64/boot/dts/vendor -> ../../../../../sm7635-devicetrees`, a symlink to a
directory that is not on this machine; that repository is
`github.com/LineageOS/android_kernel_fairphone_sm7635-devicetrees` (branch
`lineage-23.2`, `f32428ad60a7bf1ad04f9a8a001f27842e65fd79`), shallow-cloned read-only
into scratch (not committed). `qcom/fp6.dts` and `fp6-sku-60x-overlay.dts` are the
FP6 trees (the SKU overlays are copies of the Qualcomm MTP overlay and include no
display file themselves), and `qcom/display/display/` holds the SDE and panel files.
Source reading only; nothing here is a phone measurement.

The only panel file matching 1116x2484 is
`qcom/display/display/dsi-panel-nt37705-boe-amoled-cmd.dtsi`
(`qcom,mdss-dsi-panel-name = "nt37705 amoled command mode dsi panel"`): OLED, DSI
command mode, bpp 30 (10-bit), `rgb_swap_rgb`, 4 lanes (`lane_map_0123`),
`dma-trigger = trigger_sw`, `mdp-trigger = none`, TE pin used (`te-pin-select = 1`,
`te-check-enable`, `wr-mem-start = 0x2c`, `wr-mem-continue = 0x3c`), reset sequence
`<1 10> <0 5> <1 10>`, 66x146 mm, five timings of 1116x2484 at 120, 60, 90, 30 and
10 Hz (`timing@0..4`), DSC 1.1 with 558x12 slices, 2 slices per packet, 10 bits per
component, `bit-per-pixel = 8`, block prediction, and ten large `on-command`
sequences (the Novatek panel init). This agrees with the level-2 register dump
(command mode, DSC active, 1116x2484). Not established: which of the five timings the
bootloader selected, and that this is the exact panel file used by the shipped FP6
(it is the only 1116x2484 match). The DSI controller and PHY nodes in the stock DT
(`dsi-ctrl-hw-v2.8`, `dsi-phy-v5.2`) cover the host side.

## FP6 display snapshot level 2 measured 0209 (2026-10-23)

**Phone measured:** CI `39979637952` (head `bdc38ee407ec47e78f26bb026885560d7824e154`)
passed; source matched. Image
`/tmp/ios-extra-run-39979637952/package2/fp6-dpusnap2-0209.img` (SHA256
`d4fd91b52898d3ad16ecce0924f28d94034e319ca7ef13e5ad1cb7ab05aa41c1`; `fp6dpusnap=2`)
booted once via `fastboot boot`; no flash, EDL or `getvar`. 100 packets; log
`/tmp/ios-extra-run-39979637952/logs/phone-0209-dpusnap2.txt`. Read-only; no hang.

Register state the bootloader left (all values raw reads):
- GDSC `0xf822f800` (PWR_ON), `MDSS HW_VERSION=0xa0020000`.
- CTL0: `LAYER0=0x01000005`, `TOP=0xf0020000`, `FLUSH=0`, `START=0`, `INTF_ACT=0x2`,
  `DSC_ACT=0x1`, `FETCH_ACT=0x00010000`, `INTF_MASTER=0x2`, EXT0/2/3/4 = 0.
- LM0: `OUT_SIZE=0x09b4045c` (2484 x 1116), `BLEND0_OP=0x400`, `BLEND0_FG_SRC=0x00ff0000`.
- SSPP VIG0: `SRC_SIZE=OUT_SIZE=0x09b4045c`, `SRC0_ADDR=0xe3940000`,
  `YSTRIDE0=0x1170` (4464), `FORMAT=0x000237ff`, `UNPACK=0x03020001`,
  `OP_MODE=0x80000000`, `UBWC_STATIC=0xc0000101`. DMA0..2: all zero (`OP_MODE`,
  `UBWC_STATIC`, `FETCH_CFG` at their reset values).
- INTF_1 (DSI): `TIMING_EN=0` and every timing register 0 (command mode),
  `CONFIG=0x00800000`, `CONFIG2=0x00001111`, `PANEL_FORMAT=0x00002100`,
  `FRAME_COUNT=0x7b61`, `LINE_COUNT=0x5b3`, `MUX=0x000f0000`, `STATUS=0`.
So the scanout address, stride and size match the ADT's `0xe3940000` / 4464 /
1116x2484 exactly, only VIG0 feeds LM0, DSC is active, and the panel runs in DSI
command mode, where the panel retains its image and the DPU pushes a frame only when a
transfer is triggered (this is my reading of the zero timing registers and the
mainline code, not a measurement of triggers). Not established: whether frames are
still being pushed during XNU boot (one `FRAME_COUNT` sample only), which register
the bootloader uses to trigger them, and the panel's own timing/init data. The panel
description is not in the stock DTB, `research/fp6-dtb`, or upstream Linux 7.1.2
(no FP6 display nodes there); downstream panel overlays normally ship in the DTBO
partition, which we do not have locally. Level 3 (planned): repeat `FRAME_COUNT` /
`LINE_COUNT` reads over about two seconds and read the pingpong (TE) block.

## FP6 display snapshot level 1 measured 0208 (2026-10-23)

**Phone measured:** CI `39977919581` (head `d7ca0e9f96efe188af24f6f8c50853e7ade92b22`)
passed; source matched. Image
`/tmp/ios-extra-run-39977919581/package1/fp6-dpusnap1-0208.img` (SHA256
`d0dca06934f568b95efe600e430ac381c5d4189ffa854ee50dc409848c1ea42a`; cmdline
`... fp6usb=2 fp6dpusnap=1`) booted once via `fastboot boot`; no flash, EDL or
`getvar`. 92 packets; log `/tmp/ios-extra-run-39977919581/logs/phone-0208-dpusnap1.txt`.

Level 1 returned: `disp_cc_mdss_core_gdsc GDSCR=0xf822f800` (PWR_ON=1,
SW_COLLAPSE=0) and `MDSS HW_VERSION=0xa0020000`. So the bootloader's display power
domain is still on at this point of the boot and HLOS can read the MDP block
without a hang or fault; `0xa0020000` is DPU 10.2.0 by the usual Qualcomm field
layout (major `[31:28]`, minor `[27:16]`). The printed lines were joined by a literal
`\n` (my string escaping error); patch 0209 fixes that. Level 2 (CTL0, LM0, four
SSPPs, INTF_1) is packaged at
`/tmp/ios-extra-run-39977919581/package2/fp6-dpusnap2-0208.img` (SHA256
`d5942cdf9c16b7621440a0f2379fc2fa82d63823d5f661378bab3e1cb88e8ed0`) but is not run
yet; it will be rebuilt with 0209 first so its output is readable.

## FP6 display stage 2: read-only DPU snapshot, candidate 0208 (2026-10-23)

Source/host only; no phone result. The stock FP6 DT (`mdss_mdp@ae00000`, reg
`0xae00000/0x84000`) gives the block map: CTL0 `+0x16000`, LM0 `+0x45000`
(`display-pref primary`), SSPP VIG0 `+0x5000` and DMA0..2 `+0x25000/27000/29000`,
INTF `+0x35000..0x38000` (type list `dp, dsi, none, dp`, so the panel is INTF_1 at
`+0x36000`), pingpong `+0x6a000`, DSI ctrl `0xae94000` (v2.8), DSI PHY `0xae95500`
(v5.2), dispcc `0xaf00000`, `disp_cc_mdss_core_gdsc` at `0xaf09000`. Register
offsets inside the blocks are taken from mainline Linux `dpu_hw_{ctl,lm,sspp,intf}.c`
(fetched from git.kernel.org), not from a measurement. Patch 0208 adds an opt-in,
write-free probe (`fp6dpusnap=1`: GDSC status + MDSS `HW_VERSION` only; `=2`: also
CTL0, LM0, the four SSPPs and INTF_1) called first from `fp6_smmu_inventory()`. It
reads the GDSC first and does not map the MDP block if PWR_ON is clear, because a
read of an unpowered or unclocked block can hang the bus and lose the whole boot log
(as the framebuffer readback did in 0206). Host tests (including a no-write and a
GDSC-before-MDP ordering assertion) and the arm64 compile pass. Planned: boot level 1
first, then level 2, from the same CI kernel. Whether HLOS may read these blocks at
all (the DT mentions a trusted-VM display) is unmeasured.

## FP6 display stage 1 without the CPU readback 0207 (2026-10-23)

**Phone measured:** CI `39975616055` (head `aeb8e8dbcb006699c0c1dfea21e65501562e003b`)
passed; source matched. Image
`/tmp/ios-extra-run-39975616055/package/fp6-scanout-noread-0207.img` (SHA256
`c57c14d4ad66a65836222a431680e96191c65ee88b7a206024a87af29e6fc121`; same cmdline as
0206, `fp6gpuscanoutread` unset) booted once via `fastboot boot`; no flash, EDL or
`getvar`. 106 packets; log
`/tmp/ios-extra-run-39975616055/logs/phone-0207-noread.txt`. The USB log came back
and the phone answered ping.

`buf_init` passed (8/8). The `screen` capture (two IBs, 4092 + 3919 dwords) mapped
312 anonymous pages plus the 2708-page scanout BO onto the real framebuffer
(`0xe3940000`, geometry verified from `PE_current_console`; 15 tables in total) and
completed: fence `0x600dcafe`, RPTR 889/889, CB0 FSR `0x400` (no fault), GPU idle,
`check=1/1`. The `draw` capture then also passed (512 pixels in each result image).
`all 3 captures passed`; CM3 reset verified. The only difference from the 0206 run,
which lost its whole log and reset the phone after the picture appeared, is the CPU
readback of the framebuffer through a second `ml_io_map`; removing it restored
normal operation, which supports (does not isolate) that readback as the cause.
Panel observations are the user's and are not recorded here. Not measured: the
rendered pixel values in the framebuffer, how long the picture persists, and any
behaviour after the probe returns.

## FP6 display stage 1: triangle appeared on the panel 0206 (2026-10-23)

**Phone observed (user report) and measured:** CI `39973842648` (head
`860a1a91d07c2d36c2b1a686950f2e21d85c72cb`) passed; source and header matched. Image
`/tmp/ios-extra-run-39973842648/package/fp6-scanout-0206.img` (SHA256
`092b98d2e0d6567b30355d0039843ce4244ebd20e08c0da1a8b8b437f9cd785a`; cmdline adds
`fp6gpureplay=1 fp6gpureplaycb=1 fp6gpuscanout=1`) booted once via `fastboot boot`;
no flash, EDL or `getvar`. The user reported that the triangle displayed on the
panel and then the screen went back. The helper reported `phone answers ping:
False`, captured no USB log, and the phone was in fastboot again afterwards
(`/tmp/ios-extra-run-39973842648/logs/phone-0206-scanout-fastboot.txt` has only the
fastboot transcript).

So: the GPU's copy wrote into the scanout framebuffer through the TTBR0 address
space (visible evidence from the user, not a software measurement), and the boot
then reset before USB logging started. The probe's log is cached and only replayed
after the probe returns, so any crash inside the probe loses the whole log; the
cause is not measured. Hypothesis: the CPU readback, which `ml_io_map`s the
framebuffer's physical range a second time (probably already mapped by the kernel)
and is the only new CPU-side operation after the draw. Patch 0207 makes that
readback opt-in (`fp6gpuscanoutread=1`); by default the verdict is the GPU fence,
an idle GPU and the picture on the panel. Host tests and arm64 compile pass; CI and
phone pending. Not established: whether the reset came from the readback at all
(other candidates: a fault or watchdog after the GPU wrote the framebuffer), how
long the picture stays, and the pixel values.

## FP6 display stage 1: GPU copy into the scanout framebuffer, candidate 0206 (2026-10-23)

Source/host only; no phone result yet. The ADT's `sweet-fbcon` node and upstream
FP6 DTS give the bootloader's simple-framebuffer: `0xe3940000`, 1116x2484, stride
4464, 32 bpp; the kernel's own display code treats it as BGRA (`0xAARRGGBB`
words). Patch 0206 replays a Mesa Turnip A810 capture whose copy target is a
buffer with `bufferRowLength = 1116`: a 512x512 B8G8R8A8 triangle copied to
screen pixel (302, 986) of an 1116x2484 buffer (`tools/fp6-vk-draw.c` screen
mode, captured with `TU_GMEM=622592 TU_DEBUG=sysmem,noubwc`; two command streams,
4092 and 3919 dwords; 312 anonymous pages plus an 11 MB zero scanout BO). The
generator (`tools/fp6-gen-replay.py`, `scanout=FBW,FBH,X,Y,SIZE`) omits the
scanout BO's pages; the kernel maps the real framebuffer pages at that BO's VA in
the TTBR0 address space (after verifying base, size and stride from
`PE_current_console`), submits both IBs, then reads the screen region back through
an uncached mapping and counts triangle-coloured words (expect ~32768) with a
64x64 sampled preview. Opt-in: `fp6gpureplay=1 fp6gpuscanout=1 fp6gpureplaycb=1`.
Host tests and arm64 compile pass; CI and phone pending. Whether the display keeps
scanning that memory unchanged after the bootloader handoff is unmeasured.

## FP6 triangle rendered and read back 0205 (2026-10-23)

**Phone measured:** CI `39966763160` (head `19190d4d7380858b22cb468a60d9e2723bc3c29d`)
passed; source matched. Image
`/tmp/ios-extra-run-39966763160/package/fp6-replay-ascii-0205.img` (SHA256
`dc35f682e630f6af9f9b33a5c6fc329538653d44a305b5a0c4a7c1fa16c0e378`; cmdline
`fp6gpuring=1 fp6gpucompute=1 fp6gpureplay=1 fp6gpureplaycb=1`, stepping off)
booted once via `fastboot boot`; no flash, EDL or `getvar`. 100 packets; log
`/tmp/ios-extra-run-39966763160/logs/phone-0205-ascii.txt`.

The full Mesa Turnip A810 draw (CBD cleared) ran as one submission and the probe
reported `all 2 captures passed` (`buf_init` 8/8; draw `check=1/1`, fence
`0x600dcafe`, RPTR 885/885, CB0 FSR `0x400`). The two 16 KiB result images were
printed as 64x64 rows and rebuilt on the host: the linear copy
(`0x10002a000`, vkCmdCopyImageToBuffer target) is a clean triangle (512 pixels of
`0xff4080ff`, base up, apex down as Vulkan's top-left origin predicts, rows 16-46)
on a fully written opaque-black clear background (3584 non-zero pixels), so
clear, draw and blit all produced the expected values. The render target BO
(`0x100026000`) holds the same pixel counts in the GPU's tiled layout (rows
interleaved), so its row-by-row print is scrambled as expected. Rebuilt image:
scratch only (not committed). Still unmeasured: GMEM (tiled-binning) rendering
and the fake 608 KiB GMEM CCU offsets on the 576 KiB part, UBWC, textures,
UBO/constants, depth, blending, multiple draws, the original CBD-set stream (still
hangs BR), the Linux kernel's own submit-time CB patching, display, and Metal.

## FP6 first GPU draw: Turnip A810 triangle replay 0204 (2026-10-23)

**Phone measured:** CI `39965021309` (head `02caa494caaf21df497f7488b12c46177912cf2f`)
passed; source and header matched. Image
`/tmp/ios-extra-run-39965021309/package/fp6-replay-nocbd-0204.img` (SHA256
`3961c59a68ccc15887488691835e8bcf835b17a11bedeba0f3fa059a2309c61f`; cmdline adds
`fp6gpureplaystep=1 fp6gpureplaycb=1`) booted once via `fastboot boot`; no flash,
EDL or `getvar`. 107 packets; log
`/tmp/ios-extra-run-39965021309/logs/phone-0204-nocbd.txt`.

With `CONCURRENT_BIN_DISABLE` cleared in the stream's three `CP_THREAD_CONTROL`
packets (patching what Turnip itself patches at submit time), all 121 packet
prefixes of the Mesa Turnip A810 draw (offscreen 64x64 RGBA8 triangle, sysmem,
no UBWC, fake 608 KiB GMEM) completed: fence `0x600dcafe`, BR and BV read
pointers equal to the target, `RBBM_STATUS=0x00000001` (idle), CB0 FSR `0x400`
(no fault), final RPTR 3885/3885. CBD set on this part is therefore what stalled
the BR thread at the following barrier (set: stall at prefix 64, cleared: no
stall anywhere). The result buffers hold 1024 words of exactly `0xff4080ff` (the
fragment colour): 512 in each of two 16 KiB buffers (`0x100026000` image BO and
`0x10002a000`, the vkCmdCopyImageToBuffer target), which equals the triangle's
area (32x32/2). The run still printed "check=0/1" because my own threshold
(300..700 total) counted both buffers; that is a test defect, not a GPU result.
Not yet inspected: the pixel layout (shape), whether it is correct beyond the
count, UBWC, GMEM-mode rendering, CCU offsets beyond the 576 KiB part, and
anything with the original (CBD-set) stream, which still hangs. Patch 0205 counts
per 16 KiB image, passes on one holding 480..544 and prints each image as 64x64
ASCII in the log; host tests and arm64 compile pass, CI and phone pending.

## FP6 draw stall is CONCURRENT_BIN_DISABLE, footer ruled out 0203 (2026-10-23)

**Phone measured:** CI `39953899789` (head `007bce94e2fc296d74833001d7fc39fb74826379`)
passed; source matched. Image
`/tmp/ios-extra-run-39953899789/package/fp6-replay-threads-0203.img` (SHA256
`7450bdc1f126203aa36ef517400c092dbcacb72e5e02906b267cf1baaeda871c`) booted once via
`fastboot boot`; no flash, EDL or `getvar`. 95 packets; log
`/tmp/ios-extra-run-39953899789/logs/phone-0203-threads.txt`.

Result identical to 0202: prefixes 1-63 clean, prefix 64 stalls with BR read
pointer 2451, BV 2460, `RBBM_STATUS=0x00880005`. Reordering the footer
(`SYNC|BOTH` before `WAIT_FOR_IDLE`) changed nothing, which refutes the footer
hypothesis: BR stops at ring index 16, the first packet after the IB, with either
footer. Mapping packet offsets shows the draw's `CP_INDIRECT_BUFFER` is far beyond
dword 148, so prefix 64 contains only state setup plus one packet,
`CP_THREAD_CONTROL THREAD=BR | CONCURRENT_BIN_DISABLE` (dwords 146-147). The BR
thread cannot proceed past a following barrier once that bit is set, while BV has
already read to the end of the ring. Source: Turnip patches these packets at submit
time (plain BR when concurrent binning is enabled; the capture is the CB-disabled
variant); the stream has three of them (dwords 147, 173, 196 of the top-level IB).
Patch 0204 adds `fp6gpureplaycb=1` to clear the disable bit in those packets; host
tests and arm64 compile pass, CI and phone pending. Whether this part's BV pipe
supports being skipped by CBD at all is unknown. No triangle yet.

## FP6 draw replay per-step trace 0202 (2026-10-23)

**Phone measured:** CI `39952430135` (head `a964129928a7137f085ae177cf7338a2859a246b`)
passed; source matched. Image
`/tmp/ios-extra-run-39952430135/package/fp6-replay-idle-0202.img` (SHA256
`add16fbc357157528389ed1b73df7affe1491a668c271ad80eff9753e6f326e3`) booted once via
`fastboot boot`; no flash, EDL or `getvar`. 103 packets; log
`/tmp/ios-extra-run-39952430135/logs/phone-0202-idle.txt`.

Draw prefixes 1-63 (up to 146 dwords) all completed cleanly: fence `0x600dcafe`,
BR and BV read pointers both equal to the target, `RBBM_STATUS=0x00000001`
(idle). Prefix 64 (148 dwords, `CP_THREAD_CONTROL THREAD=BR|CONCURRENT_BIN_DISABLE`)
did not: fence fired, BV read pointer reached the target (2460), BR read pointer
stopped 9 dwords short at 2451 (the `CP_WAIT_FOR_IDLE` after the IB), and
`RBBM_STATUS=0x00880005` (CP_BUSY + UNSLICE_BUSY_IGN_AHB) stayed busy. Hypothesis
(not measured): the stall is produced by my footer, which waited for idle before
restoring `SYNC|BOTH`, so this prefix waits while the CP is in BR-only
concurrent-bin-disable mode; Mesa's real stream never waits there. Patch 0203
restores both threads (sync) first and then waits; host tests and arm64 compile
pass, CI and phone pending. The triangle is still not confirmed drawn.

## FP6 draw replay with the Linux submit preamble 0201 (2026-10-23)

**Phone measured:** CI `39950912667` (head `12da2b9f6f7179ea3dd91b78da4cae90fc71f224`)
passed; build-tree source matched. Image
`/tmp/ios-extra-run-39950912667/package/fp6-replay-preamble-0201.img` (SHA256
`8d5d2fe032b562c2079bc62f6b07294a685597feb81bc748d04ba282df9259f1`; stepping on)
booted once via `fastboot boot`; no flash, EDL or `getvar`. 103 packets; log
`/tmp/ios-extra-run-39950912667/logs/phone-0201-preamble.txt`.

`buf_init` through TTBR0 passed again (8/8). Draw prefix 64/121 (148 dwords, the
`THREAD = BR | CONCURRENT_BIN_DISABLE` packet) still reported a stall, but this
time the fence word read `0x600dcafe`: the CP did execute the fence write that
follows the IB, so the preamble changed the behaviour. The stall verdict came
from my criterion requiring `RPTR_BR == WPTR`; RPTR_BR read 2451 against 2460
(9 dwords behind, the position of the wait-for-idle after the IB), and
`RBBM_STATUS` stayed `0x00880005` (CP_BUSY + UNSLICE_BUSY). So after this packet
the fence fires but the GPU never returns to idle and the BR read pointer does
not catch up; whether BV (idle in the IB dump) or a pending sync is responsible is
not established. Patch 0202 judges a step by fence plus (RPTR caught up or
`RBBM_STATUS==1`), accepts an idle GPU as a quiescent ring for the next submit,
and prints a per-step line with BR/BV read pointers and `RBBM_STATUS`. Host tests
and arm64 compile pass; CI and phone pending. The triangle is still not
confirmed drawn.

## FP6 TTBR0 replay validated; draw stall localized 0199 (2026-10-23)

**Phone measured:** CI `39947768204` (head `d5ee1ca5610e509479fbf8efe608621e89fddabd`)
passed; build-tree source matched. Image
`/tmp/ios-extra-run-39947768204/package/fp6-replay-0199.img` (SHA256
`44d1b4f4169c1bc335c5792095ef9c1d1d106a62b5e59c38160305c8ff7c687f`) booted once via
`fastboot boot`; no flash, EDL or `getvar`. 106 packets; log
`/tmp/ios-extra-run-39947768204/logs/phone-0199-replay.txt`.

- **TTBR0 address space works.** The `buf_init` capture replayed with zero
  relocation through a 6-page / 6-table TTBR0 space at Mesa's original IOVAs via
  `CP_INDIRECT_BUFFER`: fence `0x600dcafe`, RPTR 849/849, data `6..13` (8/8), CB0
  FSR `0x400`. First per-context GPU address space on the FP6.
- **Draw replay still stalls, now localized.** The Mesa Turnip A810 draw (sysmem,
  no UBWC, fake GMEM 608 KiB) mapped 56 pages / 10 tables total; submission was
  accepted and CB0 reports no fault, but the fence never fires. Dump after the
  stall: BR pipe IB1 base `0x10002e000`, `rem=0`, `init=343` (the CP fetched the
  whole stream); BV pipe idle (IB1 0). `RBBM_STATUS=0x00880005` decodes
  (a6xx.xml, A8XX layout) as CP_BUSY + UNSLICE_BUSY_IGN_AHB + GPU_BUSY_IGN_AHB;
  no HLSQ/SP/VPC/PC/UCHE/CMP/DCMP slice-unit bit is set. So the shader pipeline is
  not what is busy: the CP is waiting on something (candidates: BV/BR thread
  sync, `CP_WAIT_FOR_ME`, `CP_REG_TEST`, a wait on memory) or a per-pipe
  prerequisite the Linux kernel normally provides. Not yet established.
- Patch 0200 adds `fp6gpureplaystep=1`: replay increasing packet-boundary prefixes
  of the draw stream (121 boundaries) and report the first prefix whose fence does
  not fire, with the IB dump. Host tests and arm64 compile pass; CI and phone
  pending.

## FP6 TTBR0 capture replay, first draw attempt 0198 (2026-10-23)

**Phone measured:** CI `39946365030` (head `79244af8d1ccf75430b80164a3a8bf61a9ec274c`)
passed; build-tree source and header matched. Image
`/tmp/ios-extra-run-39946365030/package/fp6-replay-0198.img` (SHA256
`c281d47fd96911e76e985c2495387888238642de5970f303ebc1a4467c762ba6`; cmdline adds
`fp6gpucompute=1 fp6gpureplay=1`) booted once via `fastboot boot`; no flash, EDL or
`getvar`. 107 packets; log `/tmp/ios-extra-run-39946365030/logs/phone-0198-replay.txt`.

The 0197 batch still passed first (`all 5 kernels passed`). The draw capture
(Mesa Turnip, A810 profile, `TU_GMEM=622592 TU_DEBUG=sysmem,noubwc`: 8 BOs,
343-dword stream with one IB, one draw, one blit) was replayed at its original
IOVAs: a TTBR0 address space of 56 pages / 4 tables built, TTBR0 and TCR
(`0xa0102010`) activated with readback, the ring accepted the submission
(doorbell not dropped, CB0 FSR `0x400`, no translation fault). The CP consumed
7 of 14 dwords (rptr 842/849) and stopped; the fence never fired and the GPU
stayed busy (`0x70880004`). This is a hang inside the draw's indirect buffer, not
a fault. The runner stopped at the first failure and had placed `draw` before
`buf_init`, so the compute replay that validates TTBR0 translation did not run:
TTBR0 translation itself is therefore not yet proven. Patch 0199 runs compute
captures first and dumps per-pipe CP IB1/IB2 position and ROQ occupancy on a
stall; its host tests and arm64 compile pass, CI and phone pending.

Source note: Mesa's A8XX sysmem CCU layout for the A810 profile needs about
608 KiB of GMEM against the 576 KiB part; the capture was made with a larger fake
GMEM size, so those CCU offsets may be what the hardware rejects.

## FP6 batched compute kernels 0197 (2026-10-23)

**Phone measured:** CI `39943744175` (head `e8b9e3d9a055e3fb7df3a14f9ec591934658aaed`)
passed; build-tree source and header matched. Image
`/tmp/ios-extra-run-39943744175/package/fp6-compute-batch-0197.img` (SHA256
`a3ef87861527937a03786d9a0e88a8440df9aa77e45e2824a0b81a1e58f805af`; cmdline adds
`fp6gpuring=1 fp6gpucompute=3`) booted once via `fastboot boot`; no flash, EDL or
`getvar`. 90 packets; log `/tmp/ios-extra-run-39943744175/logs/phone-0197-batch.txt`.

Seven back-to-back submissions through the firmware BR ring, each from a Mesa
A810 computerator capture with its own shader/descriptor/data pages. Every run:
WPTR doorbell not dropped, fence and scratch seqno `1`, RPTR reached WPTR,
CB0 FSR `0x400`, correct result, `all 5 kernels passed`:
- `buf_init` x3 (`+5` each, accumulating): `6..13`, `11..18`, `16..23`.
- `iota1`, 32 lanes: `buf[i]==i`, 32/32.
- `iota4`, same kernel as 4 workgroups: 32/32. All groups write identical
  values, so this shows the 4-group launch completed without fault, not that
  each group ran separately.
- `branch`, predicated control flow: lane 0 `0x87654321`, others `0x12345678`, 16/16.
- `localmem`, shared memory write then read by all lanes: all `5`, 8/8.
CM3 reset verified afterwards. Measured: ring reuse with persistent state across
submissions, multi-lane launch, workgroup count 4, control flow, local memory.
Not measured: graphics draw, constants/UBO, textures, private memory, per-process
address spaces, the CP power-up list, power management between submissions,
concurrent use with GMU scheduling, Metal.

## FP6 first GPU shader execution: compute dispatch 0195 (2026-10-23)

**Phone measured:** CI `39940824622` (head `465ba7a`) passed; build-tree source and
header matched. Image `/tmp/ios-extra-run-39940824622/package/fp6-compute-0195.img`
(SHA256 `056313c9629e9283a5b075c46e751c1929cd888781d54ebfafa09ec8a0a151dd`; cmdline
adds `fp6gpuring=1 fp6gpucompute=1`) booted once via `fastboot boot`; no flash,
EDL or `getvar`. 95 packets; log
`/tmp/ios-extra-run-39940824622/logs/phone-0195-compute.txt`.

With the scratch pointers relocated (0195), the 157-dword stream (Mesa A810
computerator `buf-init.asm`: eight invocations, each reads a word, adds 5, writes
it back) ran through the firmware BR ring. Measured: WPTR doorbell not dropped,
completion fence `0x00000001`, scratch seqno `0x00000001`, RPTR reached WPTR
(175/175), CB0 FSR `0x400` (no fault), GPU idle afterwards, and the data buffer
read back by the CPU changed from `1..8` to `6,7,8,9,10,11,12,13`
(`correct=8/8`). CM3 reset was verified. This is the first measured shader
execution and UAV buffer read/modify/write on the FP6 Adreno 810. It validates
the A8XX compute state Mesa emits for the A810 profile, the A8XX buffer
descriptor encoding, the shim-IOVA relocation scheme, and ring submission.
Not measured: graphics draw, multiple dispatches, resource sync between
submissions, constants/UBOs, textures, per-process address spaces, the CP
power-up list, power management between submissions, Metal.

## FP6 first compute dispatch attempt 0194 (2026-10-23)

**Phone measured:** CI `39939343713` (head `bd17debb316baf898b21426ea57a4c74eab55147`)
passed; build-tree source and header matched. Image
`/tmp/ios-extra-run-39939343713/package/fp6-compute-0194.img` (SHA256
`74f32010e68dafe9fd6f98d279f91264281fa0273221019c95bf1dc1d826545e`; cmdline adds
`fp6gpuring=1 fp6gpucompute=1`) booted once via `fastboot boot`; no flash, EDL
or `getvar`. 92 packets; log `/tmp/ios-extra-run-39939343713/logs/phone-0194-compute.txt`.

The stream is Mesa's own A810 (`FD_GPU_ID=810`, chip `0x44010000`) computerator
dispatch of `buf-init.asm`, captured through the freedreno noop drm-shim
(`FD_RD_DUMP`) and converted by `tools/fp6-gen-compute.py`. The host ring accepted
157 dwords (WPTR fence not dropped) and the CP consumed most of them, but the
dispatch did not complete: the completion fence stayed `0xdeadbeef`, the data
buffer stayed `1..8`, GPU busy stayed set, and CB0 FSR became `0x80000402`
(translation fault) with FAR `0xffffe000`, FSYNR0 `0x00040030` (write,
unprivileged). That is a Mesa shim IOVA the generator had not relocated: the
stream's `CP_EVENT_WRITE7` (dword 134) and `CP_WAIT_REG_MEM` (dword 139) use a
scratch seqno address inside Mesa's pool BO, not a BO base. This is a data
generation defect, not evidence about the shader, descriptor or A810 compute
state. Patch 0195 relocates those pointers; its host tests and arm64 compile
pass, CI and phone pending.

## FP6 host-driven ringbuffer 0192 (2026-10-23)

**Phone measured:** CI `39934932431` (head `2cda1cc7ac04ed88c71e1ab1a2f6d7dbe3b72412`)
passed; build-tree `sweet_gpu.c` matched the tested source. Image
`/tmp/ios-extra-run-39934932431/package/fp6-host-ring-0192.img` (SHA256
`ff89c5fe1e9f104ff42f28e96406db697943dc27bdd65954e967eb179b162771`; cmdline adds
`fp6gpuring=1`) booted once via `fastboot boot`; no flash, EDL or `getvar`.
104 packets; log `/tmp/ios-extra-run-39934932431/logs/phone-0192-host-ring.txt`.

After the proven raw-HFI `CP_MEM_WRITE`, the probe read the live ring registers:
`CP_RB_BASE=0x1ff8000003000` (the first firmware kind-1 allocation, 32 KiB),
`CP_RB_CNTL=0x20c`, `RPTR=WPTR=14`, AHB fence status 0. It appended one
`CP_MEM_WRITE` (value `0x8100f00d`) at WPTR from the CPU, wrote `CP_RB_WPTR_GC`
through the GMU AHB fence (not dropped), and the CP executed it: the CPU read
back `0x8100f00d`, RPTR and WPTR both ended at 18, CB0 FSR `0x400` (no fault),
CM3 reset verified. This shows the hwsched firmware leaves its BR ring usable
by a host writer when idle, as Snapintosh's X2-90 setup does. Not measured:
sustained use alongside GMU scheduling, wrap handling, BV pipe, power-up list,
compute dispatch, draw, Metal.

## FP6 A810 non-context registers 0191 (2026-10-23)

**Phone measured:** CI `39929355300` (head `8b4b68336aa099d7925cd61396586cfc1c9e2127`)
passed; build-tree `sweet_gpu.c` matched the local source. Image
`/tmp/ios-extra-run-39929355300/package/fp6-nonctxt-0191.img` (SHA256
`102468ae02aac20d2bb629ab173c8a5766a0197f673dfca7224dadd9c1712de2`) booted once
via `fastboot boot`; no flash, EDL or `getvar`. 104 packets; log
`/tmp/ios-extra-run-39929355300/logs/phone-0191-nonctxt.txt`.

Patch 0191 writes Linux's `gen8_3_0_nonctxt_regs[]` (37 entries, LPAC omitted;
50 pipe writes for NONE/BR/BV) before SQE start. After it, CP init still leaves
CB0 FSR at `0x400` (no fault), `CP_MEM_WRITE` again read back `0x8100cafe`
(`passed=1`), and CM3 reset was verified. APRIV pipes 6/7 still read
`0xdeafbead`. Not measured: ring/submission, power-up list, compute dispatch,
draw, Metal.

## FP6 first GPU command executed: 0188-0190 (2026-10-23)

**Phone measured:** CI `39927497414` (head `dd2a6fbdeec91894b8ba5a8bc2241f53cfe8ad13`)
passed; the build tree `sweet_gpu.c` matched the local source byte-for-byte.
Image `/tmp/ios-extra-run-39927497414/package/fp6-apriv-uche-0190.img` (SHA256
`947c84fcc8df6d614c7745c3f72113c5bb8c905180fbfa87e08b753a49db714e`, exact CI
kernel/ADT, verified stock DTB, 0187's bounded init and cmdline) was booted once
via `fastboot boot`; no flash, EDL or `getvar`. 94 packets; log
`/tmp/ios-extra-run-39927497414/logs/phone-0190-apriv-uche.txt`.

With APRIV (0188), the HFI GMU_ACC/EXEC flag fix (0189) and the UCHE trap bases
(0190), CB0 FSR is `0x400` (format bit only; no permission fault) after CP init,
`RBBM_STATUS` returns idle, and `CP_MEM_WRITE` wrote `0x8100cafe` which the CPU
read back (`passed=1`). This is the first measured GPU command execution and GPU
write to memory through the GPU SMMU context. APRIV readback matched for pipes 1
and 2; pipes 6 and 7 (DDE) read `0xdeafbead`, so those writes are unverified.
CM3 reset was verified afterwards. Not measured: draw, shaders, ring/submission,
the rest of `gen8_start()`, the CP power-up list, Metal.

## FP6 CP privilege setup 0188 (2026-10-23)

**Phone measured (0187):** image `fp6-sqe-unprivileged-0187.img` (SHA256
`1c7ce78f29c6a5066a99a58ed361a1bc248bf643d4d23a2cf70daa5fb7c3ac4f`), one
temporary boot, 93 packets; log `/tmp/ios-extra-run-0187/logs/phone-0187-sqe-unprivileged.txt`.
HFI START, default votes, OOB ACK and SQE base/start still work. The fault moved
off the SQE: CB0 FSR=`0x80000408`, FAR=`0x1ff8000003000`, FSYNR0=`0x00040003`,
CBFRSYNRA0=0. FAR is HFI kind 1 (flags `0x37b`, 32 KiB), mapped read-only and
privileged-only (PTE `0x903e88e83`). `CP_MEM_WRITE` was again refused; no GPU
write/readback, draw or Metal output.

**Source finding (not a phone result):** Linux `gen8_start()` writes
`CP_APRIV_CNTL_PIPE` (0x84d) per pipe, `0xf` (`0x6f` for BR): ICACHE, ringbuffer
fetch, PM4 memory access and RPTR shadow writes become privileged. HFI `GFX_PRIV`
allocations map as `IOMMU_PRIV`, as XNU does. The probe never programs APRIV, so
the CP reads the privileged ring page unprivileged. Patch 0188 programs BR/BV/
DDE_BR/DDE_BV APRIV via `CP_APERTURE_CNTL_HOST` (0x81c) before the SQE base and
start, logs each readback, restores aperture 0. Host suite passes (5 skipped);
local arm64 compile `0 of 1 files failed`. CI and phone pending.

Known unrelated bug, not yet fixed: raw HFI flags are passed to the global-domain
mapper, where HFI bit 3 (`GMU_ACC`) collides with `GFX_EXEC`, so GMU-visible
allocations are mapped executable. Fix in its own patch.

## FP6 SQE privilege correction 0187 (2026-10-23)

Source review found that Linux `adreno_get_firmware()` allocates SQE firmware
`GPUREADONLY` with the separate `KGSL_MEMDESC_UCODE` attribute. In
`kgsl_iommu.c`, read-only removes write permission and UCODE removes NOEXEC;
`IOMMU_PRIV` is added only for the distinct `KGSL_MEMDESC_PRIVILEGED` bit.
XNU 0185 instead mapped SQE pages with GFX_PRIV, producing privileged-only
leaf PTEs. The 0185 phone log's FSYNR0=`0x00040003` has PNU=0, indicating the
faulting GPU access was unprivileged. This makes the privilege mismatch a
strong, source-backed candidate for the remaining SQE permission fault; it is
not yet a confirmed hardware fix.

Patch 0187 removes GFX_PRIV from SQE leaf mappings while retaining executable
and read-only attributes. The resulting AP bits allow unprivileged read-only
access; ordinary data remains execute-never. The host page-table and GPU probe
tests pass (full suite: 13 passed, 5 skipped). Commit
`65fc38b7a337e14c12135472e87d009823c86448` passed XNU CI run `39921911338`.
The compiled buildtree `sweet_gpu.c` contains the unprivileged SQE mapping.
Automatic image packaging was skipped because `FP6_STOCK_DTB_URL` is unset;
the exact CI kernel and ADT were packaged locally with the verified stock DTB
and bounded init ramdisk. Header-v2 kernel/ADT/DTB/ramdisk round-trip passed.
Image `/tmp/ios-extra-run-0187/package/fp6-sqe-unprivileged-0187.img` has
SHA256 `1c7ce78f29c6a5066a99a58ed361a1bc248bf643d4d23a2cf70daa5fb7c3ac4f`.
Kernel SHA256 is `479972540ecfa7f94c434ed4d593bc46f8393d6ec1fd183f2e400d94f01519b3`,
ADT SHA256 is `f5d9423bc54c42d08f7c4aeb82e8400eb0fd7b0f4e13b134a5f0b85dcfa54d56`,
and stock DTB SHA256 is `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`.
The cmdline enables the 0186 SMMU/GMU diagnostics and the bounded SQE/CP
execution probe. Fastboot checks still return zero devices, so this image has
not been booted and 0187 remains unconfirmed on hardware.

## FP6 SMMU fault attribution snapshot 0186 (2026-10-23)

After the 0185 executable SQE mapping changed the reported access to a data
read but left a permission fault, patch 0186 adds read-only CB0/CB4 snapshots:
CBAR/CBA2R, SCTLR/ACTLR, TTBRs, TCR/TCR2, MAIR, FSR/FAR/FSYNR, and Qualcomm
CBFRSYNRA attribution. It also logs the exact software-walk descriptors and
SQE leaf PTE for the faulting IOVA, plus the live GPU stream route. This should
identify the SID using CBFRSYNRA0 and expose the live CB0 translation state.
ARM SMMUv2 specifies S1CBNDX as unknown for stage-1 translation; this SMMU has
IDR0.NTS clear, so `S1CBNDX=4` is not evidence of CB4 involvement. The CB4
sample is ancillary. Linux Qualcomm SMMU code uses CBFRSYNRA indexed by
context bank in its GPU fault reporting path; source evidence is not a phone
result.

Commit `a0a0f83d6fbc09c4a231f00a27d45d630a76ec4c` passed CI
`39919610871`; the new code also compiled as one file against the 0185 CI
buildtree. The full host suite passed (13 tests, 5 skipped). The temporary
image is `/tmp/ios-extra-run-0186/package/fp6-smmu-fault-context-0186.img`,
SHA256 `bf5bffbaea29aa1a62cbc055b0a450802c1aa65285268870f0621f12400b6420`.
It uses the exact kernel/ADT from that CI run and the verified stock DTB
(SHA256 `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`).
Packaging round-trip passed. Phone validation has not run: the required
pre-boot `fastboot devices` check found zero devices. Next, once the phone is
visible in fastboot, run one temporary boot with user-mode USB capture and
decode CBFRSYNRA0, CB0 state, the active route and SQE PTE. No flash, EDL or
`fastboot getvar` was used.

## FP6 SQE executable-map test 0185 (2026-10-23)

Patch 0185 (`898c5145b9f1123c54d128df57f3cb0b5fa9e692`) passed CI
`39916509697`. The CI kernel/ADT were packaged with the locally verified
stock DTB into `/tmp/ios-extra-run-0185/package/fp6-sqe-executable-0185.img`
(SHA256 `28d4ddd2289a5221bf212f3fe2bda52d35a3a1c0526fb6cb06aa0a4a4b9acea2`).
One temporary boot completed, USB ECM came up, and 92 packets / 24,016 bytes
were captured in `/tmp/ios-extra-run-0185/logs/phone-0185-sqe-executable.udp`;
decoded log: `/tmp/ios-extra-run-0185/logs/phone-0185-sqe-executable.txt`.
The phone answered ping. No partition was flashed.

**Phone measured:** HFI START, default GPU and bus votes, and GPU OOB still
ACK. CP init still faults before `CP_MEM_WRITE` is submitted. CB0 FSR remains
`0x80000408`; FAR is now `0x1ff8000016780`, FSYNR0=`0x00040003`, FSYNR1=`0`.
The SQE mapping starts at `0x1ff800000b000`; the fault offset is `0xbc80`,
inside the 84,560-byte (`0x14a50`) SQE payload. FSYNR0.IND changed from 1 in
0184 to 0, so the new syndrome describes a data access rather than the prior
instruction access. This is a changed fault location/access type after the
executable PTE change, but the permission fault remains; 0185 did not get CP
initialization or GPU execution working. No GPU write/readback, draw, or Metal
output has succeeded. Next, inspect the live CB0 configuration, CBFRSYNRA0,
and exact SQE page descriptors, then compare with Linux's Gen8 SQE memory and
SMMU setup before another phone build.

## FP6 SQE/CP execution attempt 0181 and pagewise fix 0182 (2026-10-23)

Patch 0180 validates pinned `gen80300_sqe.fw` (84,564 bytes, version
`0x01100067`, SHA256
`38fd00147e8b752dd29c53a0badac8f94b1dbd89dc06f5b1c372d3428cd1b906`) and
stages its 84,560-byte instruction payload without committing firmware.
Patch 0181 is opt-in with `fp6gpuexec=1`; it tries to map SQE firmware, a CP
power-up-list placeholder and a writable result page through the active
SID0/CB0 TTBR1 domain, then start SQE, send Gen8 CP init and issue `CP_MEM_WRITE`.
The raw HFI commands have Linux's 200 ms GPU-busy bound, and reset containment
and permanent backing retention remain active on success or failure. The
diagnostic leaves CP_ME_INIT's optional power-up-list bit 8 clear. It does not
port Linux's `gen8_start()` register setup, spinlock register list, draw path or
Metal integration.

Commit `ce2dfe3b0fd0b9a0ad309427d64cdac0d4e18e7b` passed CI run
`39908276809`; kernel SHA256
`226c25ee611eeaf514900d13a5c044e2175f31824f7d21ea640a8c1549582c33`. The
buildtree's `sweet_gpu.c` matched the locally compiled source SHA256
`5b9b152a3e42f240219abcc0680df9de40ccd359b36058b6d5c2d684db40316f`; the
staged SQE header matched the local generated header SHA256
`a042cff1cd82853b6d0274a49241e4862fb1764d3dad458db91bcc4853aff2b7`.
Packaged image
`/tmp/ios-extra-run-0181/package/fp6-sqe-cp-write-0181.img` SHA256
`eff80b5fb9aebead340ab1ce243e279b2a66352467926b800b7d26e098e52b96` used
the exact CI kernel/ADT and verified local stock DTB.

One temporary boot reached the already measured HFI `START`, both default
votes, and GPU OOB ACK (`GMU2HOST_INTR_INFO=0x80000000`, `RBBM_STATUS=1`). The
first new operation stopped at `permanent GPU buffer mapping failed`, before
SQE base writes or any HFI raw CP command. CM3 reset was verified; SID/context/
clock votes were retained. The log and raw UDP are
`/tmp/ios-extra-run-0181/logs/phone-0181-sqe-cp-write.txt` and `.udp`, both
SHA256 `15be18ebde1ef4248be7497c6290be0b5cbc406ffd208815c024b6fb9f872758`.
0181 combined VA reservation, backing allocation and SMMU map failures into
one log, so the exact failing substep is unknown. No GPU command or memory
write/readback is claimed.

Patch 0182 changes SQE backing to separate 4 KiB physical pages mapped in one
contiguous GPU VA and adds per-stage failure messages. This matches Linux's
scatter-backed global buffer mapping model and removes the large contiguous
physical allocation requirement. Commit `e853a696e99ae2aef0eee8e7f63f9c7561df8b9d`
passed CI `39909842939`; kernel SHA256
`a8af5f0241d26a4d8c93e6a02022e21d843940b76a7ec0cc5135c60df78b3da9`, ADT
SHA256 `542293f42c875f31ef866b1635b64df1ff2d65b21f23b4bbea464b2f2cf27846`,
and build-tree `sweet_gpu.c` matches `/tmp/sweet_gpu-0182.c` byte-for-byte.
The generated SQE header SHA256 is
`a042cff1cd82853b6d0274a49241e4862fb1764d3dad458db91bcc4853aff2b7`.
Image `/tmp/ios-extra-run-0182/package/fp6-sqe-cp-write-0182.img` SHA256
`623ba7fbbd0a3b75a1edb178e605335dcc8393207b0d24d768abd7f2f5e774ef` used the
matching stock DTB and bounded RAM-disk init.

One temporary boot reached the GMU/HFI startup and default votes, ACKed GPU
OOB, mapped SQE from pagewise backing and programmed its base. The HFI raw
`CP_THREAD_CONTROL + CP_ME_INIT` request returned the GPU idle indication
(`busy=0x71000000`, `RBBM_STATUS=1`). Before submitting `CP_MEM_WRITE`, the
next idle check stayed busy for 200 ms (`GPU_CX_BUSY_STATUS=0x70880004`), so
the write was correctly refused and no memory write/readback is claimed. The
probe verified CM3 reset and retained SID/context/clock votes. Decoded and raw
USB logs are `/tmp/ios-extra-run-0182/logs/phone-0182-sqe-cp-write.txt` and
`.udp`, both SHA256
`118e212a7a801d9f56913d17cc4abc98f9175933653bf3c1111f17fd8c0f5369`;
capture was 96 packets / 23,832 bytes. The pagewise fix therefore resolved the
0181 mapping failure. The 0182 trace does not include busy-status2 or CP fault
registers, so it does not identify why busy reasserted after CP init.

Patch 0183 commit `15b75bdfe45710da442bd730e7b0542b641a5e74` passed CI
`39912182367`; the buildtree `sweet_gpu.c` matches `/tmp/sweet_gpu-0183.c`
byte-for-byte. Kernel SHA256
`6f2d7d16406f3976a7b20059359bbc3eede74c0ccc5a7501954439effcdf0b5d` and image
`/tmp/ios-extra-run-0183/package/fp6-cp-fault-snapshot-0183.img` SHA256
`faaea5347ec50ffb16e518597380df23cd88701e95acd9505488c09f38e100a2`.

The phone booted once; USB capture received 103 packets / 24,434 bytes. Decoded
log and raw UDP are `/tmp/ios-extra-run-0183/logs/phone-0183-cp-fault-snapshot.txt`
and `.udp`, both SHA256
`78a2eed857220873bbe0e2dc42bbe3b320bea3589839522fc343ee2c7f00eb9d`.
Measured CB0 FSR was `0x400` after GMU firmware init, then `0x408` immediately
after `CP_THREAD_CONTROL + CP_ME_INIT`. At that same post-CP snapshot,
GPU_CX_BUSY_STATUS=`0x70880004`, BUSY_STATUS2=`0x12`, mask=`0`, RBBM=`0x00880005`,
RBBM_INT0/CP_GLOBAL/CP2GMU=`0`, SQE status=`0xdeafbead`. The entire status
tuple was unchanged after the no-ZAP secure-trust write. This localizes the
new CB0 fault to CP init and rules out the trust write as its trigger; the
current log lacks FAR and FSYNR, so the faulting IOVA and access syndrome are
not yet known. The CP memory write remains correctly refused.

Patch 0184 adds read-only CB0 FAR and FSYNR0/1. Commit
`188b92b8eda565f302b0553409b58ecdfcf69b45` passed CI `39913744029`; one
temporary boot captured 105 packets / 24,517 bytes. Kernel SHA256 is
`aff25e0f5b3c36fd32ea0ecc6aa4f7a533f2ef6b98895dd50b9c3539a0b37225`; the
packaged image `/tmp/ios-extra-run-0184/package/fp6-cb0-far-fsynr-0184.img`
has SHA256 `61eb5e87f618ea9ca789bb02b27d3bb4eef34c1f44288f28c3a3f531d23ba3d3`.
The decoded log and raw UDP are
`/tmp/ios-extra-run-0184/logs/phone-0184-cb0-far-fsynr.txt` and `.udp`, both
SHA256 `ce5f173e16d833fd35639d676bf6ba676a3cbd00af45520077f09902166a8ccf`.

Phone measurement: after CP init, CB0 FSR=`0x408`, FAR=`0x1ff800000b000`
(the first SQE instruction page), FSYNR0=`0x00040043`, FSYNR1=`0`, and the
busy/CP status tuple matches 0183. Linux ARM SMMUv2 field definitions decode
FSR `0x408` as UUT (bit 8) plus PF (bit 3); FSYNR0 has PLVL=3, WNR=0 (read),
IND=1, and S1CBNDX=4. This is evidence of a faulting read at the expected SQE
IOVA, despite the CPU page-table walk and software mapping checks. ARM SMMUv2
specifies S1CBNDX as unknown for stage-1 translation; this SMMU reports
IDR0.NTS=0, so the value `4` does not indicate CB4. CBFRSYNRA0 is needed to
confirm the faulting SID. No
`CP_MEM_WRITE` was submitted, and there is no GPU write/readback or draw result.

Source comparison changes the leading diagnosis: ARM defines FSYNR0.IND as
instruction rather than data, and Linux defines FSR bit 3 as PF (permission
fault). The global GPU PTE helper currently sets both PXN and UXN on every
mapping, including SQE firmware; the other GPU data allocations should remain
execute-never. Patch 0185 adds an explicit executable permission and applies it
only to SQE pages. Its host TTBR1 test verifies SQE XN bits clear and data XN
bits stay set; the full 13-test suite (5 skipped), GPU-probe ASan/UBSan test,
and local arm64 compile against the 0184 CI buildtree pass. CI and phone
validation are pending. This is a source-supported fix hypothesis, not yet a
device-confirmed resolution. If the next phone log still faults, use
CBFRSYNRA0, live CB0 registers and the SQE walk descriptors to confirm the SID,
effective translation context and leaf permissions before further startup
changes.

## FP6 GMU OOB ACK result 0179 (2026-10-23)

Source audit found that Linux `gen8_hwsched_hfi_start()` sends HFI `START`,
then `gen8_hwsched_setup_default_votes()` before returning to the GPU OOB path.
That helper sends two blocking `GX_BW_PERF_VOTE` messages: the default GPU
performance level and the default bus vote. XNU previously went from the
acknowledged `START` directly to GPU OOB, omitting both. FP6 stock DT selects
GPU pwrlevel 8 (`362 MHz`) and bus level 2. Patch 0179 added the separate
ACK-checked HFI votes matching those defaults.

Commit `1d0bfe045e105e8ffe753d43d9f322cd7f1a6941` passed CI run
`39904438450`. The exact CI kernel, ADT and matching local stock DTB were
packaged with the workflow static init as
`/tmp/ios-extra-run-39904438450/package/fp6-gmu-default-votes-0179.img`
(SHA256 `36d4d2150fa3d4e92ce0642d4d86cf3033ca28e3f7bb237d9f26cac353b1bee9`).
One temporary `fastboot boot` completed successfully; user-mode USB capture
produced the decoded log and raw UDP at
`/tmp/ios-extra-run-39904438450/logs/phone-0179-gmu-default-votes.txt` and
`.udp` (SHA256 `be7282865691c6363f5bea82c8dfca2336006ed856c836b401b9afe86468f3fa`).
No flash or EDL was used.

**Phone measured:** firmware init and HFI setup succeeded; HFI `START` was
ACKed at sequence 7. The default GPU vote (pwrlevel 8, perf index 2) and bus
vote (level 2, AB invalid) were each ACKed at sequences 13 and 14. GPU OOB
then ACKed: `GMU2HOST_INTR_INFO=0x80000000`; the read-only `RBBM_STATUS` was
`0x00000001`. This is the first measured completion of the GPU OOB request and
first GPU status-register read in this sequence. The probe requested OOB clear,
submitted no GPU command, then verified CM3 reset while retaining SID/context/
clock votes. Thus GMU/HFI startup and requested GX power-up now cross the OOB
boundary; GPU command execution, GPU-master DMA/write-readback, draw/readback
and Metal remain unmeasured.

Independent source reading also found a GMU clock timing difference to resolve:
stock DT lists GMU 350/650 MHz; Linux starts first boot at `freqs[1]` (650 MHz)
and changes to `freqs[0]` (350 MHz) after HFI start. XNU currently selects
350 MHz before firmware release. This is not changed by 0179 and is not yet
established as the OOB cause. Keep it as the next source/measurement question.

## FP6 GMU OOB latest measured result 0178 (2026-10-23)

Superseded by the 0179 phone result above.

- Patch 0178 commit `7b13c1483a57d39abb63db3df9eb5b678635589d` passed CI
  `39901607539`. CI kernel SHA256 is
  `31a576142f70b0c10257a80b411fc8bfc8b2ab97dbc8c2753fd7f9cb55d1aabf`; ADT
  SHA256 is `78b5c4022739f417881702d761b43bf2ca8ec10ebd00fe9584ce01c37b93a583`.
  Buildtree `sweet_gpu.c` matches the locally tested source exactly. Because
  CI's stock-DTB URL is unset, I packaged the exact CI kernel/ADT with verified
  local DTB and the workflow's static init as
  `/tmp/ios-extra-run-39901607539/package-correct/fp6-gmu-hfi-start-before-oob-0178.img`
  (SHA256 `be2f2e9217db28ad2c1c53b70706614351c41dbbd5ced34aee1fe0cdf9e72618`).
- One temporary `fastboot boot` succeeded; user-mode USB capture received 96
  packets and the phone answered ping. No flash or EDL was used. Decoded log
  and raw UDP are
  `/tmp/ios-extra-run-39901607539/logs/phone-0178-hfi-start-before-oob.txt` and
  `.udp`, both SHA256
  `fe5ab3ff3e0ed8634bc4e8d1d7e60cf2113a6db4b60f380bf91f9e599cd10b64`.
- **Phone measured:** HFI `START` (request id 10, sequence 7) was ACKed before
  the GPU OOB request. OOB still timed out: HOST2GMU bit 30 was seen
  transiently, but no GMU2HOST ACK appeared (`intr_seen=0`). HFI debug/message
  queues were empty after processing (`DBGQ ri=0/wi=0`, `MSGQ ri=88/wi=88`),
  firmware remained alive (`FW_INIT_RESULT=0x100`, `FW_BUSY=0`), GX stayed off
  (`GFX_PWR_CLK_STATUS=3`), and CM3 reset was verified. SMMU/context/clock votes
  were retained. No GPU command, DMA, memory write/readback, draw or Metal output.
- 0178 proves that correcting the HFI START/OOB order alone does not fix the
  timeout. The A810 profile does not advertise `ADRENO_GMU_WARMBOOT`, selecting
  coldboot rather than warmboot resume. Its coldboot scratch set/query helpers
  are guarded by `warmboot_enabled` and therefore send no scratch messages for
  A810's default profile. CP init remains required. Patch 0179 measures the
  default votes and OOB ACK. The full command path and SQE firmware hash are in
  `docs/FP6_ADRENO_METAL_AUDIT.md`.

## FP6 HFI response-queue phone result 0176 (2026-10-23)

- Commit `88e255c96f36065c1d059744a6a5b11e53c6b2aa` passed CI run
  `39898354731`; XNU build passed and FP6 image packaging was skipped because
  `FP6_STOCK_DTB_URL` is unset. Kernel SHA256
  `3ba9204c9f2d02697711062740b8f12baa9ec165a3094900d0a48c9c077867ac` and ADT
  SHA256 `e55863175af72b99d82cde7caa6e46ce4ffb92c3712f7fc020aeb235cc89cb05`
  were verified. Buildtree `sweet_gpu.c` SHA256 is
  `7e16380f325cdee99741e6601372cecec2c439cfd26c15cdc82a9b9055bdabe0`.
- Packaged the exact CI kernel and ADT with verified stock DTB (SHA256
  `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`) and
  the previously verified static init ramdisk. Header-v2 round-trip passed.
  Image `/tmp/ios-extra-run-39898354731/package/fp6-gmu-oob-msgq-0176.img`,
  SHA256 `18e79c470afeafb4cbc6bbfd6974dfec6f2ac49fa02095e97a4d908d416ed2e7`.
- One temporary `fastboot boot` completed OKAY; user-mode USB capture got ping
  and 108 packets. No flash or EDL command was used. Decoded log and raw UDP
  `/tmp/ios-extra-run-39898354731/logs/phone-0176-gmu-oob-msgq.txt` and `.udp`
  both SHA256 `cfb5d573b24fd3bea02c25607da69879e333ecc16e4a247b977ba1f1f745a703`.
  Fastboot transcript SHA256 `da89cc18b9003ceb308e31802ca429405957d3a8e8cb79cdab3023246bf83c03`.
- **Phone measured:** HFI startup requests ACKed, but OOB timed out again.
  This time raw HOST2GMU bit 30 was not sampled at all
  (`raw_seen=0`, before/after zero); GMU2HOST ACK stayed zero and GX remained
  off (`GFX_PWR_CLK_STATUS=3`). Both debug queue and response queue were empty;
  response queue indices were `ri=24, wi=24`. Firmware stayed alive at
  `FW_INIT_RESULT=0x100`, `FW_BUSY=0`; CM3 reset was verified with SMMU/context/
  clock votes retained. No GPU command, DMA, write/readback, draw or Metal
  output occurred. Phone returned from this boot and is not in fastboot.

## FP6 GMU OOB transient diagnostics phone result 0175 (2026-10-23)

- Commit `5c2a0e76c418284baddf843aab4b860a79a93e50` passed CI run
  `39896663901`; the CI kernel SHA256 is
  `88dd0aaad89633dcc64f5b00328e435909c4e7a8acb9a50f64552f0b61811cf7`.
  Hosted boot-image packaging skipped because `FP6_STOCK_DTB_URL` is unset.
  Packaged the exact kernel/ADT with the verified stock DTB and bounded
  ramdisk. Image:
  `/tmp/ios-extra-run-39896663901/package/fp6-gmu-oob-diag-0175/fp6-gmu-oob-diag-0175.img`
  (SHA256 `ac38ef2134de3c92c3897ee13973945e2aabefaff1243993500914227b8d8a65`).
- One temporary boot of the correctly flagged image succeeded with user-mode
  USB capture; no flash or EDL was used. Log and raw UDP are
  `/tmp/ios-extra-run-39896663901/logs/phone-0175-gmu-oob-diag.txt` and `.udp`,
  SHA256 `855b983546dccc2589f700d4fc77b3f05d7e39481bd41a18f3939fbdbbc648e7`
  (91 packets). Fastboot transcript SHA256 is
  `b17dd038b86609a8d8b3292dafd33a104def1c4e8ae6d32aad1cccf9856f32da`.
- **Phone measured:** HFI perf/BW tables, feature controls, core-FW start, and
  context-queue query ACKed (`context queues=1`). OOB timed out before HFI
  `START`. During the full 100 ms poll, `raw_seen=0x40000000` proves HOST2GMU
  bit 30 was observed set at least once; it was zero before and after the poll.
  No GMU2HOST ACK was seen (`intr_seen=0`). GX remained off
  (`GFX_PWR_CLK_STATUS=3`), `FW_INIT_RESULT=0x100`, `FW_BUSY=0`; CM3 reset was
  verified, with SMMU/context/clock votes retained. The HFI debug queue was
  empty (`ri=0, wi=0`). CB0 `FSR=0x400` is `FORMAT[1]` in the ARM SMMU register
  definition; the Linux fault mask excludes that format field, so this value
  alone is not evidence of a translation fault. No GPU command, DMA,
  write/readback, draw, or Metal output occurred. The phone is currently in
  fastboot.

## FP6 GMU OOB transient diagnostics candidate 0175 (2026-10-23)

- Patch `0175-fp6-gmu-oob-transient-diagnostics.patch` samples the HOST2GMU
  raw latch and GMU2HOST interrupt state throughout the bounded 100 ms OOB
  poll, then dumps the HFI debug queue on timeout. It established that the
  request bit was seen set while no response/ACK appeared; see result above.

## FP6 Gen8 GPU OOB/HFI ordering phone result 0174 (2026-10-23)

- Commit `ee5ef11c6a7964d5c771b0a50bd651e0860af5bd` passed CI run
  `39894842246` (build and FP6 package-init jobs green; hosted boot-image
  packaging skipped because `FP6_STOCK_DTB_URL` is unset). The CI kernel SHA256
  is `417107e3ae5717680f684e4eec2b9b716458fad579177a971bcdf926f16d3f32`.
  Packaged the exact kernel and ADT with the verified stock DTB and bounded
  ramdisk. The first image omitted opt-in GMU boot arguments, so it only booted
  to init and did not run the GPU probe. Repackaged the same build with the
  proven SMMU/GMU flags; no source rebuild was needed.
- One temporary boot of the correctly flagged image succeeded with user-mode
  USB capture; no flash or EDL was used. The image is
  `/tmp/ios-extra-run-39894842246/package/fp6-oob-hfi-order-0174-gmu/fp6-oob-hfi-order-0174-gmu.img`
  (SHA256 `f7b6d29cf0a73e5be60481b0d415fa9bf48489f2474ca3938e19c8f3a6b5426f`).
  Log and raw UDP are
  `/tmp/ios-extra-run-39894842246/logs/phone-0174-oob-hfi-order-gmu.txt` and
  `.udp`, SHA256 `db8b95e99d8b9914fb0ace6c2d6b06cfe6dee221251bc7a37c964c4d7b876b3f`
  (105 packets).
- **Phone measured:** SMMU table walk passed; DDR BCM vote, HFI perf/BW tables,
  feature controls, core-FW start, and context-queue query all ACKed
  (`context queues=1`). With GPU OOB moved before HFI `START`, OOB still timed
  out; therefore HFI `START` was not sent. At timeout `intr_info=0`,
  `gfx_pwr_clk=3` (GX off per Linux's Gen8 predicate), `fw_init=0x100`,
  `fw_busy=0`, `CB0_FSR=0x400`, `sGFSR=0`; CM3 reset was verified and
  SMMU/context/clock votes retained. This rules out request ordering alone as
  the fix. No GPU core status, command, DMA, write/readback, draw or Metal
  output was reached. The phone is not currently in fastboot.

## FP6 Gen8 GPU OOB/HFI ordering candidate 0174 (2026-10-23)

- Source comparison found a meaningful ordering mismatch with Fairphone's
  Qualcomm Gen8 Linux path. `gen8_gpu_boot()` starts the GPU MMU, requests GPU
  OOB power, then sends HFI `START`; the current XNU probe sent HFI `START`
  before OOB. Patch `0174-fp6-gmu-oob-before-hfi-start.patch` moves only that
  final HFI request to after a successful OOB ACK and carries the actual HFI
  sequence number forward. It also avoids reading GPU status if the reordered
  HFI `START` fails.
- This candidate was built and tested; see the 0174 phone result above.

## FP6 HFI version correction and OOB diagnostics result 0173 (2026-10-23)

- Patch `0173-fp6-gmu-hfi-version-and-oob-diagnostics.patch` corrects the HFI
  version passed into the startup sequence. The 0172 phone log shows the five
  words at DTCM `+0x3fe0..+0x3ff0` as
  `50010012 ffffffff 50000010 00000000 20070001`; code had passed the fourth
  word (`+0x3fec`, zero), so the HFI minor-version check skipped Linux's
  context-queue capability query. The patch passes the actual version at
  `+0x3ff0`. It also logs HOST2GMU raw OOB before/after the request, GMU
  graphics power/clock and RPMh status, firmware init/busy, CB0 FSR and SMMU
  global fault status if OOB times out.
## FP6 HFI version and OOB diagnostics phone result 0173 (2026-10-23)

- Commit `0a1c0c10779d19ce2d17dd4d6fb442979f841565` passed CI run
  `39891466280`. CI kernel SHA-256:
  `37b2f290b7f6132cc4bb5b8b551bc1c753600966514ef00b0e84273f2a1cfa3e`;
  hosted packaging skipped because `FP6_STOCK_DTB_URL` is unset. The exact
  kernel and matching ADT were packaged with verified stock DTB
  (`8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`) and
  bounded ramdisk. Header-v2 round-trip passed. Image:
  `/tmp/ios-extra-run-39891466280/package/fp6-hfi-version-oob-0173.img/fp6-hfi-version-oob-0173.img`,
  SHA-256 `c962435ac5f920da54c09697e43087468f933f9cc2da70c522c9486d2207166b`.
- One temporary `fastboot boot` succeeded using user-mode USB capture; no flash
  or EDL command was used. Decoded log and raw UDP are
  `/tmp/ios-extra-run-39891466280/logs/phone-0173-hfi-version-oob.txt` and
  `.udp`, SHA-256
  `7104517924257c8a343ce46ac9244519d8ac37e2d351137e14ec9700b2513214` (107
  packets). Fastboot transcript SHA-256 is
  `eddbe5a728b90dcca20c5587705af64d1b47b53c2efcb9f01ac6ff1cb9261340`.
- **Phone measured:** corrected HFI version handling caused the context queue
  capability query; firmware returned `context queues=1`, then ACKed HFI
  `START`. GPU OOB still timed out. HOST2GMU raw info stayed zero before/after,
  `GMU2HOST_INTR_INFO=0`, `GFX_PWR_CLK_STATUS=3`, `RPMH_POWER_STATE=0xf`,
  `FW_INIT_RESULT=0x100`, `FW_BUSY=0`, and SMMU global fault status was zero.
  Linux Gen8's power predicate treats either bit 0 or bit 1 of the graphics
  power/clock status as GX off; this boot did not report GX on. CB0 FSR sampled
  `0x400` during firmware init and `0` at timeout. CM3 reset was verified and
  SMMU/context/clock votes retained. No GPU core read, command, DMA,
  write/readback, draw or Metal output was measured.
- Raw HOST2GMU info was zero at the sampled times before and after the request,
  but these samples cannot rule out a transient latch that firmware consumed.
  `GFX_PWR_CLK_STATUS=3` indicates GX off by Linux's Gen8 predicate. The test
  does not establish whether the request reached the GMU; do not claim GPU
  power-on.

## FP6 GPU power-on OOB probe 0172 (2026-10-23)

- Commit `dc61567a02f8877fb9cbbdc80e9c05cb6cafe1a5` passed XNU CI run
  `39889495686`; the kernel build succeeded. CI skipped hosted image creation
  because `FP6_STOCK_DTB_URL` is unset. Kernel SHA-256:
  `ee915124f4bc00a7180556676677b153909e13490165e0fbf39d903ca0f8e576`.
  Packaged the exact CI kernel and matching ADT with verified stock DTB
  (`8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`) and
  bounded RAM-disk init. Header-v2 kernel/DTB/ramdisk round-trip passed.
  Temporary image `/tmp/ios-extra-run-39889495686/package/fp6-gpu-oob-0172.img`,
  SHA-256 `25dd97d6f506c54b8b26a15a366fde1f8538993718ee039b5b0877bc965c82c6`.
- One bounded `fastboot boot` succeeded and the phone answered ping. No flash or
  EDL command was used. The capture contains 108 UDP packets; decoded log and
  raw UDP are `/tmp/ios-extra-run-39889495686/logs/phone-0172-gpu-oob.txt` and
  `.udp`, both SHA-256
  `19e40ae622f3194c477cd176fcdb587dbba4f390c2ce7c8db88ee4d7b3d6f13b`.
- **Phone measured:** GMU firmware init and HFI init succeeded; HFI `START` was
  ACKed. Patch 0172 then wrote GPU OOB request bit 30 and waited 100 ms.
  `GMU2HOST_INTR_INFO` remained zero; the probe reported timeout before reading
  GPU `RBBM_STATUS`, asserted CM3 reset and verified reset while retaining SMMU,
  context and clock votes. Therefore this test did not confirm GPU-domain
  power-on and produced no GPU register read, command, DMA, memory readback,
  draw or Metal result.
- Linux Gen8.3 sets `gmu_clk` to `GMU_FREQ_MIN` (350 MHz from the FP6 DT table)
  after HFI start and before GPU OOB. XNU’s existing clock setup already holds
  GMU at 350 MHz, so this rate match does not explain the timeout by itself.
  Next diagnostic should capture whether HOST2GMU raw OOB bit 30 latched, the
  post-timeout GMU interrupt/status words, and the GPUCC CX/GX domain status
  before reset. The phone has since left fastboot for this temporary XNU boot;
  check `fastboot devices` before any future boot request.

## FP6 HFI no-preemption probe candidate 0171 (2026-10-23)

- Fairphone Gen8 source review confirms `enable_preemption()` returns without
  sending `HFI_FEATURE_PREEMPTION` when preemption is disabled. In
  `gen8_ringbuffer_init()`, the matching no-preemption branch sets one ring and
  returns before `gen8_preemption_init()`, so it avoids allocating secure CSW
  records. The measured kind-5 `GFX_SECURE` request arrived after XNU enabled
  HFI preemption. This supports testing omission of that request; it does not
  prove the GMU will omit kind 5 or that XNU can yet start a ring.
- Candidate patch `0171-fp6-gmu-no-preemption-probe.patch` adds opt-in boot arg
  `fp6gmunopreempt=1`. It skips only the HFI preemption enable command; default
  A810 behavior is unchanged. Host tests assert the opt-in emits no command and
  the default still sends level-1 preemption data `0xD`. Focused normal and
  ASan/UBSan tests pass, the full suite passes 13 tests with 5 dependency
  skips, and local arm64 compilation reports `0 of 1 files failed`. Commit
  `3d05098ff1095f58ceec2769340f51a315f45f98` passed CI run `39845816435`; the
  XNU build succeeded and hosted image packaging was skipped because
  `FP6_STOCK_DTB_URL` is unset. Kernel SHA-256
  `314f570a70c67b73bff5eca32f867ed7bc05ad87d73baa3090f15bcca7195487`.
  The original `/tmp` image was removed, so it was rebuilt from the retained CI
  kernel/ADT, verified Volcano DTB, and workflow init as
  `/tmp/ios-extra-run-39845816435/repackage/fp6-hfi-no-preempt-0171.img`,
  SHA-256 `bc489958ba715a53ccf4a8c489e3051600de6856ce38c9e89271fe06961a45da`.
  Header-v2 kernel/DTB/ramdisk round-trip passed. Args include
  `fp6gmunopreempt=1` and the established SMMU/GMU boot flags. One temporary
  `fastboot boot` succeeded; no flash or EDL operation was used. The decoded USB
  log is `/tmp/ios-extra-run-39845816435/logs/phone-0171-no-preempt.txt`, SHA-256
  `9a7fedb23c75086fc06e09591bfee4ef95acf09dec6c976e46e42c15e2ee0ccd`; 97 UDP
  packets were captured.
- **Phone measured:** GMU firmware reported `FW_INIT_RESULT=0x100`, HFI
  initialized and ACKed the startup tables/requests and bootstrap DDR vote. With
  preemption omitted, firmware requested GPU allocations kinds 2, 14, 15 and 1,
  plus GMU-only kind 16; it did not request secure kind 5. HFI request 14
  (`CORE_FW_START`) ACKed at sequence 5; request 10 (`START`) ACKed at sequence
  6. The bounded probe then reset CM3 and retained SMMU/context/clock state.
  This resolves the secure-CSW allocation boundary for a non-preempting
  path, but no GPU core boot, SQE execution, DMA write/readback, draw or Metal
  output occurred. The next code step is Gen8.3 GPU core/SQE initialization after
  this HFI boundary, using the Linux sequence and correctly staged SQE payload.
- Linux Gen8.3 source inspection confirms `adreno_get_firmware()` strips the
  first four bytes of `gen80300_sqe.fw`, stages the remainder in a GPU-readable
  allocation, then programs the SQE instruction base and starts SQE before CP
  initialization. The pinned raw artifact is 84,564 bytes, SHA-256
  `38fd00147e8b752dd29c53a0badac8f94b1dbd89dc06f5b1c372d3428cd1b906`, kept in
  `/tmp` only. This is source/artifact evidence; phone execution remains
  unproven.

## FP6 CB0 takeover and HFI allocation boundary 0170 (2026-10-23)

- Commit `54a96ca789ef424bfe2f265e480d76c7a4f206a8` passed XNU CI run
  `39842360411`; XNU build succeeded. CI skipped its hosted boot image because
  `FP6_STOCK_DTB_URL` is unset. Kernel SHA-256:
  `036a0a3e5c7c98d74724266c7d16de4b2b67ed36f54f0b9979b187f4a0594d4e`.
  The matching CI ADT and verified Volcano DTB were locally packaged with the
  workflow's minimal init. Header-v2 round-trip passed. Image:
  `/tmp/ios-extra-run-39842360411/package-correct/fp6-cb0-reinit-0170.img`,
  SHA-256 `678ae82e3565a403f33abfa0b1ba6ae4629325637e918da158e9d087a15f90a8`.
  It uses `rd=md0` and bounded GMU/HFI arguments; no partition was written.
- One temporary `fastboot boot` succeeded. The USB logger captured 113 UDP
  packets at `/tmp/ios-extra-run-39842360411/logs/phone-0170-cb0-reinit.txt`
  and `.udp`; SHA-256 for both is
  `8f4552a25b5c20f67db78e2620c3e9eaf851c07004b5e89d3197cccdeec50216`.
  Fastboot transcript is in the matching `-fastboot.txt`. No flash or EDL
  command was issued. The bounded path verified CM3 reset and retained SMMU
  context/clock votes. The device is still in the temporary XNU boot; do not
  assume it has returned to fastboot.
- **Phone measured:** 0170 found powered CB0 disabled and unrouted, with a
  different residual register image than 0169 (`CBAR=CBA2R=0`,
  `SCTLR=0x2ff54304` with `M=0`, `FSR=0`). It replaced that context, verified
  the programmed TTBR1 setup, enabled SID0 through group 1, and preserved the
  existing group 0 SID5->CB2 route. This is the first successful live CB0/SID0
  configuration on the phone, not proof that the GPU master performed a
  translation.
- Firmware ran (`FW_INIT_RESULT=0x100`), HFI initialized (`HFI_CTRL_STATUS=1`),
  and the phone ACKed the six startup requests plus the bootstrap DDR vote.
  XNU then handled GPU allocation events for kinds 2, 14, 15, four kind-1
  buffers, kind 3 and kind 4, publishing the requested GPU mappings; it also
  mapped a GMU-only kind-16 allocation. The next request was kind 5, flags
  `0x1007`, size 3,670,016 bytes. The driver stopped and reset CM3 because this
  includes `GFX_SECURE`; it did not map ordinary memory into this request.
  No HFI `START` ACK, GPU core boot, DMA result, command/write-readback, draw or
  Metal output was observed.
- **Source check:** Fairphone's `adreno_hfi.h` identifies kind 5 as
  `HFI_MEMKIND_CSW_PRIV_SECURE`. `adreno_gen8_hwsched_hfi.c` sends secure
  allocations to `kgsl_allocate_secure()`. `kgsl_sharedmem.c` uses secure
  allocation and `hyp_assign_table()` to transfer pages from HLOS to
  `VMID_CP_PIXEL`; normal host RAM is not a valid substitute. Gen8 source also
  has a non-preempting, single-ring setup path when the preemption feature is
  disabled. Next, verify whether a bounded single-ring command probe can omit
  preemption without requesting kind 5; otherwise the missing protected-memory
  service is the blocker. Do not clear the secure flag or acknowledge this
  request with non-secure pages.

## FP6 CB0 transition diagnostics 0169 (2026-10-23)

- Added patch `0169-fp6-smmu-cb0-stage-snapshots.patch`. It only reads CB0 and
  stream-group state at three checkpoints: after the CB2 test cleanup, just
  before CM3 release, and after GMU firmware init. The existing refusal log
  remains the endpoint at the first GPU global allocation. This should show
  whether the change is associated with the CB2 test, GMU setup, firmware
  execution, or HFI without writing CB0.
- The modified `sweet_gpu.c` cross-compiles against CI buildtree `39831380821`
  (`0 of 1 files failed`). Patch `git apply --check` passed against that
  buildtree. Commit `8ec6a73e7b2bdf920b52977909a625e81d3d954d` passed full XNU
  CI run `39835047101`; the kernel SHA-256 is
  `6c9a6cedc6998253c9425706e789d02ad88c50664f6f741675467c0d0e62c126`. Binary
  string inspection confirms all three stage labels are in the CI kernel.
- Packaged the CI kernel and ADT with verified Volcano DTB
  (`8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`) and
  the previous bounded RAM-disk init. Header-v2 round-trip passed. Image:
  `/tmp/ios-extra-run-39835047101/package/fp6-cb0-stages-0169.img`, SHA-256
  `4c9ac2171e8603bb7d8b2bb8aa9cd7c1c622467c9e4b6bcfffb94edced84cf89`.
  The CI ADT lacks `/product` artwork; packaging used `--allow-no-product`,
  so this image is for diagnostic kernel output only. One temporary
  `fastboot boot` succeeded (no flash or EDL command); USB ECM answered ping.
  Raw UDP and decoded log are
  `/tmp/ios-extra-run-39835047101/logs/phone-0169-cb0-stages.udp` and
  `/tmp/ios-extra-run-39835047101/logs/phone-0169-cb0-stages.txt`, each SHA-256
  `a466761c1ca5c5f662e77c99473530482419386951163adad7392d821f51f097` (99
  packets). User returned the phone to fastboot after this bounded boot.
- Same-boot snapshots show the powered CB0 image unchanged after the CB2 test,
  before CM3 release, after GMU firmware initialization, and at the first GPU
  allocation refusal: `CBAR=CBA2R=0`, `SCTLR=0x2ff54314` (`M=0`),
  `TCR=0x710e6fcc`, `TCR2=0x00030065`, `TTBR0=0x19b3d3770fc36d7b`,
  `TTBR1=0xdc20c4a9af8db9f4`, `MAIR0=0x069faeaa`, `MAIR1=0x8c99bf1f`, `FSR=0`.
  Pre-CM3 and post-firmware snapshots show group 0 assigned to SID5/CB2 by the
  contained GMU walk; group 1 remains invalid with fault route
  (`SMR=0`, `S2CR=0x00020000`). The GMU did not alter CB0. The first HFI
  allocation still stopped at our all-registers-must-be-zero refusal before
  any CB0 write.
- The same boot reached `FW_INIT_RESULT=0x100`, `HFI_CTRL_STATUS=1`, six
  successful HFI ACKs (GPU perf, DDR/CNOC, configuration and preemption), and
  an acknowledged bootstrap DDR vote. Firmware reset was verified after the
  CB0 refusal; SID/context/clock votes were retained. This validates the
  staged readouts and continues to prove GMU/HFI exchange, not GMU DMA, GPU
  execution or rendering.
- Follow-up patch `0170-fp6-smmu-cb0-disabled-reinit.patch` replaces the blanket
  zero-register test with measured-state guards: CBAR/CBA2R must be zero,
  SCTLR.M clear, FSR clear, CB0 TLB idle, no live route may target CB0, and the
  candidate must be an exactly empty/fault-routed stream group. Only then does
  it replace stale CB0 TTBR/TCR/MAIR values while SID0 remains fault-routed,
  verify context/TLBI state, and install SID0 last. The existing SID5->CB2
  route is preserved. Normal, ASan/UBSan, full host suite, and local arm64
  compile pass; CI and phone validation of 0170 remain pending. This is the
  first planned CB0 write; do not claim GPU DMA until the phone confirms it.

## Powered FP6 SMMU baseline measured (2026-10-23)

- Commit `9eeb38e3657ba8bfd259c240155a97868b4db118` passed CI run
  `39831380821` (conclusion `success`). The build workflow skipped its hosted
  image because `FP6_STOCK_DTB_URL` is unset. The verified kernel SHA-256 is
  `34436f1dd7469a83658ba5d4b1ab4f63cea44510374f4b3e5e26c1bac5b3ae24`.
- Packaged that kernel with its CI ADT, the previously verified Volcano DTB,
  and the bounded RAM-disk init as header-v2 image
  `/tmp/ios-extra-run-39831380821/package/fp6-smmu-powered-baseline-0168.img`
  (SHA-256 `b0ce427af518fd6e76a1cf69c5ea45b834ebde227221eb251993e3b331548b97`).
  The ADT lacks `/product` artwork traits, so packaging used
  `--allow-no-product`; this image is for kernel/SMMU diagnostics, not a full
  SpringBoard validation. The image was unpacked and kernel/DTB/RAM-disk
  round-trip checks passed. Boot args enabled `fp6smmu=2 fp6smmupower=1` and
  deliberately omitted GMU firmware boot.
- One authorized temporary `fastboot boot` succeeded; the phone answered ping.
  USB log `/tmp/ios-extra-run-39831380821/logs/phone-0168-powered-smmu-baseline.txt`
  SHA-256 `85a5ae74b441b77bb051d301ef0ba9e474a1b0f724be6afc6471a6c61e6d0ef7`.
  It recorded `IDR0=0x4c017e18`, `IDR1=0x40000016`, 24 stream groups, 22 CBs,
  4 KiB pages and `CB0 +0x20000`. Immediately after CX/SMMU clock power and
  before the CB2 diagnostic, every stream group was invalid and fault-routed.
  Powered CB0 read `CBAR=0`, `CBA2R=0`, `SCTLR=0x2ff5c314`,
  `TCR=0x7d0e6f8c`, `TCR2=0x00038065`, `TTBR0=0x19b143770fcb6d7b`,
  `TTBR1=0xdc20c8e1af8db9f4`, `MAIR0=0x079fae8a`, `MAIR1=0x8899bf1f`,
  `FSR=0`. `SCTLR.M` is clear, so this is disabled, nonzero state. This shows
  the earlier `0/22` scan was taken before power and cannot establish a clean
  powered bank. Do not zero or overwrite these unexplained CB0 values.
- The CB2 test completed its software page-table walk (`IOVA=0x60000000`
  translated to expected `PA=0x904623000`) and left the tested route/bank
  disabled and reserved. This is not hardware ATOS (`ATOSNS` is set), nor proof
  of GPU DMA. With no GMU boot requested, there is no firmware/HFI result from
  this run. The earlier post-HFI CB0 snapshot (0167) differs in SCTLR/TCR2 and
  TTBR values; they are separate boots, so this does not locate a transition.
- Next useful hardware image should take read-only CB0 snapshots at staged
  boundaries in one GMU/HFI boot: after CB2-test cleanup, immediately before
  CM3 release, and at the first `GFX_ACC` allocation/refusal. That will locate
  when the powered CB0 image changes without touching the bank. This phone has
  now left fastboot and is running the temporary XNU image; no autonomous
  return-to-fastboot path has been established, so do not reboot it unattended.
  No GPU DMA, command execution, draw, or native Metal progress was measured.
- Read-only XNU source inspection explains the missing return path: the SWEET
  platform expert does not override `haltRestart()`. Inherited generic XNU
  handling has no Qualcomm PSCI reset or bootloader-reason operation here.
  After a one-shot fastboot boot, the host cannot use fastboot to reset the
  running phone back into fastboot. Any such mechanism needs a known FP6
  bootloader reason and a separately validated restart implementation.

## FP6 post-CORE_FW_START HFI candidate 0165 (2026-10-22)

- Added the source-matched post-CORE_FW_START exchange: read the measured DTCM
  HFI version and query `HFI_VALUE_CONTEXT_QUEUE` only for minor version >= 3;
  decode Gen8 v5 ACK data from dword 2 and status from dword 3; send preemption
  feature control with Linux A810 profile data `0xD` (level 1, GMEM save,
  skip save/restore); then send the one-dword `H2F_MSG_START`. Fairphone's
  `adreno_gpu_core_gen8_3_0` profile has preemption but not HW_FENCE, LPAC or
  AQE, so those feature controls are not enabled. Existing event dispatch stays
  active while waiting for each ACK and can map MEM_ALLOC requests before reply.
- The A810 firmware HFI version `0x20070001` is measured in the 0159 phone log
  (`/tmp/ios-extra-run-39766804611/logs/phone-0159-gmu-hfi-core-start.txt`), so
  the context-queue query is enabled for this device. The 0165 source candidate
  is exercised by a host HFI queue peer: GET_VALUE returns 1 in the v5 ACK, the
  next request is exactly one dword, and both ACKs are validated. GMU domain,
  GPU global-domain and GPU probe tests pass. `tools/xnu-cc.py` compiles
  `sweet_gpu.c` against CI buildtree `39793471917` (`0 of 1 files failed`).
- Commit `b96b41b2ea432f65a9164f279a7ab5e61cc8b014` passed CI run
  `39814973566`; XNU build and FP6 workflow succeeded. The verified kernel
  SHA-256 is `916d0e406f6425d1681b3522c6e2403ca2b4c16342ac8dbc1355efa5da7891a8`;
  the CI kernel manifest passed. CI skipped image packaging because
  `FP6_STOCK_DTB_URL` is unset. Locally packaged the exact CI kernel and ADT,
  verified stock Volcano DTB, and bounded RAM-disk init with header-v2 round-trip:
  `/tmp/ios-extra-run-39814973566/package/fp6-gmu-hfi-start-0165.img`, SHA-256
  `1f1575412a97639396691ccfbc7898022937818b6bba4f5097d54fe25733de4f`.
  The boot line enables the bounded SMMU/GMU/HFI probe and uses `rd=md0`; it
  does not write a partition. No 0165 phone test exists. `fastboot devices`
  returned zero before packaging. The user then identified and explicitly
  requested flashing the Tegu iOS rootfs from
  `/home/ersa/Dev/ios-extra/research/fp6-rootfs-tegu-20261021/` to the existing
  `userdata` partition. Its sparse SHA-256 matched the recorded
  `a1c6f7da616520841c4d56ac2a147940c5c93a0b4406cb1c9ae6832d64338f7c`; all 16
  fastboot sparse chunks completed `OKAY`. Redacted transcript:
  `/tmp/fastboot-flash-fp6-rootfs-20261022.log`. This overwrote prior userdata.
  One 0165 RAM-disk boot was issued through the bounded USB capture helper.
  Phone log: `/tmp/ios-extra-run-39814973566/logs/phone-0165-gmu-hfi-start-resume.txt`
  (SHA-256 `616da7d037e14403ef9064c347b978b8d7efe9d9df56ce1d89c515358e4f8e50`);
  pcap: `/tmp/ios-extra-run-39814973566/logs/phone-0165-gmu-hfi-start-resume.pcap`
  (SHA-256 `1db0dd86e8c6ba9dff7300c4c8877ce54c94ed16cce3bc3b048ed7e45e7fb43c`).
  The phone log measured `FW_INIT_RESULT=0x100`, `HFI_CTRL_STATUS=1`, and the
  expected `0x20070001` firmware. The first post-start message was
  `id=15 type=1 size=3 hdr=0x0001030f`, matching a TABLE ACK, but the parser only
  accepted generic ID 126 and reset the bounded probe. CM3 reset was verified;
  GPU START and GX remained untested. Follow-up patch 0166 accepts a response
  labeled with the acknowledged request ID while retaining sequence/echo/status
  validation. GPU probe plus ASan/UBSan tests and the GMU bounded-boot test pass
  with that host implementation. It still needs one phone test to verify TABLE
  ACK payload handling and continue the HFI exchange. Commit `af030f8` passed
  CI run `39821513140` (build and FP6 packaging jobs succeeded). The new
  header-v2 image is `/tmp/ios-extra-run-39821513140/package/fp6-gmu-hfi-ack-0166.img`,
  SHA-256 `4d06ee27cd0c25778841923c04c2e61e5aaddb0421cd0e5de794e2cfb2d33ee7`.
  Rootless USB capture uses the existing autoconnecting `fp6-usb-log` profile
  and a bounded unprivileged UDP listener. After fixing the interface rename
  race, the 0166 RAM-disk image was booted once with the user-mode helper; fastboot
  reported success and the phone answered ping. Captured phone log:
  `/tmp/ios-extra-run-39821513140/logs/phone-0166-hfi-request-id-ack-usercap2.txt`,
  SHA-256 `e8b772c189f5815f5cb1c42d95afc49411870ca600956e3355b9688e2886bc91`
  (raw UDP capture has the same hash at `.udp`). All six request-ID ACKs passed:
  GPU perf TABLE, DDR/CNOC TABLE, three configuration requests, and preemption;
  DDR bootstrap vote was acknowledged, firmware remained `FW_INIT_RESULT=0x100`
  and `HFI_CTRL_STATUS=1`. The firmware then requested global GPU memory
  (`kind=2`, handle 2, VA `0x1ff8000000000`, PA `0x903e5c000`). Startup stopped
  because CB0 or the selected fault-routed SID0 group failed the driver's
  cleanliness check. No GPU memory map, DMA, command execution, draw, or Metal
  was verified. Exact HFI lines and host setup are in `docs/GPU_LOG.md`.
  Candidate 0167 was subsequently built and tested; see the current GPU state
  and `docs/GPU_LOG.md` for its CI, image and phone evidence.

## FP6 GPU HFI allocation refusal diagnostics 0167 (2026-10-22)

- Commit `d3945d021d4f4013e8f966dfca41158d125cdae8` passed CI run
  `39827421127`. The kernel SHA-256 is
  `abe30b248c2b311fc83c10838e3bb2a51ae14719bec7b68700f64ccc32694445`.
  Locally packaged the exact CI kernel with matching ADT, the verified stock
  Volcano DTB and bounded RAM-disk init; header-v2 round-trip passed. Image
  `/tmp/ios-extra-run-39827421127/package/fp6-gmu-hfi-diag-0167.img`, SHA-256
  `65452f75f388850b624a1c1904f4676f9b56fa0aa062981500dc081447480b50`.
- One bounded phone boot reached all six HFI ACKs and then received the first
  global allocation (`kind=2`, handle 2, VA `0x1ff8000000000`, PA
  `0x903e5c000`). It refused before changing the GPU SMMU. At refusal, group
  1/24 was fault-routed (`SMR=0`, `S2CR=0x20000`); CB0 read `CBAR=0`,
  `CBA2R=0`, `SCTLR=0x2ff54314`, `TCR=0x7d0e6f8c`, `TCR2=0x10065`,
  `TTBR0=0x11f173774fcb6d7a`, `TTBR1=0xdc20c8a1af8db1f4`, `MAIR0=0x079fae8a`,
  `MAIR1=0x8899bf1f`, `FSR=0`. CM3 reset was verified; no GPU mapping, DMA,
  command execution, draw or Metal was reached. Log:
  `/tmp/ios-extra-run-39827421127/logs/phone-0167-cb0-sid0-diagnostics.txt`
  (SHA-256 `87eee3625cbd8f913153b9e065b025b43a2211fc72a14d0fe200d517ad752b36`).
- Rechecked the packaged DTB itself: `kgsl-smmu@3da0000` has resource
  `0x03da0000/0x40000`. Its measured `IDR1=0x40000016` gives a 4 KiB page
  shift and NUMPAGENDXB=4; Fairphone Linux computes 32 pages before the CB
  window, so CB0 at `+0x20000` is consistent with both the DTB aperture and
  mainline's `arm_smmu_page()` layout. The earlier `0/22` context-bank scan ran
  before the explicit SMMU power-up, so it does not establish that powered
  CB0 is empty. Do not reclassify the odd CB0 values as a bad mapping or write
  through them yet. Next, capture powered CB0 and all stream-group SMR/S2CR
  values before any probe changes them, then compare with this post-HFI state.

## GMU cacheability source check (2026-10-22)

- Read-only Fairphone Gen8.3 source review corrected a possible false alarm in
  the GMU page-table PTE: `HFI_MEMFLAG_GMU_CACHEABLE` selects the GMU `GMU_CACHE`
  IOVA aperture (`0x4000..0x00ffffff`), while `get_attrs()` in
  `adreno_gen8_hwsched_hfi.c` only returns READ plus optional PRIV/WRITE. It
  does not request `IOMMU_CACHE`. Linux `io-pgtable-arm.c` therefore uses
  AttrIndx 0 for both cacheable-window and noncached-window mappings. The XNU
  GMU context's MAIR0 is `0x44` (AttrIndx 0 = Normal Non-cacheable), matching
  the current GMU PTE construction; adding AttrIndx 1 based only on the HFI
  flag would diverge from Linux.
- Added an explicit host assertion that both windows use AttrIndx 0 while the
  cached flag remains associated with the correct GMU IOVA range. This is a
  source-model check, not a phone observation. `fastboot devices` returned
  zero devices during this pass, so the 0164 phone test remains pending.
- The same Linux `gen8_hwsched_hfi_start()` review confirms the current XNU
  sequence ends after `CORE_FW_START` (with event dispatch active). On success,
  Linux next enables the context queue and hardware-fence client, sends
  HW_FENCE control, configures preemption/LPAC/AQE, and sends `START`. XNU does
  not yet implement that post-CORE_FW_START sequence. The 0164 phone log must
  first establish CORE_FW_START ACK and any real MEM_ALLOC descriptors; after
  that, the next implementation is the measured post-start command sequence.
- Linux hardware-fence backing is a separate resource from ordinary kernel
  pages: `adreno_hwsched_register_hw_fence()` obtains a descriptor from
  `msm_hw_fence_register()` and uses its device/CPU addresses; `MEM_ALLOC`
  kind `HW_FENCE` then reuses that descriptor. XNU has no equivalent service,
  and 0164 correctly refuses that kind. Keep the HFI HW_FENCE feature disabled
  until this external memory contract is implemented; context queue startup
  can be investigated independently.

## FP6 GPU HFI global-memory integration candidate (0163/0164, 2026-10-22)

- Patch 0163's GPU global-domain helper now takes an explicit allocation size
  for each table page; its added-file hunk count is corrected. Patch 0164 connects
  HFI `MEM_ALLOC` requests with `GFX_ACC` to permanent 16 KiB-contiguous backing,
  the 20 MiB GPU TTBR1 aperture at `0x0001ff8000000000`, and a 4 KiB S1 map.
  It programs the GPU-reserved CB0 and enables an unused fault-routed SMR group
  for SID0 only after table publication and readback. When firmware also requests
  `GMU_ACC`, the same pages are appended to the existing GMU domain before the
  ACK. Unsupported/secure requests continue to fail closed. Backing and tables
  are retained permanently.
- The context checks now tolerate only the FP6 SMMU's measured readback changes:
  TCR2 TBI0/TBI1 are forced to 1 (`0x38011` reads `0x38071`) and SCTLR.ASIDPNE
  reads as 0 (`0x1167` reads `0x0167`). Other programmed bits remain checked.
  A host MMIO peer exercises the actual context setup and a synthetic
  `GFX_ACC` HFI request through its ACK; it walks the resulting TTBR1 PTE and
  checks the route, dirty-CB0 refusal-before-write, and idempotent setup.
  The standalone page-table tests, GPU probe tests and ASan/UBSan GPU probe tests
  pass. `sweet_gpu.c` cross-compiles to arm64 against CI buildtree
  `39793471917` (`0 of 1 files failed`), and the patch series applies in the host
  harness. This is source/host/compiler evidence only.
- Commit `cacda42725fd0945a6a8df96bf28e27b8d8a2868` passed CI run
  `39807392802`; both the XNU build and FP6 workflow completed successfully.
  CI kernel SHA-256 is
  `34e4835aa437df8ecd101fe0b98aba7b18e5a80094ab71ad860976dec0cc7539` and
  SHA256SUMS passed. CI skipped its image because `FP6_STOCK_DTB_URL` is unset.
  The `xnu-buildtree` artifact download returned HTTP 503 (account egress limit),
  so no extracted CI tree comparison was possible; CI itself built the pushed
  source successfully.
- Locally packaged the verified CI kernel and matching CI ADT with the verified
  stock Volcano DTB, plus the workflow's minimal RAM-disk init. Header-v2
  unpack/round-trip passed. Image
  `/tmp/ios-extra-run-39807392802/package/fp6-gmu-hfi-gfx-0164.img`, SHA-256
  `125860c6c4aa898cb40b5039558d146408d5f5c468fef12c96a979bb6c63b4cc`.
  It boots `rd=md0` with `fp6smmu=2 fp6smmupower=1 fp6gmuload=1 fp6gmuboot=1`
  and USB logging enabled. No partitions are written. `fastboot devices` showed
  no device, so the temporary boot and phone result are pending.
- The phone's next real `MEM_ALLOC` descriptor, GMU acceptance, SID0 route,
  GPU execution and Metal remain unverified. Do not treat the modeled ACK or
  software walk as proof of device DMA.

## FP6 GPU global-memory source audit (2026-10-22)

- Read-only Fairphone SM7635 kernel review confirms GPU SID 0 uses the
  `qcom,adreno-smmu` path with split TTBR0/TTBR1 and QCOM ARM64 LPAE S1.
  Linux reserves CB0/CB1 for GPU SID 0 and starts non-GPU client allocation at
  CB2. The measured SMMU reports 48-bit VA / 36-bit PA. KGSL's global GPU VA
  starts at `0x0001ff8000000000` in a 20 MiB aperture; SMMU mapping
  sign-extends it for TTBR1 and maps system-memory scatterlists.
  Its HFI GPU-access allocation is therefore not satisfied by the current
  32-bit GMU-only domain. The XNU GPU path needs an independent SID 0 TTBR1
  domain, GPU VA/global-buffer mapping and matching cache ownership. Exact
  hardware allocation flags still need to be checked against the phone log.
- Source-only finding recorded in `docs/FP6_ADRENO_METAL_AUDIT.md`. No code
  change, build, or phone observation in this pass; Android remains in use.

## FP6 GMU-only HFI allocation follow-up (0162, 2026-10-22)

- Source-review correction to 0162: GMU S1 PTE permissions now follow the
  Linux Gen8 `get_attrs()` policy. `IOMMU_READ` is always present;
  `GMU_WRITEABLE` controls write permission and `GMU_PRIV` controls privileged
  access. The PTE uses nG, AF, outer-shareable, and the resulting AP bits. Host
  fixtures verify default read-only/unprivileged and explicit privileged/RW
  requests, plus GPU-access refusal. Normal and ASan/UBSan protocol/domain tests
  pass; `test_gpu_probe.py` passes; the changed source compiles against the
  39787950216 CI buildtree (`0 of 1 files failed`). First CI `39792609801`
  stopped before compilation because the edited 0133 patch had a stale
  added-file line count. After correcting it, CI `39793471917` passed the XNU
  build and FP6 workflow. The built kernel SHA-256 is
  `e4dbf5cb1acfd17f19273cf1bdd0baf53f790e88a856bd37127c2a54abcdbd2c`.
  Extracted CI source contains the permission-aware allocator and updated PTE
  logic. No phone result exists. The firmware's actual descriptor is still
  unknown, and the user is testing Android.
- Repackaged that CI kernel with the verified product ADT and stock Volcano
  DTB; header-v2 round-trip passed. Image
  `/tmp/ios-extra-run-39793471917/package/fp6-gmu-hfi-memalloc-permissions.img`,
  SHA-256 `897b67af46ec1b0da14dc927a5a3234ed462abed90be3874500a391093f18e22`.
  The image is not phone-tested.

- Candidate patch 0162 answers non-secure, non-GPU-access `MEM_ALLOC` requests
  using permanent kernel backing and a live append to the GMU SMMU page tables.
  It cleans the published tables, issues context TLBIALL/TLBSYNC, waits for
  completion, then returns the Linux-shaped ACK with host handle, GMU address
  and page-rounded size. GPU-access, secure, hardware-fence, fixed-MMIO and
  unsupported large size-alignment requests still fail closed and reset CM3.
- Host protocol tests simulate kind 2 / flags 0 / 4 KiB / alignment 12: one
  allocation maps at `0x60027000`, the table walk reaches its backing PA, the
  service ACK is sent, and START completes. A GPU-access request is refused
  without a mapping or service reply; CM3 reset is verified by the model.
  Normal and ASan/UBSan harness runs pass. `sweet_gpu.c` compiles to an arm64
  object against CI buildtree `39775328855` (`0 of 1 files failed`). These are
  host/compiler checks only; the phone's actual MEM_ALLOC descriptor and
  firmware acceptance remain unobserved. The user is using Android, so no
  device commands were run.
- Commit `1c0bf94` first failed CI `39786196862`: Apple Clang rejected a C
  declaration immediately after a label. Commit `4a14fe7` moved the response
  array before the label and renamed the shadowing parameter. The retry CI
  `39787950216` passed its XNU build; its automatic package step skipped because
  `FP6_STOCK_DTB_URL` is unset. The kernel SHA-256 is
  `6d35acc9772c0b0cc740d409505016fd23c5267d230a923a830ca15561678934`;
  SHA256SUMS passed. The CI buildtree SHA-256 is
  `d1d4d850193c4b64a1604c5a0dc83997247294222df0ac20e66b4653dc58ebf1`, and
  its `sweet_gpu.c` and GMU-domain header match the locally reviewed candidate.
- Locally packaged with product ADT SHA-256
  `4da4226e6b9ac393ff22b66a304d9172d6be2bfd6d558348a47379c51aab1d80` and stock
  Volcano DTB SHA-256 `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`.
  Header-v2 round-trip passed. Image:
  `/tmp/ios-extra-run-39787950216/package/fp6-gmu-hfi-memalloc-0162.img`,
  SHA-256 `30fc97daccfa67230e2f2bedac463591b2f310e285b9ac0c2d1fbc1730ed502d`.
  It has `fp6gmuload=1 fp6gmuboot=1` arguments and is not phone-tested.
- Next: wait for the user's Android work to finish, then use the permissions
  image above for one bounded phone observation and capture the actual MEM_ALLOC descriptor.
  The synthetic kind-2 request is not evidence that hardware will request or
  accept this mapping. GPU command execution remains unproven.

## FP6 HFI service-message milestone (0161, 2026-10-22)

- Patch 0161 extends the 0160 HFI waiter to dispatch interleaved firmware
  messages. It answers `GMU_CNTR_REGISTER` (ID 110) with Linux's permitted
  zero-offset response, then continues waiting for the command ACK. Generic
  ACK validation now follows Linux's echoed request-header/status comparison.
  It decodes and logs the complete `MEM_ALLOC` descriptor (ID 20), then
  deliberately fails closed and resets CM3: no GPU/GMU page backing or mapping
  exists yet, so the requested addresses cannot safely be fabricated.
- The host protocol peer covers the counter-event/START-ACK sequence and a
  bounded MEM_ALLOC refusal/reset. Normal and ASan/UBSan runs pass. The changed
  `sweet_gpu.c` cross-compiles against CI buildtree `39775328855` with system
  Clang (`0 of 1 files failed`). The focused patch applies in the host suite;
  `git diff --check` is clean. Commit `b5b9faa6f27eeea631586a03bd9ca86e41d9a37f`
  passed CI run `39779962789` (XNU build and FP6 job). Kernel SHA256 is
  `5d09f5406cfcbb1fcf3480ab7aca2f79f98a40ff65465fe7b32d9fa84ead7930`.
  CI image packaging skipped because `FP6_STOCK_DTB_URL` is unset. Locally
  packaged the CI kernel with the verified product ADT
  (`4da4226e6b9ac393ff22b66a304d9172d6be2bfd6d558348a47379c51aab1d80`)
  and stock Volcano DTB
  (`8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`).
  Header-v2 round-trip passed. Image `/tmp/ios-extra-run-39779962789/package/fp6-hfi-service-0161`,
  SHA256 `79944b9033c401f3b2f29869714c2227481d3c4281f6fb90b1f9aec511b50e59`.
  It has not been phone-tested; the user is using Android, and no device
  commands were run.
- The decisive next evidence is a later phone log containing the exact
  `MEM_ALLOC` descriptor, after which the allocation kind, size, address and
  mapping requirements can be matched to the Gen8.3 Linux source before
  implementing any backing. This patch does not complete HFI startup or GPU
  execution.
- Deeper Linux-source review (Fairphone module tree commit
  `54c948d9b30c2ba01835e64c36b68b80692554ac`) clarifies the implementation
  split: GMU-only requests use kernel memory plus a GMU IOVA mapping; requests
  with `GFX_ACC` use GPU global memory, and requests also carrying `GMU_ACC`
  must be imported into the GMU IOVA space. The Gen8 GMU VMA ranges are
  `0x60000000..0x7fffffff` (noncached) and `0xc0000000..0xdfffffff`
  (extended); the cacheable window is `0x4000..0x00ffffff`. XNU's current
  published GMU domain initially had no live-map/TLBI update path and there is
  still no GPU-side global allocator. Patch 0162 adds only the GMU-only kernel
  allocation case. A real phone descriptor is still needed to establish that
  this supported subset matches firmware's request.

## FP6 Gen8.3 HFI-to-GPU source boundary (2026-10-22)

- Source inspection only; no build or phone observation. Fairphone's
  `gen8_hwsched_hfi_start()` continues after `CORE_FW_START` by enabling the
  context queue and hardware-fence client, sending HW_FENCE control, setting
  preemption/LPAC/AQE controls, and then sending `START`. During `START`, the
  GMU may interleave F2H `MEM_ALLOC` and `GMU_CNTR_REGISTER` requests. Linux
  backs/maps `MEM_ALLOC`; it can answer counter-allocation failure with zero
  offsets. XNU patch 0160 currently assumes each queue-1 packet is a final ACK,
  so it cannot complete this event exchange. Its frozen GMU domain also does
  not map arbitrary GPU-accessible allocations. Next implementation must
  service real request types and map their required memory before claiming HFI
  startup. These events need ACKs with their own IDs (20/110) and the event
  header echoed; generic H2F command ACKs use ID 126. Linux's six-dword counter
  reply permits zero offsets and resumes waiting for START.
- After HFI, Linux starts the GPU MMU, acquires GPU OOB, applies `gen8_start()`,
  enables GPU IRQs, installs SQE/AQE instruction bases, and boots the hwsched
  ring. Gen8 `CP_ME_INIT` is a seven-payload packet with a GPU power-up register
  list. A local A642L XNU reference demonstrates the later acceptance shape—
  command-processor memory write/readback followed by 2D clear/readback—but its
  A6xx packet/setup sequence is not transferable as A810 evidence. Details are
  in `docs/FP6_ADRENO_METAL_AUDIT.md`.
- The FP6 0160 CI image remains untested on the phone while the user is using
  Android. No device command was run for this source review.

## FP6 Gen8 HFI prerequisite draft (0160, 2026-10-22)

- Patch 0160 extends the failed 0159 `CORE_FW_START` probe with the Linux Gen8
  HFI performance table, BW vote table, HWSCHED/KPROF controls and bounded
  request/ACK handling. It captures the HFI debug queue on firmware assertion
  and stops after CORE_FW_START, resetting CM3 as before. It does not service
  F2H `MEM_ALLOC` or attempt GPU command execution.
- The table values are checked against the extracted FP6 stock DTS and local
  Fairphone KGSL source: GPU 362 MHz at rail level `0x40`; GMU 350/650 MHz;
  zero ARC entries validated; first three DDR bandwidth rows (shared by DDR7
  and DDR8); and CNOC levels. BCM commands encode both AB/X and IB/Y fields.
  ACV perfmode remains off because its Linux threshold is original DDR index 9,
  beyond this bounded three-level subset. Optional ACD/BCL/CLX/IFPC controls are
  not sent because their runtime enable/data inputs have not been reproduced.
- Host probe test checks five HFI requests, queue sequencing, table fields,
  matching and mismatched ACK sequences, and reset containment; ASan/UBSan
  version passes. `test_gpu_probe.py` passes with a no-op cache-flush stub.
  Single-file XNU cross-compile against CI buildtree `39766804611` reports
  `0 of 1 files failed`.
- Commit `5243eb1f6e8b0590e580fd66e604ea34a5faa0f2` passed CI run
  `39775328855` (XNU build and FP6 boot job). Kernel SHA256
  `ddce0dae8fd220bcd9a238b3500cf5693af4c46bd72ee0d18dd123f1bfca4d14`.
  CI image packaging was skipped because its generated ADT omitted `/product`
  artwork traits; the CI kernel was packaged locally with the previously
  verified product ADT and stock DTB. Image:
  `/tmp/ios-extra-run-39775328855/package/fp6-gmu-hfi-prerequisites/fp6-gmu-hfi-prerequisites.img`,
  SHA256 `f63635017fa022319c4f6c6a6cb29224aec193edea49372eb4dc13ae85c2db8e`.
  Header-v2 payload/kernel/DTB round-trip passed. No phone test has been run;
  the simulated ACK is not evidence of GMU acceptance.
- The original 0159 phone result remains `irq=0x4 fw=0x900`; debug data was not
  captured. The next phone test should establish whether the corrected
  pre-start tables clear that assertion. The phone is currently reserved for
  the user's Android test; do not run a device command during it.

## FP6 first Gen8 HFI command phone result (2026-10-22)

- Patch 0159 adds the Linux Gen8 HFI `CORE_FW_START` queue request after HFI
  controller init. It uses the existing 17-queue hwsched table, writes a
  2-dword request with sequence 1, rings `HOST2GMU_INTR_SET`, waits up to one
  second for the message IRQ, invalidates the cached HFI buffer, and validates
  the returned ACK header, request header, and zero status. Cache ownership is
  returned to the GMU before the doorbell; the CPU does not touch the buffer
  while firmware owns it. An unexpected response fails closed and the existing
  bounded path resets CM3.
- Commit `78ce55ec29dd66de6ffdb93eb5c487436de77303` passed CI
  `39766804611`; XNU build and FP6 boot job passed. Kernel SHA256
  `3f3aa08c6fc98403b768a2887e7703934afdca26d683f229062c30c6f8801aa0`.
  Packaged image
  `/tmp/ios-extra-run-39766804611/package/fp6-gmu-hfi-core-start.img/fp6-gmu-hfi-core-start`,
  SHA256 `d68b056515ffc18677842c0dea5bcc51f1dd4a8f11b069ba9341fa4af29c7b08`.
- One temporary `fastboot boot` captured 101 UDP packets. Decoded log
  `/tmp/ios-extra-run-39766804611/logs/phone-0159-gmu-hfi-core-start.txt`,
  SHA256 `ff9b450dc47e29d15f87cabc192b1862198892b543810de72bf99203412b220c`;
  pcap SHA256 `c828b23c0d2c4be46919d8b00cd9cea3b6bf0b9c9a61a5ce68f5608de6db9008`.
- Phone confirms the `CORE_FW_START` exchange does not succeed. After CM3
  release and `HFI_CTRL_STATUS=1`, the request ends with
  `HFI CORE_FW_START timeout/fault irq=0x4 fw=0x900`; the bounded path verifies
  CM3 reset. Linux defines GMU2HOST bit 2 as DBGQ and FW_INIT_RESULT mask
  `0xe00` as firmware assertion. This is a firmware-side fault, not an ACK
  timeout alone; the debug queue contents were not captured by this patch.
- Linux `gen8_hwsched_hfi_start()` sends warmboot scratch, performance and BW
  tables, optional feature controls and log settings before `CORE_FW_START`.
  Patch 0159 sent CORE_FW_START directly after HFI controller init, so it did
  not reproduce Linux's pre-start sequence. The phone's HFI version is
  `0x20070001` (2.7.1), selecting the `H2F_MSG_TABLE` GPU performance format.
  Linux builds that table from the active GPU pwrlevel bin and live cmd-db
  `gfx.lvl`, `cx.lvl`, and `mx.lvl` ARC data; the BW table uses the selected DDR
  levels and live SH0/MC0/ACV BCM metadata. Next implementation must source and
  validate those exact inputs and capture the GMU debug queue on failure. Do
  not add guessed table values or MEM_ALLOC mappings.
- Linux `adreno_gen8_hwsched_hfi.c` allocates/maps F2H `MEM_ALLOC` requests
  dynamically. The next response must first identify any request the GMU makes;
  XNU must not invent handles or addresses that are absent from the persistent
  domain/SMMU tables. No HFI message has yet been exchanged on the phone.

## FP6 ACV vote and GMU/HFI phone result (2026-10-22)

- Commit `548673a33b397ef80cdbc701cd503903ab63118a` (patch 0158) passed CI
  `39762347940`. The CI kernel SHA256 was verified before local packaging. Image
  `/tmp/ios-extra-run-39762347940/package/fp6-gmu-bootstrap-acv-width.img`,
  SHA256 `0c2e73788e98d3a0bbe768ee54e9f4989e3e88973cb2e82d7438ad76ae3f6c10`.
- One `fastboot boot` succeeded; USB capture yielded 92 packets. Decoded log
  `/tmp/ios-extra-run-39762347940/logs/phone-0158-gmu-bootstrap-acv-width.txt`,
  SHA256 `199a1032353ab16000e60d3424fc72edcc8d99e9941872be251fa66e56791526`;
  pcap SHA256 `50e7f70104ca136dfc74a27e3642c725c7b953cca30328a1dedc9108a42c025a`.
- Hardware accepted the SH0 and MC0 variable votes and fixed ACV vote
  (`addr=0x50068`, width 0). The bounded TCS acknowledged the DDR vote. CM3 was
  released; firmware reported `FW_INIT_RESULT=0x100`, then
  `HFI_CTRL_STATUS=1`. The probe stopped and verified CM3 reset while retaining
  SMMU/context and clock votes. This confirms GMU firmware startup and HFI
  controller initialization. It does not demonstrate HFI message exchange,
  GMU DMA, GPU execution, rendering, or Metal. Optional `GPU_INIT_CX_REGS`
  remains unavailable but nonfatal in this path.
- Next measured milestone: bounded HFI startup message and pre-mapped MEM_ALLOC
  handling with explicit cache ownership, followed by a small GPU memory
  write/readback before rendering or Metal integration.

## FP6 cmd-db ACV metadata diagnosis (2026-10-22)

- Patch 0157 commit `32e325fb8197eac394b91eb9e7f6b140d6a6b9fe` passed CI
  `39760355071`; kernel was locally packaged with verified ADT/Volcano DTB as
  `/tmp/ios-extra-run-39760355071/package/fp6-gmu-cmdb-diagnostic.img`, SHA256
  `bd3a24bce181fcc7c4510ba73a6157d126d15274bfaead9f82bfe8049d822476`.
- One temporary boot captured 95 UDP packets. Decoded log
  `/tmp/ios-extra-run-39760355071/logs/phone-0157-cmdb-diagnostic.txt`, SHA256
  `2eff12f71f275bc4d48dab5fe2d7491312535e0f940dede1fb72436ed76253f1`;
  pcap SHA256 `d6f144827081c75eaf3ce03d4f11e2b7c277c743e857a4847e4476de96c447b2`.
- The dump identifies ACV in BCM slave 5 at address `0x00050068`; aux record is
  valid (`unit=1`, `width=0`, `vcd=12`, length 8). The parser had rejected it
  because it required nonzero width for every BCM. Linux marks ACV `fixed=true`
  and does not use its width. Patch 0158 permits zero width only for fixed
  entries, retains the nonzero-width requirement for SH0/MC0, and updates the
  ASan/UBSan fixture to the observed ACV metadata. CI and phone results are
  recorded above; all three votes were accepted and HFI initialized.

## FP6 Linux cmd-db lookup phone retest (2026-10-22)

- Patch 0156 commit `8c8c00233ce086caf4ef840f02948d8e9520153c` passed CI
  `39758346968`; kernel SHA256
  `72a9a9d0166fd390caf96beeec39d4e08671f3285e18acadbbb58b0229cd5683`.
  The temporary image package used the verified ADT and Volcano DTB, header-v2
  round-trip passed, and SHA256 is
  `1cf437c943cb94edbaaa5e0a0f6e62709f57c2d61bab4f9e3a2e2065c55f97fa`.
- The `fastboot boot` USB capture has 92 packets. Log
  `/tmp/ios-extra-run-39758346968/logs/phone-0156-cmdb-linux-lookup.txt`, SHA256
  `b40b04abf1a055af6b0906434b68b1550f1978b2b6914edbd1f67fc9621a3e84`; pcap
  SHA256 `2d44cac32e7e86131ea4fea5ac735d1b4510278acc1866b6229bc838d237e0e4`.
- Mirroring Linux's ordered name search did not resolve ACV: the log still reports
  missing ACV metadata. CM3 remains held in reset and no TCS vote was issued.
  Candidate patch 0157 adds bounded read-only header summaries and ACV/A-name
  entry/aux diagnostics only when metadata lookup fails; it does not relax the
  guard. Its ASan/UBSan host test checks that missing ACV cannot send a vote.
  Patch 0157 is not built or phone-tested yet.

## FP6 BCM address-ID correction phone result (2026-10-22)

- Patch 0155 commit `8462f999359f501ec523daaf1852693e3f384db6` passed CI run
  `39755620038` (XNU build and FP6 boot job success; CI packaging skipped
  because its stock-DTB URL is unset). Kernel SHA256
  `72a9a9d0166fd390caf96beeec39d4e08671f3285e18acadbbb58b0229cd5683`.
  Locally packaged with the verified product ADT and stock Volcano DTB; header-v2
  round-trip passed. Image:
  `/tmp/ios-extra-run-39755620038/package/fp6-gmu-bcm-address-id.img`, SHA256
  `0d4ff5ab9ee7aef5a1139841bcf6a909ed20d0be7ac73c65b43cf7899bbbf24a`.
- One temporary `fastboot boot` was performed through the USB helper; no partition
  writes or `getvar`. Capture: 93 UDP packets, 19,248 decoded bytes. Log
  `/tmp/ios-extra-run-39755620038/logs/phone-0155-bcm-address-id.txt`, SHA256
  `6a7bb87ec85d75558f95e9b1e81e6ec5d75e13657054ce097c0ed47a56e7ca0e`; pcap
  SHA256 `d437f9b66424434075057c7951f4fa7a40967c6f57f2f1e9e78d3d99b72b2ea7`.
- New result: BCM ID 5 validation accepts SH0/MC0, but lookup stops at
  `bootstrap BCM metadata missing name=ACV`. CM3 remains reset; no vote was issued,
  so this boot did not execute GMU firmware/HFI or GPU work. Linux
  `cmd_db_get_header()` scans populated slave headers in order; the old parser
  searched only ID 5. Candidate patch 0156 now mirrors Linux lookup, tracks the
  selected header ID, requires SH0/MC0 to resolve as BCM ID 5, and validates
  address/header consistency and aux data. The ASan/UBSan fixture places ACV in
  the following ARC header and passes. Patch applies to CI buildtree 39755620038;
  CI and phone validation are pending.


## FP6 HFI cache-path phone retest (2026-10-22)

- Patch 0153 commit `e53c66ab499d75d2101b1736ffbb85a7642e64f8` passed CI run
  `39745254929` (build job 6m44s; FP6 boot job passed). Packaging was skipped
  by CI because `FP6_STOCK_DTB_URL` is unset. The CI kernel was packaged locally
  with the verified product ADT and Volcano DTB; package round-trip and SHA
  manifest checks passed. Temporary image:
  `/tmp/ios-extra-run-39745254929/package/fp6-gmu-hfi-cache-isolation.img`,
  SHA256 `cca41889433f9c1005ddf0aa79513f5be29f49a0bbb1b49808bc150de0d18c5e`.
- One authorized `fastboot boot` was run with `tools/gpu-phone-test.py`; no
  partition writes or `getvar` calls. The USB capture contains 411 packets and
  121,789 bytes. Pcap SHA256
  `440ad1cde70cb785db62a2f78b1d1bdb839a4a31593398d88883c9353dae367a`;
  decoded log SHA256
  `cd93331eea3af227a2808a44c2f6192130b6a106a928f79b6d3800c9d001ab23`.
  Both are under `/tmp/ios-extra-run-39745254929/logs/`.
- Source, build and phone evidence agree: the 0153 image boots through launchd
  without the earlier `phystokv_range` panic. GMU firmware reports
  `FW_INIT_RESULT=0x100`, `HFI_CTRL_STATUS=1`, then the bounded probe verifies
  CM3 reset and retains the context and clock votes. CX timer seeding is
  healthy (16 samples; XNU CNTVCT at 19.2 MHz). The optional
  `GPU_INIT_CX_REGS` SCM call is unavailable and is logged as nonfatal.
  `CB_FSR=0x400` remains the known FORMAT-only status. The SMMU SID stays
  disabled; the persistent firmware upload returned `0` (success). No HFI
  messages, GMU DMA, GPU commands, or rendering were exercised. Removing the
  WIMG rewrite is strongly supported as the panic fix, though the original
  panic had no stack trace, so causality is not formally proven.
- Patch 0154 implements the Linux-equivalent minimum DDR BCM vote before CM3
  release. It reads live cmd-db BCM addresses/aux data at `0x81c60000`, computes
  the peak-only 2,136,718 kB/s request from the stock FP6 DT, and uses one idle
  ACTIVE RPMh TCS. It waits for all command acknowledgments and keeps CM3 in
  reset if metadata, TCS state, or completion is uncertain. Fairphone Linux
  source (`9535e0f08` plus its Gen8.3 module) supports the encoding and startup
  order. The host harness passes with UBSan and the patch applies to the exact
  source from CI run `39745254929`. The first CI image and phone attempt are
  recorded below; the BCM slave ID was wrong, so no vote was written. This is
  an active bus-vote write, not read-only. After validating it once on phone,
  continue with HFI BW/PERF tables and MEM_ALLOC handling with
  explicit cache ownership transitions. GPU MMU/OOB, SQE/AQE submission,
  bounded GPU memory write, rendering/readback, and the A810-compatible
  IOKit/Metal path remain outstanding.

## FP6 patch 0154 first phone attempt (2026-10-22)

- CI `39750406760` passed for `0c5bd243dc26286b1283d5b00ca3daed50c890a2`.
  Kernel SHA256 `d9020fb23a17d7787fef17d0848a51910437da1bb2fb65a3ef07821963a25d78`.
  Local package used the verified FP6 ADT and stock DTB; header-v2 round-trip
  passed. Image `/tmp/ios-extra-run-39750406760/package/fp6-gmu-bootstrap-ddr-vote.img`,
  SHA256 `6093f7f39acac3cb034dc926b94655b100784511f4575b45facc10572d6a3647`.
- One `fastboot boot` was issued after finding exactly one fastboot device. The
  phone log photo shows `bootstrap BCM metadata missing name=SH0`, then
  `first boot stopped before CM3 release; DDR vote unavailable`. Therefore no
  BCM command was written and this boot did not start GMU firmware. The device
  continued booting and the user reports it is waiting for Apple HFS. USB ECM
  did not appear before timeout, so no pcap was produced; the fastboot transcript
  is `/tmp/ios-extra-run-39750406760/logs/phone-0154-bootstrap-ddr-vote-fastboot.txt`.
- Source review found the bug: cmd-db slave IDs are ARC=3, VRM=4, BCM=5. The
  first candidate incorrectly searched BCM names under ARC ID 3 (where CX/MX
  ARC records reside). Patch 0154 is being corrected to search ID 5, and the
  host fixture now identifies its records as BCM entries. The corrected patch
  passes the targeted ASan/UBSan host harness. The build and ID-5 phone retry
  are recorded in the following section. Its USB log lacks the earlier
  `metadata missing` line; source review found a separate stale address-ID=3
  check, so the code likely found metadata and silently rejected BCM addresses.
  Patch 0155 corrects the address check and test fixture; it is not built or
  phone-tested yet. No vote attempt has succeeded on hardware.

## FP6 patch 0154 cmd-db ID-5 retry (2026-10-22)

- Commit `4f68fcb011d5cbec92485f5b076a470140560f59` passed CI run
  `39752494051`; kernel SHA256 `1d67f88580dffa942cbc54e1b8b68c5d6f360de31dac6c16d8c3512b56eff9e8`.
  Packaged header-v2 image with USB ECM enabled:
  `/tmp/ios-extra-run-39752494051/package/fp6-gmu-bootstrap-ddr-vote-cmdb5.img`,
  SHA256 `fe97c9fadae1388605b37124550677f596201c3f51bdc151afd6e80d4f835494`.
- One temporary boot reached ping and produced a 96-packet USB log. Decoded
  text `/tmp/ios-extra-run-39752494051/logs/phone-0154b-bootstrap-ddr-vote.txt`
  (SHA256 `dc1eb8596dfaee7c70f0c8a40f056468c235fbf2b9f513361d10cd68aae2f602`),
  pcap SHA256 `c94751cca1fbba39e8129d11d3e3da7ae9ff5bb782498d522cd0a652f918b4d9`.
  SMMU walk, ARC floors, clocks, timer and firmware upload succeeded; optional
  SCM remained unavailable. Bootstrap then still reported missing SH0 metadata
  and stopped before CM3 release. No BCM write occurred.
- The log does not contain `bootstrap BCM metadata missing name=SH0`; it only
  contains the generic DDR-vote refusal. `fp6_gmu_bootstrap_bcm_vote()` still
  required `(addr >> 16) == 3` after looking up records. Since BCM addresses
  encode slave ID 5, and the host fixture also used `0x300xx`, this explains
  the silent refusal. Patch 0155 changes validation to BCM ID 5, reports any
  other ID, and uses `0x500xx` fixture addresses. It passes ASan/UBSan and
  applies after 0154 to the exact prior CI source. Build and phone retry remain.
  Handoff: `docs/FP6_GPU_CONTINUATION.md`.

## FP6 GMU first-boot attempt (2026-10-22)

- Repackaged CI kernel from run `39667763253` (commit `c79f49f`) with the
  verified product ADT and stock FP6 DTB. Temporary image:
  `/tmp/ios-extra-run-39667763253/package/gmu-first-boot/fp6-gmu-first-boot.img`,
  SHA256 `bfd28263fd42356b507e84d135a5581235e04b1183e52ebeafcafa919194d6b6`.
  Boot arguments enabled the opt-in SMMU, GMU firmware upload and bounded
  first-start paths (`fp6smmu=2 fp6smmupower=1 fp6gmuload=1 fp6gmuboot=1`).
- Phone reached launchd and logged the software walk passing for IOVA
  `0x60000000` -> PA `0x903627000`. It stopped before firmware upload:
  inherited GMU clock register `0x90d4` read `0x2001`, and the clock guard
  refused to proceed without checking whether CM3 was held in reset. No TCM
  upload, CM3 release, GMU DMA or GPU execution occurred. Full decoded log and
  pcap are `/tmp/ios-extra-run-39667763253/logs/phone-0140-gmu-first-boot.txt`
  and `.pcap` (SHA256 of decoded log `5b45571dd8ed645487722c56417e8d98b3b1e5d2ccf97637853834993e612097`).
- Patch `0147-fp6-gmu-inherited-clock-reset-gate.patch` moves the safety check
  ahead of clock reconfiguration: if the GMU core clock is already running, it
  reads `CM3_SYSRESET` first and refuses any clock change unless reset is
  confirmed. If reset is held, the bounded clock/firmware path can continue.
  Patch applies to the CI source; `tests/test_gpu_probe.py` passes. Full CI and
  a retest are still required.

## FP6 GMU clock-fix temporary image packaged (2026-10-22)

- Packaged CI run `39674158109` / source `696a07851fb4e46fd4ab810bdc97e666c14013e2` with product ADT `4da4226e6b9ac393ff22b66a304d9172d6be2bfd6d558348a47379c51aab1d80` and Volcano DTB `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`.
- Image: `research/local-fp6/package-696a078/fp6-gmu-clockfix-boot.img`, SHA256 `9a074945623e65676cf0f1d509a848de63ebe7d54c055b67bf844c9d0da6e989`. Header-v2, embedded payload and DTB round-trip validation passed. Manifest records boot args and all input hashes.
- The phone console photo now shows this image's GMU clock path succeeded: inherited core clock `0x2001`, CM3 reset confirmed, MX ARC floor `0xc0` acknowledged at level 5/TCS0, GPLL0 600 MHz, PLL0 configured, and GMU350/HUB200 clocks enabled. Persistent upload checked 159 pages and returned success (`firmware upload=0`) with CM3 held in reset and SID disabled before the bounded probe.
- GMU firmware then returned `FW_INIT_RESULT=0x100`; `HFI_CTRL_STATUS=1`. The probe reasserted and verified CM3 reset and retained SID/context/clock votes. SMMU global IRQ INTID705 was disabled/pending=0 in the read-only inventory; CB FSR `0x400` is the previously identified FORMAT status, not an asserted translation fault. This proves firmware start and HFI controller initialization, not an HFI command exchange or GMU DMA.
- USB ECM capture `/tmp/fp6-gmu-clockfix-phone.pcap` (SHA256 `b496a1396a21f4be468cb096ad12646526a9281fc2e5d59f99f14c84f4271f86`) and decoded `/tmp/fp6-gmu-clockfix-phone.txt` (SHA256 `185a559ce97068c27f45d3f261d1e62e0c8b28ebb6707c40bbc03c90bb5ba760`) started after the GPU log segment. They contain later boot/userland lines but not the early GMU messages; the console photo is the evidence for those values. Capture ended after 12 seconds because the UDP report stream is continuous.

## FP6 ADT and vendor DTS recovered locally (2026-10-22)

- Copied `/home/ersa/Downloads/vendor_boot.img` to ignored `research/local-fp6/vendor_boot.img` (SHA256 `26dbd78d40a739fd0790518fdaa09bef2cfb4a2098a5daf51098617f0f2ad31c`). `unpack_bootimg` identified Android vendor_boot v4 and extracted its DTB, vendor ramdisk and bootconfig under `research/local-fp6/vendor_boot/`.
- The DTB is a concatenation of 14 FDT blobs. All were split and decompiled with `dtc` under `research/local-fp6/vendor_boot/dtbs/`. `dtb-04` is Volcano (`qcom,volcano`, MSM ID `0x27c`) and its SHA256 `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3` matches the previously verified FP6 stock DTB. Selected DTS and DTB are `research/local-fp6/fp6-stock.dts` and `.dtb`.
- Generated `research/local-fp6/fp6.adt` with `tools/mkadt.py --device fp6`; it parsed successfully and contains the iPhone10,3 identity and D22AP `/product` artwork traits. It uses the existing read-only product-tree reference. SHA256 `4da4226e6b9ac393ff22b66a304d9172d6be2bfd6d558348a47379c51aab1d80`.
- Full local artifact inventory, hashes and regeneration commands are in ignored `research/local-fp6/README.md`. None of these device or Apple-derived files are tracked by Git.

## GMU clock fix pushed; bounded boot probe added (2026-10-22)

- Push to `ersascape/ios-extra` on `main`: commit `696a07851fb4e46fd4ab810bdc97e666c14013e2` (`fix(fp6): work on gmu support`). CI run `39674158109` passed; build artifact kernel SHA256 `a10bf7fb4b756f528c95af80d1dc14ed1e66dc8a290c5c0f3dfc6d1fc3670291`. The `fp6-boot` packaging step skipped because `FP6_STOCK_DTB_URL` is unset.
- Patch 0147's phone retry (`/tmp/ios-extra-run-39670975229/logs/phone-0147-gmu-first-boot.txt`, decoded SHA256 `8221b5123fd0ff78b92ebba115458007e007927d75af6a78f97ff2871a939aa2`) confirms GMU `CM3_SYSRESET=1` before setup and MX ARC floor acknowledged. Clock setup then refused without a named failure, so firmware upload/CM3 release did not occur on that boot. The temporary log directory is no longer present in this workspace.
- Patches 0148/0149 add stage-specific clock diagnostics and Linux-aligned setup: MX SVS_L1 floor `0xc0` for GPU PLL calibration, enabling outputs on a compatible inherited Lucid OLE PLL without changing its rate/divider, and waiting for RCG root-on before changing CFG. Unreadable/unsupported live PLL state still refuses; the PLL FSM path remains unsupported because gpucc-volcano exports no software vote register.
- Patch 0149 adds a 16 KiB trace buffer/header, checks firmware fault bits before success bits, and bounds even successful CM3/HFI initialization by asserting reset and verifying it. It retains DMA pages, SID/context and clock votes after the probe, including if reset readback fails, because reset alone does not show bus transactions drained.
- Source review used Fairphone Linux kernel `9535e0f0885d3d4b91c38054541e16019d1e64bd` and modules `54c948d9b30c2ba01835e64c36b68b80692554ac`. `python3 tests/test_gpu_probe.py`, its ASan/UBSan run, and `python3 tests/test_fp6_gmu_boot.py` pass. CI verifies compilation of the patched XNU tree; it does not run these host tests.
- The phone booted 0148/0149 successfully through GMU firmware initialization and HFI_CTRL_INIT. The 0150 CI phone test later stopped safely before upload because CX timer validation returned 0/16 samples; the photo and USB log agree. An unbuilt local follow-up now accepts zero-skew samples and sets CPU WCOMB on the five 16 KiB pages backing the shared HFI queue allocation before publishing the domain. Host normal and ASan/UBSan probes pass; system-Clang AArch64 compile against the exact 39728088129 build tree reports 0/1 failures. No HFI messages or GPU work have run yet. Full HFI still needs the minimum DDR vote, perf/BW tables and MEM_ALLOC request handling. GPU MMU/OOB/SQE startup and a known-value memory-write test remain. UniXNU NativeAdreno/NativeMetal contains A740-specific register and GMEM assumptions and cannot be treated as A810 support.

## Patch 0145 phone log: software table walk passes (2026-10-22)

- A later report appended to `/tmp/claude-1000/-home-ersa-Dev-ios-extra/febca858-d68f-4e09-bdd9-8bdf4a7eb119/scratchpad/gmu-boot4.log` has boot args matching the locally packaged SMMU test (`fp6smmu=2 fp6smmupower=1`). This is a new run in the same log file; the earlier ATOS failure remains above it.
- Phone log: IDR0 `0x4c017e18` advertises ATOSNS; TCR2 readback is `0x00038071`; the CPU table walk reports IOVA `0x60000000` -> PA `0x903617000`, expected `0x903617000`, `passed=1`. This is the first phone confirmation of the software-walk path.
- The final state is `mapped=1 contained=1 route_live=0 bank_reserved=1`; the context bank is disabled and reserved, so no GPU master ran. This validates CPU-visible page tables only, not SMMU table fetch, stream routing, GMU DMA or GPU execution. The log continues through launchd and userland startup; no visible-screen confirmation was recorded.

## Patch 0145 build and local FP6 image (2026-10-22)

- CI run `39663527285` passed for `ced5799de0456a1f06a1fb90291eff40e4e17bfd`;
  kernel artifact SHA256SUMS verified. The CI `fp6-boot` job skipped image
  packaging because the repository variable `FP6_STOCK_DTB_URL` is unset.
- Locally packaged the CI kernel with the full product ADT (SHA256
  `6435ed347b1091a80ae59e695f6decc4f2c89ef647f493b83d2ebf2578a3e752`) and
  verified stock FP6 DTB (SHA256
  `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`). The
  UFS-root command line enables `fp6smmu=2 fp6smmupower=1` for the SMMU
  software-walk validation.
- Image: `/tmp/fp6-gpu-ced5799-39663527285/fp6-shim-0145-soft-walk.img`, SHA256
  `b0555fbcbfb28a9ad8dae5fb3123ec130fabc8a83c2f03f6639d91a7314ad1db`.
  Header-v2 payload, shim, and embedded-DTB round-trip checks passed. This is
  a packaged image only; it has not been booted on the phone.

## FP6 SMMU ATOSNS software walk (2026-10-22)

- Reviewed `/tmp/claude-1000/-home-ersa-Dev-ios-extra/febca858-d68f-4e09-bdd9-8bdf4a7eb119/scratchpad/gmu-boot4.log`. The boot reports GPU SMMU `IDR0=0x4c017e18`; after the CB TCR2 readback it logs `context-bank ATOS IOVA=0x60000000 PAR=0x0 expected=0x90361b000 passed=0`, then contains the failure before any master runs. IDR0 bit 26 (`ATOSNS`) is set, so the zero PAR is consistent with unsupported ATOS rather than evidence of a bad PTE. The same log's setup reached TCR2 but does not include a successful TCR readback.
- Patch `0145-fp6-smmu-soft-walk.patch` uses the configured 4 KiB SMMU granule and T0SZ=32, and checks the expected physical page for both temporary and persistent GMU table ranges when ATOSNS is set. CI `39663527285` passed on `ced5799`; the packaged image and phone result are recorded above. It does not prove SMMU table fetch, SID5 routing or GMU DMA.
- Replaced the persistent-table physical-address scan (up to 2,048 candidate L3 entries on every page walk) with direct L1/L2/L3 selection from the IOVA, while retaining physical-address checks. Corrected the patch hunk count; `git apply --numstat` parses it. Host coverage now checks the ATOSNS path issues no ATS write and returns the expected PA, and checks direct persistent table lookup at all three levels.
- `python3 tests/test_gpu_probe.py` passes. Full host suite: 12 tests pass normally and with ASan/UBSan (`ASAN_OPTIONS=detect_leaks=0`). The phone report passes the software walk; no screen confirmation is recorded.

## Timer failure diagnostics follow-up (2026-10-22)

- The latest `ml_get_hwclock()` image reached `upload refused: CX timer
  synchronization failed`; no USB capture was produced, so the exact failing
  branch is unknown. Source review found silent returns if either CX counter
  read fails or if CPU/CX counters do not advance during the bounded 1 ms
  check.
- Added patch 0151 to print which counter read failed, or both before/after
  values when the counters do not advance. Verified it applies to the exact
  source tree from CI run `39732507544`. This is source-level verification
  only; CI and phone results are pending.

## FP6 CX timer: USB diagnosis and Linux-aligned seed fix (2026-10-22)

- CI `39735265609` passed for `089d4ef39822e751ada55eae9bc53f3ccc4472f2`.
  The temporary image was `/tmp/ios-extra-run-39735265609/package/fp6-gmu-timer-diagnostics.img`,
  SHA256 `b5a30a6bce20a730c39529ae08121ddfdbe29c614ad42477b3a21ed9de6c9fef`.
  It was booted once with `fastboot boot`; no partition was flashed or written.
- USB capture `/tmp/ios-extra-run-39735265609/logs/phone-0151-cxtimer-diagnostics.pcap`
  (SHA256 `d297cbf17896b9e36d0afc4709ae6ead0b1eeff7fb7709a9cfdba6a12aca0851`)
  decoded to 405 packets / 122,058 log bytes at
  `/tmp/ios-extra-run-39735265609/logs/phone-0151-cxtimer-diagnostics.txt`
  (SHA256 `729d365b3edab8c39364aca208c58e2673738594498b8dfb438ebba4c643af32`).
  The phone reports CPU counter `0x71e78f2c7->0x71e793e01` while CX stays
  `0x71e78f2ab->0x71e78f2ab`; this confirms the added “must advance” check caused
  the refusal. Firmware upload, SCM/CM3 release and HFI did not run.
- Patch 0152 removes the post-seed CX readback, offset, advance and rate gates.
  Fairphone Linux `gen8_cx_timer_init()` seeds the counter and continues without
  those checks. The host harness models a static post-seed CX counter;
  `python3 tests/test_fp6_gmu_boot.py` and `git diff --check` pass. CI and phone
  validation of this fix are pending.
- Commit `09a398b2d85e1a38e17558003ecdb3e0faa64dc1` passed CI run
  `39739290127`. Kernel SHA256 is
  `9a5d96ef3eb2a2d9b6e854cdaf05852fce850ca18fe57e87e4376364e770a630`.
  Packaged header-v2 image `/tmp/ios-extra-run-39739290127/package/fp6-gmu-cxtimer-linux-seed.img`
  SHA256 `1062709ab0ab0d7a88b8bc5a15a25a3141b5bb4b48557c19741a54b6272ec881`
  with product ADT SHA256 `4da4226e6b9ac393ff22b66a304d9172d6be2bfd6d558348a47379c51aab1d80`
  and stock DTB SHA256 `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`.
  Kernel checksum and package round-trip checks passed.
- Initial checks found `fastbootd`, then no device. A later explicit user
  authorization put the phone in bootloader fastboot and the image was tested
  once, as recorded below. No flash or partition write occurred.
- Linux Gen8 source confirms minimum DDR bandwidth is voted after firmware load,
  SCM CX setup and version info, before GMU start and HFI. The XNU RPMh helper
  currently supports ARC and VRM resources, not the interconnect/BCM vote, so
  if timer removal reaches FW_INIT the following measured work is the minimum
  DDR vote before enabling HFI traffic.
- Phone test on `fp6-gmu-cxtimer-linux-seed.img` was then authorized and run
  once through `tools/gpu-phone-test.py`. `fastboot boot` returned OKAY, but the
  phone panicked before answering the USB ECM ping. The supplied panic is
  `phystokv_range: illegal pa: 0x3df4000 phys base 0x900000000 size 0x100000000`
  at `arm_vm_init.c:406`. No pcap was produced; only the helper's fastboot
  transcript remains at
  `/tmp/ios-extra-run-39739290127/logs/phone-0152-linux-cxtimer-seed-fastboot.txt`.
  No second boot or recovery command was issued.
- Source-order candidate (not yet confirmed by a panic backtrace): after the
  timer check, `fp6_gmu_boot_reserve()` first changes the five HFI backing pages
  to WCOMB. XNU's `pmap_set_cache_attributes()` reaches `phystokv_range()` when
  the page is treated as managed RAM; the reported PA is outside the configured
  high RAM window. The full panic backtrace is needed to confirm this caller
  before changing allocation/cache policy. The device is currently back in
  bootloader fastboot after the panic.

## Current FP6 GPU path

The active target is FP6 Adreno 810 Gen8.3. Patch 0170 passed CI `39842360411`
and the phone test safely configured disabled CB0 for SID0 and serviced nine
GPU-access allocation kinds plus one GMU-only allocation. Firmware and HFI
startup succeeded, then the probe correctly stopped at secure preemption kind 5
(`GFX_SECURE`); Fairphone Linux uses protected pages assigned to `VMID_CP_PIXEL`,
which XNU does not yet implement. The bounded path reset CM3. GPU-core boot,
GPU-master DMA, command write/readback, draw/readback and Metal remain
unverified. See the 0170 section at the top for the exact image and log. The
next source question is whether a single-ring probe can disable preemption and
avoid the secure allocation while retaining a valid Gen8 startup path.

See [FP6 GMU first boot](docs/FP6_GMU_FIRST_BOOT.md), [FP6 Adreno Metal audit](docs/FP6_ADRENO_METAL_AUDIT.md) and [FP6 SMMU power](docs/FP6_SMMU_POWER.md).

## Freedreno / Metal reference inspection (2026-10-22)

- Read-only inspection of `/tmp/hackios-xnu-kernel` commit
  `8e61187098f2c26c5daee8f9f72b6416aa64b9ab` and
  `/tmp/hackios-xnu-userland` commit
  `906425b75e02b4f99eb5d7bb1ef7c9583472d772`, especially
  `tools/mesa/mk-mesa.sh`, `tools/mesa/freedreno-darwin.patch`,
  `tools/mesa/redwood-drm/`, and `iokit/Kernel/RedwoodGPU.cpp`.
- Confirmed the working rendering path is Mesa Freedreno (`msm` DRM KMD) over
  an IOKit `RedwoodGPU` user client: buffer create/info/map/close, command
  submission, and fence waits. The userland DRM shim maps the Linux ioctl
  selector and structure ABI onto IOKit calls; buffer handles are mapped as
  client memory. IOSurface import has a separate Redwood selector.
- AIR is a Mesa frontend to NIR/ir3 and is callable from the Metal library
  path, but it does not implement Apple's Metal object model or submission
  ABI. The reference's measured hardware is Adreno 642L; FP6 is Adreno 810
  Gen8.3, so its kernel interface and lifetime model are useful, while its
  chip-specific command programming cannot be copied as A810 support.
- Panic follow-up from CI buildtree `39739290127`: the reported PA
  `0x3df4000` equals `0x903df4000 - gPhysBase(0x900000000)`, an offset within
  the configured RAM window. This raises a specific question about a
  base-relative page number being passed where XNU expects an absolute PA.
  The exact code path is still unconfirmed without panic frames. Do not change
  allocator/cache policy or run another phone test on this inference alone.

## Patch 0150: CX timer and SCM CX preflight (2026-10-22)

- Source inspection: Fairphone Linux `adreno_gen8.c` initializes the CX AO
  timer with 16 samples using `cntpct` and writes to `cx_misc` offsets
  `0x200/0x204`; first GMU start calls optional SCM CX setup with ALWAYS_EN and
  TSENSE. Patch 0150 ports the sample/seed operation, adds bounded readback
  and rate checks, and requests only those two features (`0x9`), leaving BCL
  and CLX disabled.
- The opt-in `fp6gmuboot=1` path synchronizes the timer before firmware upload.
  SCM availability and initialization are checked before SID publication and
  CM3 release. An unavailable SCM service is treated as optional; an available
  service returning an error aborts before the GMU is routed as an SMMU master.
- Host-model timer/SCM fault-injection tests, normal and ASan/UBSan runs, the
  GPU probe host harness and a local AArch64 single-file syntax compile passed.
  The compile used system Clang because the configured Swift Clang path is
  absent. Full unittest discovery cannot import `test_fp6_gmu_runtime.py`
  because `/tmp/fp6-firmware/gen80300_gmu.bin` is unavailable; the directly
  relevant tests pass.
- CI run `39728088129` passed on `c1de4a39ed6dfc2307311fc9d09115f1d3085f5a`.
  Kernel SHA256 `0f57862c073138ddcf74c1380f862c5bc295f3cea2849c8d781a313d15278710`
  verified against `SHA256SUMS`. The workflow image package skipped because
  `FP6_STOCK_DTB_URL` is unset. Local header-v2 image
  `/tmp/ios-extra-run-39728088129/package/fp6-gmu-cxtimer-scm`
  has SHA256 `ff170c41e125c5f1e91431f14a281db4dfe7855d4e55c8d92274f747d489ebd8`;
  it embeds the verified stock DTB and product ADT and enables the opt-in
  upload/first-boot path. No phone boot yet: `fastboot devices` showed zero
  devices when the image was ready.
- Phone test of that image reached launchd and ECM ping. It stopped before
  firmware upload: timer reported `valid=0/16 CNTFRQ=19200000`; therefore SCM
  CX setup, CM3 release, `FW_INIT_RESULT`, and `HFI_CTRL_STATUS` were not
  attempted. The decoded USB capture is
  `/tmp/ios-extra-run-39728088129/logs/phone-0150-cxtimer-scm.txt` (SHA256
  `36c5f8cb4638a0a5436b49e14538160d7907f309f1c6e2a793328bc06ec74a89`); pcap
  is beside it (SHA256
  `e7d6cc8bcaaa7c35b1923a85765e551ee93ebc1eedcf0732bdbc318575949c10`). The
  console photo corroborates the timer failure and shows the subsequent SMMU
  context test contained with `route_live=0`.
- Root cause is now narrowed to the sample filter: the code rejected
  `write_cost == read_cost`, although a 19.2 MHz counter quantizes short
  accesses to equal ticks. The next local patch accepts zero-skew samples and
  reports raw read/write timing ranges plus shorter/outlier counts. Normal and
  ASan/UBSan host tests cover the equal-tick case; the updated file compiles
  against the CI build tree with system Clang. This fix is not yet built by CI
  or phone-tested.
- The combined local follow-up also marks all five 16 KiB CPU pages covering
  the shared 0x12000-byte HFI allocation `VM_WIMG_WCOMB` before writing queue
  headers or publishing the SMMU domain. It confirms physical contiguity and
  that each page was default cached or already WCOMB, then sets and checks the
  attributes. This mirrors Linux's write-combine HFI mapping and prevents
  cached CPU writeback from clobbering GMU-owned queue indices. The pmap API
  definitions are explicitly declared in the FP6 driver because they are not
  exported by the BSD-visible header configuration.
- The combined patch passes `test_fp6_gmu_boot.py`, `test_gpu_probe.py`,
  `test_rpmh_arc.py`, and `test_xnu_cc.py`, normally and the two C harnesses
  under ASan/UBSan. A system-Clang AArch64 compile of `sweet_gpu.c` against
  the exact CI 39728088129 build tree reports 0/1 failures. This source delta
  is local only: no CI build or phone test has been run for it yet.
- Follow-up build `6c248dd` passed CI run `39730474027`; kernel
  `SHA256=1dccb4fb5992417c37b73c28fc74d49e30c2f7dc8b3e2050fd5b8cfd08a02228`.
  The temporary header-v2 image
  `/tmp/ios-extra-run-39730474027/package/fp6-gmu-timer-wcomb.img` has
  `SHA256=f2b92b5fcfeb6af4e86a953dae8202b12abda5c1f700e8a9c59cd51d69137845`.
  Its phone boot still refused the timer: `valid=0/16`, `read=0..0`,
  `write=0..0`. USB capture contains 705 packets / 168,631 log bytes;
  pcap SHA256 `048725f34765776a36d4ce5cbc13733854bbf47875ed30b491ca095e15f59dfe`,
  decoded text SHA256 `e14fbf9b65b5a6dd6ff6f4d6d791f254933d0530ec79ad71d8d7bcbc94aed83a`.
  It confirms SMMU test contained and no firmware upload. All samples were
  discarded as backward before recording timing ranges.
- Source inspection found XNU's `ml_get_hwclock()` is its nonspeculative
  `CNTVCT` hardware timebase; the driver had used raw `CNTPCT`. The latest
  local update uses `ml_get_hwclock()` and logs backward-read counts plus the
  final raw sample triple. This is an XNU-specific counter-source correction
  inferred from the phone result; no CI or phone result exists for it yet.
- The interrupted test exposed a prompt loop in `phone-ecm-host.py`: setup
  errors retried two `pkexec` commands every 100 ms, while the outer test also
  made separate capture/cleanup authorization requests. The updated helper
  performs setup, bounded capture and stale-capture cleanup under one
  authorization, fails immediately on setup/auth errors, and self-stops
  tcpdump. The prior root capture at
  `/tmp/ios-extra-run-39730474027/logs/phone-0150-timer-wcomb.pcap` was not
  stoppable after pkexec authorization was denied; the next authorized helper
  call can stop only that exact capture path. No serial is stored.
- Minimum DDR bandwidth/BCM voting remains unresolved. Do not send HFI messages
  until shared HFI backing is mapped Normal noncached on CPU pages and runtime
  BCM metadata is understood.

## FP6 GPU SMMU: TCR2 passes, FSR FORMAT bits (2026-10-21)

- Boot of CI `39650403002` (`b919d67`, 0143), 18:19:12 UTC, USB log:
  `TCR2 wrote 0x00038011 read 0x00038071` (accepted), then `setup failed:
  fault clear +0x22058 want=0x00000000 got=0x00000400`, `contained=1
  route_live=0 bank_reserved=1`. FSR 0x400 is FORMAT (bits 10:9 = 0b10,
  AArch64 context), read-only, not a fault. Patch 0144 checks only Linux's
  ARM_SMMU_FSR_FAULT bits (0xc00001fe), and compares only programmed fields
  for SCTLR (0x27), S2CR (TYPE + CBNDX) and SMR, logging any extra bits read
  (pre-emptive: this SMMU has forced read-only bits). Compiles locally; host
  suite passes.

## FP6 GPU SMMU context bank live; TCR2 TBI bits (2026-10-21)

- Boot of CI `39649157006` (`ebae218`, 0141/0142), 18:09:17 UTC; full boot
  log received over USB (0142 whole-ring replay works, 104 KB including the
  early SMMU inventory: IDR0=0x4c017e18 IDR1=0x40000016 IDR2=0x00005511
  sCR0=0x002c0406, 24 groups, 22 banks). CX vote + GDSC on as before;
  `clock index=3 running without SW enable (0x00000000)` (0141 works).
- **CB2 TCR2 now retains its value**: wrote 0x00038011, read 0x00038071.
  Previously it read 0 (dead bank while CX was collapsed). The difference is
  TBI0/TBI1 (bits 5-6), forced on by the hardware or hypervisor; the strict
  readback rejected it before any stream route was written (`route_live=0`),
  and the rollback's TCR2==0 check reported `contained=0` for the same bits.
  Patch 0143 compares TCR2 without the TBI bits in setup and rollback and
  logs the value read. Compiles locally; host suite passes.

## FP6 GMU boot attempt: stopped at the SMMU AHB clock (2026-10-21)

- Boot of CI `39647440570` (`8e055a8`, all GPU stages on, console muted),
  18:00:16 UTC. Phone stayed up (launchd running). Console photo: RPMh CX
  vote and CX GDSC succeed again; `before/after AON gates ahb=0x00000000
  hub_cmd=0x00000000 hub_cfg=0x00100000 hub_div=0x00000001`; gates
  cb 0x1, cxo_aon 0x0, demet 0x0, gx_ahb_ff 0x80000001, rscc_hub_aon 0x1,
  rscc_xo_aon 0x1, sleep 0x1; then `clock index=3 before=0x00000000` and
  `prerequisite clock failed index=3; no context writes`, so the context
  test, upload and CM3 release did not run.
- gpu_cc_ahb reads 0 with CLK_OFF clear: running under hardware/other-voter
  control while its SW enable ignores writes (cxo_aon and demet likewise).
  Linux does not read back HALT_DELAY branch enables. Patch 0141 accepts a
  branch that is SW-enabled or not CLK_OFF, and logs it.
- USB log: the host received 37 KB starting mid-boot; the early lines were
  lost because the logger replays only 64 KB and starts sending at link-up,
  before NetworkManager has assigned 192.168.7.1. Patch 0142 replays the
  whole 4 MB ring and waits 3 s after link-up. Host side: NM profile
  `fp6-usb-log` and a ufw rule for UDP 5140 (added by the user).

## FP6 SpringBoard/PosterBoard crash after Bold Text: CoreImage GL (2026-10-21)

- User enabled Settings > Accessibility > Bold Text; SpringBoard and
  PosterBoard then crash: `CRASH SpringBoard sig 11 code 0x100000001 sub 0x0
  slide 0x35730000`, `pc 0x0 lr 0x1ca26858c` (unslid 0x194b3858c).
- Symbolicated with ipsw 3.1.739 against the 20H392 shared cache extracted
  from the Tegu root (local, git-ignored: `research/dsc-20H392/`,
  `research/tools-ipsw/ipsw`): CoreImage `CI::GLContext::init()` +204. Its
  `GetMacroContext` -> `[EAGLContext getMacroContextPrivate]` returns NULL
  (no GLES renderer: no GPU driver), the 0x2c8-byte GL dispatch struct stays
  zero, CoreImage logs "Unable to get macro state for the GLContext" and
  then calls slot +0xe8 with 0xb71 (GL_DEPTH_TEST) -> blr to NULL. No Bold
  Text code in that function; the respring path presumably creates a GL
  CIContext (inference). Fix depends on a GPU renderer, or forcing CoreImage
  to its CPU renderer / making GL context creation fail cleanly (not tried).

## FP6 GMU first boot patch (2026-10-21)

- Patch 0140 (opt-in `fp6gmuboot=1`, after a successful `fp6gmuload=1`
  upload; also needs `fp6smmu=2 fp6smmupower=1`) follows
  `docs/FP6_GMU_FIRST_BOOT.md`: reserves noncached HFI (0x12000, 17 queues),
  log (64 KiB) and VRB (4 KiB) first-fit from 0x60000000 before the domain is
  frozen, fills the queue table/VRB header, re-arms the SID5 stream match,
  masks all GMU interrupts, writes KGSL's register config (RPMH_POWER_STATE,
  FAL, BOOT_CONFIG 2, HFI_QTBL, fence range 0x80c808a0, CM3_CFG 0x4052,
  GBIF, GENERAL_8..11, caches), prints the DTCM firmware versions, releases
  CM3 and polls FW_INIT_RESULT for 0x100 (100 ms, aborts on 0xe00), then
  HFI_CTRL_INIT/STATUS. No HFI messages yet. Failure puts CM3 back into
  reset, masks/clears interrupts and sets the fence to allow. Compiles
  locally; host suite passes; no phone result. This would be the first GMU
  firmware execution on FP6.

## FP6 first RPMh vote and CX power on the phone (2026-10-21)

- No-spam GPU power test (`fp6smmu=2 fp6smmupower=1`, kernel `121a02d`,
  booted 17:42:00 UTC), console photo: `CX GDSCR=0x0022f001
  status=0x2800010a HUB_CMD=0x00000000`; **`FP6 CX ARC floor 0x40
  acknowledged level=2 TCS=0`** (first RPMh vote from XNU on FP6); **`CX GDSC
  on GDSCR=0xf8228800 status=0x80000202`** (PWR_ON). SMMU clocks: 0x7000
  before 0x80000000, GCC memnoc 0x3, snoc 0x1, gpu_cc_ahb 0x90bc before
  0x00000000 and its enable did not stick -> `prerequisite clock failed
  index=3; no context writes`.
- gpu_cc_ahb and the hub RCG reading all-zero (not CLK_OFF) suggest a dead
  hub/RSCC clock domain. gpucc-volcano probe enables seven always-on gates
  (cb, cxo_aon, demet, gx_ahb_ff, rscc_hub_aon, rscc_xo_aon, sleep) before
  any GPUCC clock; our SMMU path did not. Patch 0139 enables them right
  after the CX GDSC and logs ahb/hub before and after (source-based).

## FP6 canvas placement and USB log host setup (2026-10-21)

- User: a black bar is visible at the top. 0130 centred the 1125x2436 canvas
  on the 1116x2484 panel (24 rows above and below). Patch 0138 adds boot-arg
  `sweetfb_top=N` (rows above the image, clamped to 0..48) in AppleCLCD and
  SweetHID alike, default 0: image at the top edge, the 48 spare rows below.
  Both files compile locally; no phone result yet.
- The GPU CX test boot (17:37:51 UTC) could not be read: `-enable_kprintf_spam`
  in the hand-written boot args flooded the console. Repacked without it:
  scratchpad `img-121a02d/nospam/fp6-shim-gpu-cx-power-console-nospam.img`,
  SHA256 `2b76017a22ebf733599e2556648dc9d15fde27aa2b029f167289bfa6a457c6ec`.
- Host USB log: NetworkManager profile `fp6-usb-log` (static 192.168.7.1/24,
  matched by host-side MAC 02:00:5e:77:ee:01, autoconnect) replaces the DHCP
  attempt on `enp128s20f0u9`; ping 192.168.7.2 answers. A user-level UDP
  listener received nothing because ufw is active; allowing UDP 5140 on that
  interface needs root (`ufw allow in on enp128s20f0u9 to any port 5140 proto
  udp`).

## FP6 GPU power review and fixes (2026-10-21)

- Recovered an interrupted session's unpushed work from `/tmp/fp6-smmu-work`
  onto branch `codex-gpu-rescue`: commits 3896b67/e63291f/ab3faae/22d527c and
  uncommitted 0134 (opt-in `fp6smmupower=1` CX ARC floor + CX GDSC + hub CXO),
  0135 (`fp6gmuload=1` GMU upload with CM3 held in reset), 0136 (GMU clock
  preparation), `docs/FP6_SMMU_POWER.md` and host tests. CI `39641511245`
  built it.
- Phone evidence (console photo, earlier kernel): `CX_GDSCR=0x0022f001`
  (SW_COLLAPSE set), GPU SMMU groups 10-23 invalid with S2CR fault type,
  `context banks with nonzero state=0/22`. The SMMU (`kgsl-smmu@3da0000`,
  `vdd-supply = gpu_cc_cx_gdsc`) sits in the collapsed CX domain, which is
  the leading explanation for CB2 TCR2 reading back 0.
- Source review against Fairphone `gdsc-regulator.c`, `rpmh-rsc.c`,
  `arm-smmu.c` and KGSL gen8 found, and patch 0137 fixes: CX GDSC power
  status is GPUCC+0x9094 (DT `hw-ctrl-addr`), not GDSCR bit 31; GDSC enable
  now sets clk-dis-wait 8 and RETAIN_FF like Linux; RSC votes no longer mask
  the slot IRQ and poll gated IRQ status - they use Linux's two-step
  trigger/mode clear and poll CMD_STATUS ISSUED|COMPL and TCS idle; the ARC
  floor is LOW_SVS (0x40) instead of the TURBO boot-proxy 0x180; GMU clock
  preparation no longer reads GMU registers before all six KGSL GMU clocks
  run (adds hub_cx_int 0x90e8) and refuses if the GMU core clock is already
  on; FP6 GPU MMIO is single LDR/STR inline asm with register sources and
  TLBIALL/TLBSYNC write QCOM_DUMMY_VAL (-1), per arm-smmu.c's hypervisor
  note. The earlier 0131 rollback abort matches Gunyah refusing a stage-2
  CBAR (TYPE=0) restore. Host model updated (status register, GDSC bits,
  LOW_SVS index); 12/12 host tests pass; local arm64 compile passes; FP6 GPU
  functions contain no WZR/XZR MMIO stores or write-back MMIO accesses.
- Not yet fixed (latent): PAS/zap SMCs use FAST call IDs, leave x6
  uninitialized and do not handle INTERRUPTED/WAITQ returns (Linux uses STD,
  x6=0, retries); the zap carve-out stays mapped after load. FP6's GPU is
  Adreno 810, Gen8.3 (`qcom,adreno-gpu-gen8-3-0`, gen80300 firmware, KGSL
  hwsched path); the GMU is at 0x3d37000/0x68000 per the stock DT.
- Merged to main as `f103c2d`. Test image from CI `39643343440` (branch
  head `121a02d`; kernel patches identical to main `f103c2d`), local ADT with
  `/product`, stock DTB, console visible, `fp6touch=2 fp6smmu=2
  fp6smmupower=1`: scratchpad `img-121a02d/fp6-shim-gpu-cx-power-console.img`,
  SHA256 `88b5038ad453a48dd31d2be689afd243c8589aa7cbea7434bfae72ac8e9e1d51`.
  Kernel contains the 0137 log strings. Temporarily booted 17:37:51 UTC;
  first FP6 RPMh (CX ARC LOW_SVS) vote attempt; result pending.

## CX power state observed on phone (2026-10-21)

- User supplied a console photo from the clock-prerequisite build. It shows
  `CX_GDSCR=0x0022f801`, `HUB_CMD=0x00000000`, followed by the refusal
  `CX domain is not enabled; needs RPMh/CX power before context access`. The
  GDSCR SW_COLLAPSE bit is set and PWR_ON is clear, consistent with an off CX
  domain. This run did not reach TCR2 programming, so it does not isolate why
  the earlier TCR2 write read as zero. The photo does not independently name
  the image, though its diagnostic text matches the 0b41ea2 clock build.
- 0134 draft now adds a dedicated FP6 RSCv3 CX ARC floor vote and CX GDSC/hub
  safe-XO setup. It needs source review, full harness and kernel build before
  any phone test. GMU clocks remain a separate stage; avoid changing live GMU
  rates until reset state has been read.

## Stock-clock kernel packaged (2026-10-21)

- CI39636402248 passed on0b41ea23c1d910865a2412c88fcccedb3dfb388e.
  Downloaded kernel matched artifact SHA256SUMS. Packaged visible-console
  UFS-root image `/tmp/fp6-smmu-0b41ea2/image/fp6-shim-smmu-clocks.img`,
  SHA256 `d4c7a60686b9e71c796900d94ca43531ba4d5e0657b937928b3ddd702341d0ff`.
  Header/payload/DTB packaging checks passed. Includes0132 stock clock votes,
  not the subsequent0133 domain helper or draft0134/0135. No phone result yet.
- Loader callback failure cases now check readiness, allocation, external copy,
  TCM write and publication failures stop the upload at the proper boundary.
  Eight firmware unittest cases passed after this extension.

## Persistent Gen8 GMU mapping layer (2026-10-21)

- Patch0133 adds boot-lifetime sparse 4KiB tables and external backing
  reservation/copy/publication operations. It rounds firmware reservation sizes
  to page coverage and refuses page overlap; uses Normal NC, privileged RW,
  outer-shareable PTEs matching KGSL flags without IOMMU_CACHE. GMU cached VMA
  metadata does not silently choose write-back SMMU attributes.
- `python3 tests/test_fp6_gmu_domain.py` passes synthetic boundary/failure
  cases and actual pinned firmware through upload callbacks, with payload byte
  comparisons and PTE physical-address walks. The map freezes after publishing.
  This remains a staged helper without a runtime owner; live allocation/cache
  callbacks, context activation and GMU execution are not established.

## Firmware loader host check (2026-10-21)

- Eight `tests/test_fp6_gmu_fw.py` cases pass, including staging both headers
  and compiling/running the upload layer against the SHA-pinned actual blob.
  Callback harness checks six external reservations, one external data copy,
  all TCM words and final publication. ASan/UBSan execution also passed with
  leak detection disabled (LeakSanitizer is unsupported under this host tracer).
  This proves callback sequencing on host, not real DMA or GMU execution.
- Review caught an integration issue in draft0133: firmware preallocation
  lengths are not all page aligned; the mapping layer must round safely.
  Also verify cache attributes against KGSL flags rather than infer them from
  GMU VMA names. Agent is correcting these before integration.
## FP6 SpringBoard bounding-path crash: missing /product artwork traits (2026-10-21)

- Correction to the entry below: the user reports the stale MobileGestalt
  cache was already cleared, so the cache theory does not explain the
  `69f9878` crash. That image used CI's `fp6.adt` (10,496 bytes), which has
  **no `/product` node**: CI lacks the Apple D22AP tree, so mkadt silently
  omitted it. Local ADTs (13,180 bytes) carry `/product` with
  `artwork-device-subtype` 0x984 (2436), `artwork-scale-factor` 3,
  `artwork-device-idiom` "phone", `artwork-display-gamut` "P3" and
  `artwork-dynamic-displaymode` "0" - the traits the asset manager uses to
  pick renditions. Without them `BoundingPathBitmap-1125x2436-375x812-3.00x`
  cannot be matched even though it exists. Earlier home-screen boots used
  local ADTs with `/product`.
- `tools/mkadt.py` now refuses a non-QEMU ADT without `/product` unless
  `--allow-no-product`; `tools/fp6-package.py` refuses an ADT lacking
  `artwork-device-subtype` unless `--allow-no-product` and records
  `product_node` in the manifest. CI passes the override for its build-only
  ADT and its (currently skipped) packaging. Local checks: missing D22AP
  tree -> both tools refuse; override -> `product_node: false`; full ADT ->
  `product_node: true`.
- The `img-0b41ea2` image below has `/product`. If SpringBoard still aborts
  with it, the no-`/product` boot may have re-cached wrong traits and the
  MobileGestalt cache needs clearing once more.

## FP6 SpringBoard bounding-path crash: earlier stale-cache hypothesis (2026-10-21)

- `/tmp/fp6-blackboot-packets.txt` (kernel `69f9878`, which already includes
  0130's 1125x2436 canvas) shows 423 SpringBoard aborts:
  `Failed to load bounding path bitmap data from the asset manager for asset
  name: BoundingPathBitmap-1125x2436-375x812-3.00x`. The requested name is
  the correct iPhone X one and the asset exists in the root catalog (earlier
  audit), so canvas geometry is no longer the issue.
- Same failure as Tegu, where it followed boots with the wrong identity and
  cleared only with a fresh root booted with the correct D22 ADT from its
  first boot. On FP6 the current root booted several times with the native
  1116x2484 screen before 0130; MobileGestalt's disk cache (keyed by build and
  UUID, per SWEET) keeps traits derived from that screen. Source-based
  diagnosis; not yet confirmed by a clean-root boot.
- Proposed test: reflash the never-booted Tegu-built root
  (`research/fp6-rootfs-tegu-20261021/fp6-ios-root-tegu.simg`, `a1c6f7da...`),
  then first-boot a kernel with 0130. Image from CI `39636402248` (`0b41ea2`;
  0070, 0130, touch, keys; GPU tests off by default), regenerated ADT with
  canvas 1125x2436 and `/product`, stock DTB `16a9e60e...`, console muted,
  `fp6touch=2`: scratchpad `img-0b41ea2/fp6-shim-ufs-root-touch-canvas.img`,
  SHA256 `5e8c0f7b8f47549f41a13af95b9bb1c2ad2db2e30928d6ad216beb535d6d3274`.
  Not booted yet.

## Stock SMMU clock prerequisites and battery protocol (2026-10-21)

- Patch0132 votes the four stock SMMU clocks in DT order, with bounded
  Linux branch halt/HWCG handling. It borrows only an already-powered CX
  domain and running hub parent; full regulator/RPMh/hub ownership is still
  needed if either is off. Context refusal is not successful translation.
  Agent reports host harness passed; no phone result or kernel build yet.
- Fuelgauge audit and transport-independent numeric GET protocol are in
  `docs/FP6_FUELGAUGE_AUDIT.md` and `xnu/protocol/fp6_battery_glink.h`.
  Stock reporting uses ADSP PMIC GLINK, not the old PM6150 polling path.
  No live transport or measured gauge readings exist yet.
- SpringBoard agent compared the local root catalog against original OS.dmg:
  matching SHA256 `0a53453f1e096f70ccb38618b0b8c32fa950f71dc3b559c4ce556825517aa04d`.
  This excludes corruption/omission of that local catalog, not a runtime
  rendition/trait lookup failure or a difference on the running phone.

## Gen8 firmware upload layer (2026-10-21)

- Added `xnu/helpers/fp6_gmu_loader.h`, staged alongside the pinned generated
  firmware by 0129. It follows KGSL Gen8 preallocation/TCM/external-copy
  semantics with explicit backing, reset-readiness and visibility callbacks.
  TCM indices use Gen8 GPU dword register indices, not guessed physical addresses.
  This is an unconnected implementation layer: live XNU allocation/SMMU mapping
  callbacks and startup integration remain required. No firmware execution or
  build/test result is claimed for this change.
- SpringBoard audit found the requested bounding-path name in the root catalog;
  the earlier runtime failure does not prove the catalog file is absent. Exact
  rendition lookup/decoding is under investigation; preserve statusbar geometry.

## FP6 exact SMMU refusal and SpringBoard capture (2026-10-21)

- Phone console photo reports `setup failed: register readback +0x22010
  want=0x00038011 got=0x00000000`: CB2 TCR2 did not retain the requested
  value. CBA2R/CBAR checks precede it and passed. Translation and GMU execution
  remain unproven; do not accept zero as successful setup. Investigating the
  Fairphone driver's SMMU power/clock and access prerequisites.
- CI `39630788262` succeeded for `69f987818adc6ebe628e8f453a1f10f668c7dd5f`.
  Local visible-console package:
  `/tmp/fp6-smmu-69f9878/image/fp6-shim-smmu-failure-visible.img`, SHA-256
  `bd604be97cf92049048ad5751efbad7663077b49a18c129a8f5ec1296cabc3b4`.
  Uses selected stock DTB, UFS root, existing ECM transport; no Tegu draft.
  Packaging checks passed. Photo alone does not independently identify its image.
- Passive USB capture `/tmp/fp6-blackboot-69f9878.pcap` recorded 4575 packets,
  zero capture drops. Capture filename is not proof of running kernel identity.
  Decoded packet text `/tmp/fp6-blackboot-packets.txt` shows repeated SpringBoard
  SIGABRT with `_UIScreenComplexBoundingPathUtilities` assertion: missing
  `BoundingPathBitmap-1125x2436-375x812-3.00x`. This establishes a userspace crash;
  it does not establish the cause of the reported gradual display darkening.
  Rootfs asset/identity investigation is separate from SMMU/GMU startup.
- Auth-to-Metal audit is in `docs/FP6_ADRENO_METAL_AUDIT.md`. UniXNU has a
  Darwin Turnip backend worth adapting. AirNir currently hard-gates generation7
  and its host script selects A740; FP6 needs the A810 target. This is source
  evidence, not an FP6 runtime result.

## FP6 CB2 test phone observation and failure diagnostics (2026-10-21)

- User's new console photo shows `context banks with nonzero state=0/22`,
  followed by `context test group=0 cb=2 mapped=0 contained=1 route_live=0
  bank_reserved=1 result=test failed; no master run`. Boot proceeds through
  platform registration and CPU startup at the shown point. This demonstrates
  that this attempt passed the earlier rollback panic site, but does not prove
  home-screen arrival or successful translation. The photo followed delivery of
  the atomic ATS image; its exact flashed/booted artifact is not independently
  established by the photo.
- No ATOS result or timeout appears between inventory and the failure summary.
  The likely exit is an earlier register-readback, fault-clear, or TLB-sync
  check. Previously these all silently entered rollback. Patch 0131 now caches
  the first failed offset, requested value and readback and reports them after
  cleanup, distinguishing readback mismatch, FSR clear failure and TLB timeout.
  It changes no register programming or acceptance criteria. Host tests verify
  each nonzero refused setup write reports its exact offset and never reaches
  ATOS; normal and ASan/UBSan suites pass. Firmware has not executed.

## FP6 atomic ATS image, existing ECM transport (2026-10-21)

- CI `39627541732` passed for `2a068b7c182bce5b11bf6bffe3b47d702683e3c4`.
  Downloaded kernel SHA-256
  `0b7a4b4c47fb28dc3275250241ab235065ffc672e82d18a5db16babb85d1f3db`
  matched its CI SHA256SUMS before packaging.
- Packaged `/tmp/fp6-smmu-2a068b7/image/fp6-shim-ufsroot-smmu-atomic.img`,
  SHA-256 `bec67541d4c5d0b08d985f03e65201004aa833d9e4741fc9ee04ea94b8e6a9c4`.
  Uses the verified selected FP6 stock DTB (`81985341...`), UFS root,
  `fp6smmu=2`, `fp6usb=2`, `fp6touch=2`, `fp6pas=1`, eight CPUs and quiet
  console defaults. Header-v2 payload/shim/DTB round-trip checks passed.
  No Tegu transport changes are included; no phone test has run.
- Work on an EP0 host-pull log console is an external draft only:
  `/tmp/fp6-usb-ep0-log-console.draft.patch`. It sketches an EP0-only mode3,
  serial-callback polling and deferred SMMU test after USB startup. It is not
  in the patch series or any kernel/image. Host reader, protocol tests, deferred
  test harness stubs and full kernel validation remain unfinished. Do not apply
  it unchanged. The firmware port remains incomplete: no GMU execution yet.

## FP6 atomic ATS correction and reference correction (2026-10-21)

- Source inspection found a protocol error in patch 0131: AArch64 ATS1PR was
  issued as two 32-bit stores. Fairphone `arm-smmu-qcom.c` explicitly requires
  an atomic ATS1 access and uses `arm_smmu_cb_writeq`. The FP6 helper now uses
  one aligned volatile 64-bit store with the existing ordering barriers. The
  harness rejects split ATS writes and verifies one 64-bit request. This does
  not establish the cause of the photographed CBAR external abort.
- Corrected the preceding audit's mistaken Gen7.11 identification. The selected
  FP6 stock tree (`8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`)
  explicitly selects `qcom,adreno-gpu-gen8-3-0`. Fairphone's matching
  `adreno_gpu_core_gen8_3_0` uses `gen80300_{gmu.bin,sqe.fw,zap.mbn}` and
  `adreno_gen8_hwsched_gpudev`. Gen7.11 is another supported module profile,
  not the FP6 hardware profile. Use `adreno_gen8_gmu.c` for runtime loading.
- The same stock tree supplies the GPU QTB500 TBU at `0x03de8000/0x1000`,
  covering SIDs `[0,0x400)`. This identifies the SID5 ECATS target; its power,
  halt/resume, ownership and register access remain untested.
- PAS state correction: patch 0127 implements an opted-in ZAP load; the earlier
  phone observation recorded successful INIT_IMAGE, MEM_SETUP and AUTH_AND_RESET.
  `fp6pas=1` alone remains a query; `fp6zap=1` requests the authenticated load.
- CI `39625922013` passed on `2582fe6`. Its locally packaged image
  `/tmp/fp6-smmu-2582fe6/image/fp6-shim-ufsroot-smmu-cbarfix.img` has SHA-256
  `9918c0219c91414234942b761d7c9555cbad76a2df8d477ddab28ec7c20f96f8` and was
  not phone-tested. It predates the atomic ATS fix and is superseded for live
  SMMU testing. It embeds the complete vendor_boot DTB collection (SHA-256
  `16a9e60e...`); subsequent packages should use the verified selected tree
  above, matching prior tested packages. No GMU execution is claimed.

## FP6 SMMU rollback panic containment (2026-10-21)

- Phone observation: the `fp6smmu=2` GMU SID5 ATOS test panicked in rollback.
  The photographed state shows PC `0xfffffe0007ae71c0`, LR
  `0xfffffe0007ae6f64`, FAR `0xfffffe30000e1000`, ESR `0x96000010` (synchronous
  external abort). Symbolication against the matching CI kernel places PC in
  `fp6_smmu_inventory` at the write restoring the selected context bank's CBAR.
  This is strong address-level evidence for the panic site; the earlier reason
  the test entered rollback remains unknown. GMU firmware was never released.
- Patch 0131 now avoids writing CBAR/CBA2R during rollback. It leaves the
  candidate bank configured but disabled (`SCTLR=0`), invalidates the temporary
  stream match, restores the fault route, and intentionally reserves the bank
  and permanent page-table allocation for the rest of that boot. The probe now
  selects CB2 or higher, matching Linux's reservation of CB0/CB1 for GPU
  pagetable switching. The host
  harness verifies that success and each injected setup failure leave no active
  stream match. Normal and ASan/UBSan GPU probe tests pass. This is a source
  change and containment hypothesis only; no rebuilt image or phone result yet.
- Fairphone KGSL/SMMU cross-check (hardware profile corrected above): the current
  `fp6gpu=1`/`fp6pas=1` modes inventory GPUCC and query PAS availability. A
  separate `fp6zap=1` mode implements ZAP authentication, phone-confirmed earlier.
  Linux's QSMMUv500 path allocates CB0/CB1 to GPU SID0/1 and other clients from
  CB2 onward; patch 0131 now respects that rule. Its CBAR/TCR/TTBR/MAIR ordering
  follows `arm_smmu_write_context_bank`, but the probe's fixed SCTLR `0x27` is
  not Linux's complete fault/coherency setup.
- Important limit: patch 0131 triggers CB `ATS1PR`, which checks context-bank
  page translation but does **not** prove the SID5 stream route end to end.
  Fairphone QSMMUv500 resolves SID-specific ATOS through the corresponding TBU
  ECATS path (halt TBU, disable fault/stall handling temporarily, trigger ECATS,
  inspect/clear FSR, restore SCTLR, resume). Thus the test output is now named
  context-bank ATOS, and SID5 routing remains unverified. The next proper route
  test needs exact FP6 TBU mapping/ownership and a bounded ECATS sequence.
- The Tensor progress screenshot describes user-space AIR shader compilation,
  pipeline import and texture setup, with no compositor draw yet. Those are
  meaningful user-space milestones but do not transfer as a percent-complete
  estimate for FP6: this tree has not started GMU firmware execution, SQE/CP,
  GPU submission, or a Metal bridge.
- Tegu USB source review: `shim/tegu/usb.c` is a pre-XNU polled DWC3 EP0 gadget;
  Tegu also carries the transport into XNU via patch 0088 so its console can
  collect later XNU output. Its shim and XNU versions rely on Tegu-specific
  DWC3/eUSB PHY addresses, firmware handoff, DMA RAM and `cpus=1`; they cannot be
  copied to FP6 as-is. The host reader uses USB control requests to retrieve a
  buffered log. An FP6 adaptation may provide a panic-safe path independent of
  the current ECM logger, but must first establish FP6 controller/PHY ownership
  and DMA constraints.

## FP6 SMMU live-test kernel data abort (2026-10-21)

- User reported `kernel data abort` with PC `0xfffffe0007ae71c0`, LR
  `0xfffffe0007ae6f64`. Against the kernel from CI run `39618365269`, PC resolves
  inside `fp6_smmu_inventory`; instruction disassembly places it at the MMIO
  store restoring the candidate context bank's old CBAR during rollback. The
  image manifest for that run records `hardware_tested: false`; matching this
  report to that image is not yet confirmed.
- The rollback had already restored the old SMR, disabled the context bank,
  and restored S2CR before reaching CBAR. FAR and ESR were requested to
  distinguish an access fault from a hardware/external abort and establish the
  exact register address. Do not treat this as a GMU firmware failure: CM3 was
  never released.
- Cross-checking Fairphone Linux `arm_smmu_write_context_bank()` found that
  the probe programmed TCR/TTBR/MAIR before CBA2R/CBAR, unlike Linux's
  CBA2R -> CBAR -> TCR2/TCR -> TTBR -> MAIR -> SCTLR order. Patch 0131 and the
  stage-failure harness were reordered to match Linux. This source correction
  is not yet built or phone-tested and does not, by itself, explain the abort.

## FP6 SMMU fault-route selection fix (2026-10-21)

- The user's boot photo from `fp6smmu=2` shows all visible stream groups have
  `SMR=0`, fault routing, and `S2CR=0x00020000`; SID 0/2/5 have no valid visible
  match, and all 22 context banks read clean. The probe refused before any
  programming because it required the whole S2CR to equal `0x000200ff`.
- Corrected free-group selection to test only `S2CR.TYPE == FAULT`; CBNDX is
  irrelevant for a fault route. Host coverage now models the observed
  `0x00020000` value through successful ATOS mapping and rollback.
- `tests/test_gpu_probe.py` passes normally and under ASan/UBSan.
- CI run `39615067086`, source `67f9abdf09067f7cffa2fe1ef16494dbb937e068`,
  ultimately completed successfully; XNU build passed. Automated image
  packaging was skipped because `FP6_STOCK_DTB_URL` is unset. The previous
  local test image at `/tmp/fp6-run-39615067086-image/fp6-shim-smmu-atos.img`
  used the still-unfixed probe and was not a valid SMMU programming test.
- The corrected source is not yet built by CI or tested on the phone. Next:
  publish the focused patch, confirm its XNU build, package with the matching
  stock DTB, then rerun the SID 5 ATOS check. The GMU remains held in reset;
  no firmware has been loaded or executed.

## FP6 Gen8.3 GMU firmware staging and SMMU inventory draft (2026-10-21)

- The local Fairphone kernel modules tree is the hardware reference. Its
  `adreno_gen8_gmu.c` confirms Gen8 firmware blocks are loaded into ITCM/DTCM
  or backing memory from zero-size preallocation records; HFI and CM3 startup
  are still separate stages. The XNU port does not yet consume the generated
  firmware header or start CM3.
- Added `tools/fp6-gmu-fw.py`, pinned to FairBlobs commit
  `e58a5be8fa0fb6bc5a5f2e29cc01c036ccf75710` and SHA-256
  `6adcbf43b162fb4bdc00154824f44c5f96d82a223cfbe7012d5904098f5bf2fc`. It
  validates the 88,708-byte Gen8.3 GMU image and emits 11 preallocation
  descriptors plus four data blocks into a generated header. The firmware
  itself remains outside Git. `0129-stage-fp6-gen80300-gmu.sh` stages that
  header in FP6 CI builds; it is not wired into a runtime loader yet.
- Repaired `0128-fp6-qsmmu-readonly-inventory.patch` and extended the host
  harness to check that `fp6smmu=1` reads SID 0/2/5 routing and context-bank
  registers without MMIO writes. This models the diagnostic only; the actual
  FP6 SMMU window has not been read by this build or tested on the phone.
- Host GPU probe suite passes, including the new SMMU inventory case; the six
  GMU firmware parser tests pass and the staging shell script is tested against
  the local pinned blob. CI runs `39588975030` and `39589703230` stopped in
  staging: the parser path was wrong, then macOS Bash 3.2 rejected an empty
  array under `set -u`. Run `39590152515` passed staging but found the inventory
  calling a SWEET-only MMIO helper; an FP6-local ordered read helper is now in
  place and host tests pass. A follow-up CI run is pending. No GMU firmware has
  been loaded and no GPU commands have executed.

## FP6 PAS/ZAP retest image (2026-10-21)

- CI run `39583564215` completed the corrected kernel build for commit
  `2c6ab5ee519f433b899616217eb9d74f9a2b57b3`. The kernel checksum verified;
  the matching ADT SHA-256 is
  `50247d49f727ef9b2b588c2522250bed4d3b742d139ed2d994ffe79634823a65`.
  The workflow skipped boot-image packaging because `FP6_STOCK_DTB_URL` is not
  configured, so the matching CI kernel and ADT were packaged locally with the
  verified stock `tree-04.dtb` and minimal init ramdisk.
- Temporary image:
  `/tmp/fp6-zap-39583564215/image/fp6-shim-fp6zap-fixed.img`, SHA-256
  `94036ddf12326342ed7432cbd570aa7aac0ee3048ef0a51ae25f5190a6c97644`.
  It enables `fp6gpu=1 fp6pas=1 fp6zap=1 fp6touch=2 fp6usb=2` and includes the
  mapped-virtual-address cache-clean fix for the prior `phystokv_range` panic.
- User-provided console photo from this image confirms the phone reached all
  three firmware stages: `PAS_INIT_IMAGE fid=0xc2000201`,
  `PAS_MEM_SETUP fid=0xc2000203`, and `PAS_AUTH_AND_RESET fid=0xc2000205` each
  returned `smc=0x0 result=0x0`; the kernel then reported “GPU ZAP authenticated
  and reset; PAS remains active.” This validates the SMC route, metadata and
  image mapping, cache-clean fix, TrustZone authentication, and peripheral
  reset on FP6. The screenshot also shows the touch/HID and framebuffer
  services registering. The log was captured from the screen, not a host pcap.
  GMU CM3 startup, HFI, GPU SMMU configuration and command execution remain
  untested.
- A fresh `fastboot devices` check after the report returned zero devices, so
  no further boot was attempted in this turn.

## FP6 quiet-console package defaults (2026-10-21)

- Updated `tools/fp6-package.py` so every generated FP6 image omits
  `-enable_kprintf_spam` and enables `sweetfb_noconsole=1`,
  `sweet_noconsole=1`, and opts in to `fp6pas=1`. This keeps the normal
  framebuffer free of routine kprintf output after the first GUI swap. The
  PAS code only queries SMC call availability and GPU PAS support; it does not
  load/authenticate firmware or touch GPU registers. The kernel ring and
  USB logger remain enabled; panic output is still allowed to draw, and output
  before the GUI swap may still appear on screen. This is a package-default
  change only; it does not alter the kernel.
- Locally packaged the latest successful FP6 kernel from CI run `39569106154`
  (kernel SHA-256 `601288b0a5ae4ac1af9d870a269673205be1856b75f72f7da48131c809bdf100`),
  reusing that run's ADT and stock DTB. The first quiet image omitted
  `fp6touch=2`; that would skip the live touch-driver start. The package
  default now includes it. A corrected diagnostic image with the framebuffer
  console visible (so `QCOM SCM:` output is visible) is:
  `/tmp/fp6-debug-pas-touch-39569106154/fp6-shim-ufs-root-pas-touch-visible.img`,
  SHA-256 `667423e85a0139acab9203ce824bbc4fbfc5a2ce2b657cd515691fa324765f59`.
  Its arguments include `fp6pas=1 fp6touch=2 fp6usb=2`, and omit
  `-enable_kprintf_spam` and the framebuffer mute args. It uses the same
  latest successful kernel and matching ADT/DTB. Header-v2 contents validated;
  it was temporarily booted once after the user said the phone was ready.
  USB capture decoded 448 packets. The console showed `PAS_IS_SUPPORTED`
  advertised and GPU PAS ID 13 supported=1, followed by the FP6 touch driver
  polling at 1116x2484. The user confirmed touch responds. This proves only
  the read-only PAS query; no firmware load/auth/reset or GPU register access
  occurred. Captures are retained outside Git under `/tmp/fp6-kernel-logs`.
- Earlier quiet image (retained for reference):
  `/tmp/fp6-quiet-local-39569106154/fp6-shim-ufs-root-quiet-pas.img`, SHA-256
  `5798d5592286aebf569f5a45c0a33107bc2a1058dad317adabdc78387755dc7c`.
  It had `fp6pas=1 fp6usb=2`, kprintf spam off, and framebuffer mute enabled;
  the live touch argument was absent.

## Codex Adreno/PAS work merged into main (2026-10-21)

- Merged the uncommitted `fp6-adreno-gen711` working state (Codex): patch
  0118 (FP6 GPUCC inventory, opt-in), its PAS query patch renumbered from
  0119 to **0122** (main already had 0119-0121), and its NOTES, docs and
  host-test changes. The two patches touch only sweet_gpu.c/sweet_ufs.c and
  apply after 0119-0121.
- Fixed before any phone use: the PAS patch called SMC FID 0xC2000101 as
  "is call available", but that is SIP service 0x01 (BOOT) function 0x01,
  `QCOM_SCM_BOOT_SET_ADDR`; the query is SVC_INFO 0x06 / IS_CALL_AVAIL 0x01
  = **0xC2000601** (Fairphone `drivers/firmware/qcom_scm.h:111-147`). The
  host test's expected FID was corrected likewise. PAS_IS_SUPPORTED
  0xC2000207 (PIL 0x02 / 0x07) was already correct. Disassembly of the local
  arm64 object shows `smc #0` with x0=0xC2000601, x1=1, x2=0x02000207, then
  x0=0xC2000207, x2=13. The phone query result above matches the expected
  SMC path.

## FP6 Adreno 810 profile correction (2026-10-21)

- Correction from reinspection of the actual `~/Downloads/vendor_boot.img` DTB
  and the linked LineageOS devicetree: FP6 is `qcom,adreno-gpu-gen8-3-0` with
  Volcano GPUCC. GPU is `0x03d00000/0x40000`, GPUCC is
  `0x03d90000/0x9800`, GMU windows are at `0x03d68000`, `0x0b280000`, and
  `0x03d40000`, GPU IRQ SPI 300, GMU IRQ SPIs 304/305, and a dedicated
  `qcom,qsmmu-v500` GPU SMMU at `0x03da0000`. Volcano's GPU DT `iommus`
  properties give stream IDs 0 (user GPU), 2 (secure GPU) and 5 (GMU), all with
  zero masks; these are not context-bank indices. The TBU range is still broad
  (`0..0x3ff`), while those client tuples provide exact SIDs. Runtime S2CR/CB
  ownership and Gunyah's access policy remain unverified.
- Source revisions inspected: LineageOS devicetrees `lineage-23.2` at
  `f32428ad60a7bf1ad04f9a8a001f27842e65fd79`; Fairphone kernel modules at the
  current local checkout; FairBlobs FP6 firmware at `e58a5be8fa0fb6bc5a5f2e29cc01c036ccf75710`.
  The matching Fairphone KGSL profile in the local kernel modules tree is Gen8.3
  and names `gen80300_gmu.bin`, `gen80300_sqe.fw`, and `gen80300_zap.mbn`. The
  public FairBlobs FP6 firmware tree contains these blobs (88,708 / 84,564 /
  12,088 bytes; SHA-256 `6adcbf43b162fb4bdc00154824f44c5f96d82a223cfbe7012d5904098f5bf2fc`,
  `38fd00147e8b752dd29c53a0badac8f94b1dbd89dc06f5b1c372d3428cd1b906`, and
  `a91c411027746d4c3389a69b66f25d21eb646e89f2de5eed3f698e370f83f26c`). These
  downloaded blobs remain in `/tmp` and are not in Git. The earlier Murena
  Gen7.11 filenames belong to a different/older software profile and are not
  selected by this DT compatible. The signed Zap image requires Qualcomm
  PAS/TrustZone authentication; it is not ordinary firmware copying.
- UniXNU organization inventory via GitHub API found: UniXNU, UniXNU-sheng,
  uefi-sheng, ArmCpu, ArmDTPlatform, ArmVirtPlatform, DarwinBoot, NativeAES,
  NativeAdreno, NativeGeniSpi, NativeHidInput, NativeKeyStoreEvents,
  NativeMetal, NativeMobileDisplay, NativeRamBlock, NativeUfs,
  NativeVirtioBlock, NativeVirtioConsole, AdrenoFirmware, AdrenoPM4, AirNir,
  ArmSmmu4K, NativePrelink, VerifiedRoot, NativeNovatekTouch,
  ShengPreflight, and `.github`. NativeAdreno, PM4, AirNir and the display
  Adreno/PM4 and AirNir paths target Sheng/A740; their board profiles and
  instruction encoders are not FP6 drop-ins. NativeMobileDisplay demonstrates
  a CPU framebuffer-copy service, rather than GPU acceleration. ArmSmmu4K and firmware/HFI parsing are the
  strongest pieces to study for a later port, subject to FP6 geometry and
  protocol validation.
- Local patch `0118` adds an opt-in `fp6gpu=1` read-only inventory of 11 Volcano
  GPUCC branch registers (base/size and offsets corrected to the exact DT and
  `gpucc-volcano.c`). The inventory patch itself has not yet been rebuilt or
  phone-tested after this correction. It maps no GPU-core, GMU, or SMMU windows and performs
  no writes, power/clock requests, DMA, or firmware startup. It is diagnostic
  groundwork only; no acceleration is enabled yet. Host model tests pass both
  normally and with ASan/UBSan (`ASAN_OPTIONS=detect_leaks=0` is needed because
  LeakSanitizer cannot operate under this test runner's ptrace sandbox); RPMh
  and XNU-compile-log helper tests also pass. An AArch64 Clang syntax check
  with lightweight XNU header stubs passed. The patch applies to the accumulated
  GPU source; no full XNU CI build or phone inventory test has run for 0118.
  This work is on `main`; no phone GPU inventory test has run.

## FP6 Qualcomm PAS query (2026-10-21)

- Patch `0122` adds an opt-in `fp6pas=1` QCOM SCM query during early boot
  setup. It asks SCM whether `PAS_IS_SUPPORTED` is advertised, then queries
  PAS peripheral ID 13 (GPU). It does not load Zap, initialize/authenticate a
  PAS image, reset a peripheral, map GPU memory, or touch GPU/GMU/SMMU MMIO.
- The SMC IDs, SIP owner, argument encoding, and PAS query order were checked
  against the cloned Fairphone Qualcomm kernel's `qcom_scm.c` and
  `qcom_scm-smc.c`; the GPU PAS ID and Zap flow were checked in its KGSL
  Adreno loader. XNU's PSCI `smc #0` helper is the only existing local SMC
  precedent; this does not establish that the direct SIP SCM route is accepted
  on FP6 (the vendor kernel also has a QCPE/HAB transport branch).
- Host model tests cover disabled/invalid modes, service-unavailable and SMC
  error paths, and the exact two successful query descriptors. The local
  harness and ASan/UBSan GPU harness pass. CI build 39569106154 included this
  patch; the phone result is recorded above. It is still query-only.

## FP6 Adreno startup and signed ZAP loader draft (2026-10-21)

- User clarified that GPU bring-up must not be attached to UFS initialization.
  Patch 0127 moves the FP6 GPU inventory and PAS query into a dedicated
  `EARLY_BOOT` startup hook in `sweet_gpu.c`; UFS no longer owns those calls.
- Patch 0126 fetches `gen80300_zap.mbn` from FairBlobs commit
  `e58a5be8fa0fb6bc5a5f2e29cc01c036ccf75710`, verifies its SHA-256, validates
  the ELF32/QDSP6 program-header and relocatable-segment layout, then emits
  only the signed-image metadata and segment into a generated header. The
  firmware binary remains out of Git.
- Patch 0127 adds opt-in `fp6zap=1`: check PAS availability/support, write the
  metadata into the second page of the stock 8 KiB no-map Zap carveout, call
  PAS_INIT_IMAGE, copy/zero the relocatable 4 KiB image page, call
  PAS_MEM_SETUP and PAS_AUTH_AND_RESET, and call PAS_SHUTDOWN on failure.
  Successful PAS state remains active. This does not start the GMU, map or
  program the GPU SMMU, or execute GPU commands.
- The staging script passed against the local blob (SHA-256
  `a91c411027746d4c3389a69b66f25d21eb646e89f2de5eed3f698e370f83f26c`),
  producing a 0xfcc-byte Linux-compatible metadata buffer and 0x378-byte
  segment. Host GPU harness and full four-test suite pass, including
  ASan/UBSan; `git diff --check` passes. These changes have not yet had a full
  XNU CI build or a phone test. PAS authentication is therefore not proven.

## FP6 touch, HID services and ring switch (2026-10-21)

- Patches 0115 (SweetHID button/touch services registered on FP6, touch
  geometry from the boot framebuffer), 0116 (ring/silent switch as Telephony
  RingEnable via `sweet_hid_key(4)`, position returned by copyEvent and sent
  to new clients) and 0117 (`bsd/dev/qcom_geni.c/.h` polled GENI FIFO/SPI
  core; `bsd/dev/fp6_touch.c` ESWIN EPH86xx on SE0 SPI mode 3 ~1.9 MHz CS0,
  vendor TLV protocol, X inverted on 1116x2484, GPIO 107 slider to the ring
  switch; `fp6touch=1` read-only probe, `fp6touch=2` live). Hardware facts
  re-checked against Fairphone kernel sources: Volcano TLMM REG_BASE
  0x100000 (GPIO n at 0x0f100000+0x1000n, 168 GPIOs), SE0 pins 0-3 func 1,
  GCC vote 0x52008 bits 18-22, halts 0x23018/0x23008/0x23000/0x23004/0x18004,
  non-DFS RCG 0x18010 with XO in its table, FIFO full-duplex opcode 3.
  The repo's earlier Cliffs TLMM description (179 GPIOs, reserved 56-60) and
  "SPI pins 94-97" are wrong for FP6 and not used by this driver.
- Local arm64 compile (system clang, CI flags via xnu-cc replay) passed for
  the new files and SweetHID.cpp. CI `39554419254` (head `43fdbd7`) build
  job passed; kernel SHA256SUMS verified, symbols present.
- Image (wifimac ADT, console muted, `fp6touch=2`):
  `/tmp/fp6-touch-39554419254/img/fp6-shim-ufs-root-touch.img`, SHA256
  `39175f461e09eeb9dd2f1af9ecf225841cee49f28646f4a9ff8345820ffbf6b0`.
  Temporarily booted 06:23:21 UTC (`fastboot boot` OKAY). Phone result (screen
  photos): SE0 `fw=0x102 proto=1 if_disable=0x1 status=0 hw=0x202029e4/...
  dma=0x1 mclk=0x11 clksel=0`: SPI firmware is loaded but FIFO mode is
  disabled (GSI/GPI DMA only), so `qgeni_fifo_init` refused (err 19).
  Clock bring-up worked: initial vote 0x52008=0x40000900, RCG 0x18010 root
  off (0x80000000, cfg 0x100000) -> rcg 0, cfg 0x100001 (XO); branch 0x18004
  0x80004000 -> 0x4000; 0x23018/0x23008=0x4000, 0x23000/0x23004=0. TLMM:
  gpio0/1 cfg 0x203 (GPIO out high, pull-up), gpio2/3 cfg 0x1 io 0, gpio19
  (CHG) cfg 0x1 pull-down io 1, gpio20 (reset) cfg 0x1 input pull-down io 0
  = controller held in reset, gpio107 (slider) cfg 0 no pull io 0 =
  floating (DT wants pull-up). SweetHID works: `key 0xb/0x2d down (1
  clients)` after `FP6 SLIDER: gpio107=0 -> ringer`. No controller access happened (the check
  precedes any SPI transfer). Stock Volcano DT wires SE0 SPI to GPI DMA
  (`gpi_dma0` @0xa00000, SID 0x576, gpii-mask 0x3e, static-gpii-mask 0x01;
  QUP wrapper SID 0x563), so FIFO-disabled GSI firmware is the leading
  explanation, now confirmed. Chosen direction: a polled GPI DMA path in
  qcom_geni (research in progress).
- Patch 0119 adds a polled GPI DMA (GSI) path to qcom_geni, used when SE
  firmware disables FIFO (as on FP6 SE0): read-only GPII 0 state check
  (refuses unless both channel and event contexts are zero), SMMU stream
  pass-through for SIDs 0x576/0x563 (accepts existing bypass or
  unmatched-stream bypass, else adds a Linux-style S1_TRANS_S2_BYPASS bank),
  16 KiB contiguous DMA (event ring 2 KiB, TX/RX rings 1 KiB, bounce
  buffers), Linux msm_gpi sequence (IRQ-status config, EV ALLOCATE, CH
  ALLOCATE x2, program, START x2) and per transfer CONFIG0+GO+TX DMA / RX DMA
  TREs with EOT polling. The touch driver now also sets GPIO 107 and 19 to
  pull-up inputs and releases reset on GPIO 20 (low 10 ms, high, 300 ms).
  Local arm64 compile passed. CI `39556553401` (head `9cdc23a`) build
  passed; kernel SHA256SUMS verified. Image (wifimac ADT, console muted,
  `fp6touch=2`): `/tmp/fp6-gpi-39556553401/img/fp6-shim-ufs-root-gpi-touch.img`,
  SHA256 `85424b1ece61a39be62d9c97c91089bbf8bb7e884b168c94b0b416cb43f8b54d`,
  temporarily booted 06:43:30 UTC. Result: kernel data abort at PC
  0xfffffe00074f57f0 (LR 0xfffffe00074f5738) = `qgeni_smmu_passthrough+0xe8`,
  the first SMR load of the stream-match scan (SMMU base + 0x800 + 4i); the
  sCR0/IDR0/IDR1 loads before it completed, so the GPII 0 idle check had
  passed. FAR/ESR not captured. Unlike sweet_ufs.c, which reads the same
  SMRs on this phone, the new scan did not cap the IDR0 group count at 128.
- Patch 0120 caps the SMR scan at 128 groups as sweet_ufs.c does and logs
  sCR0/IDR0/IDR1 before scanning (diagnosis is source-based until the next
  boot). Patch 0121 adds `bsd/dev/fp6_keys.c`: read-only polling (20 ms, two
  equal samples) of PMK8550 PON_RT_STS 0x1310 (bit 7 power, bit 6 volume
  down; GEN3 subtype 0x09 checked at 0x1305) and PM7550 GPIO 6 RT_STS
  0x8d10 bit 0 (volume up, active low; used only if EN_CTL bit 7 and
  digital-input mode) through the v7 arbiter observer channel for EE 0
  (core 0x0c400000 APID map +0x2000+4n, cnfg 0x0c42d000 owner +4n, obs
  0x0c440000 +0x20*apid; offsets checked in spmi-pmic-arb.c). The only MMIO
  write is the observer read command; `fp6keys=0` disables. Both compile
  locally.
  CI `39557553973` (`9d9f1de`, before the Codex merge) passed. Image with
  console visible and `fp6touch=2`:
  `/tmp/fp6-keys-39557553973/img/fp6-shim-ufs-root-touch-keys-console.img`,
  SHA256 `7008124cc16249af752d318806fef60efba97df12360f832aa27eaef8ee2abcc`,
  temporarily booted 06:59:58 UTC. Result: same data abort, PC
  0xfffffe00074f5810 (`qgeni_smmu_passthrough`, SMR scan, already capped).
  Panic registers: FAR = SMMU map base + 0x800 (SMR 0, first entry), ESR
  0x96000010 (EL1 data abort, DFSC 0x10 synchronous external abort), sCR0
  0x00230406 (USFCFG set: unmatched streams fault), IDR0 0x4c017e72 (114
  SMRGs), IDR1 0x60000048 (72 banks, 4 KiB pages). The faulting load was
  post-indexed (`ldr w15, [x14], #4`); the preceding sCR0/IDR loads used
  plain base+offset and succeeded. Diagnosis: the apps SMMU is trapped by the
  hypervisor, which cannot emulate write-back loads (no valid instruction
  syndrome) and injects an external abort; sweet_ufs.c's SMR loop compiled
  to plain loads. The 128 cap (0120) was not the cause.
- Patch 0123 makes the rd/wr MMIO accessors in qcom_geni.c, fp6_touch.c and
  fp6_keys.c single inline-asm LDR/STR with a plain base register. Local
  objects contain no write-back loads/stores to MMIO (remaining write-back
  forms are stack pushes, a const-table load and buffer copies). Because
  sCR0.USFCFG=1, the GPI streams need SMR/S2CR entries; whether the
  hypervisor accepts those writes is unknown (readback is checked).
  CI `39559458529` (`a24dc47`, includes the Codex merge) passed. Images
  (console visible, `fp6touch=2`): touch+keys
  `/tmp/fp6-mmio-39559458529/touch-keys/fp6-shim-ufs-root-touch-keys-console.img`
  SHA256 `0c592511eebde58a5fba6afed8728415b73eeeeaf37930b53b83981da381c20c`,
  temporarily booted 07:12:27 UTC. **User reports touch and buttons work**
  (first FP6 input: SE0 SPI through GPI DMA with SMMU stream entries via the
  hypervisor-trapped MMIO, PMIC keys through the v7 SPMI observer channel);
  SpringBoard then crashed (signal/reason not yet reported). Leading
  suspect from SWEET history: patch 0070 (`pid_hibernate`, syscall 435) was
  SWEET-only, so SpringBoard gets SIGSYS when an app leaves the
  foreground; 0070's two guards now include FP6 (source fix, unconfirmed);
  user also reports Settings -> General -> About crashes (as on SWEET:
  PodcastsUI force-unwrap of `URL.volumeTotalCapacity`, diagnosed there, not
  fixed) and apps show black windows (SWEET: e.g. Phone blocked in a sync
  voicemail XPC that needs the modem). 0099's sweet_sample.c guard and new
  patch 0124 enable SWEET's process sampler on FP6, opt-in via
  `sweetsample=Name,...` (output is console/log only); same plus `fp6pas=1`
  `/tmp/fp6-mmio-39559458529/touch-keys-pas/fp6-shim-ufs-root-touch-keys-pas-console.img`
  SHA256 `9fbaab46e356761bf2519b0d7df4738571bc366b338a442386390fb450770957`
  (not booted). The stock DT confirms the Gunyah hypervisor
  (`gunyah_hyp_region@80000000`, trustedvm/oemvm guests). Rails
  (L22B/L9B) and PMIC are still untouched. Work is committed from a separate
  worktree on main because the shared checkout is on Codex's
  `fp6-adreno-gen711` branch.
  The driver does not touch reset, L22B/L9B or PMIC; slider polarity
  (mainline: GPIO 107 high = muted) is unverified.

## FP6 home screen (2026-10-21)

- **User reports the iOS home screen on FP6** after booting
  `fp6-shim-ufs-root-wifimac-console.img` (`5ebfd2d5...`): kernel from CI
  `39550549760` (`b8ad3fe`: 0031/0039/0042/0043/0048/0052/0059 on FP6), ADT
  with the D22AP identity and `/chosen/mac-address-wifi0` (`96baa92`), stock
  DTB, console left visible. Root: the freshly flashed Tegu-built image
  (`fp6-ios-root-tegu.simg` `a1c6f7da...`, raw `574cbad6...`) on `userdata`, per
  the user; its first boots therefore used the D22AP identity.
  Touch/buttons have no FP6 HID driver (no SweetHIDButtons/SweetHIDTouch on
  FP6), so interaction is not established.
- Same kernel/ADT repacked with the default arguments (console muted after the
  first swap: `sweetfb_noconsole=1 sweet_noconsole=1`):
  `/tmp/fp6-fixes-39550549760/img-home/fp6-shim-ufs-root-home.img`, SHA256
  `1a7f40b4e66d03fcb44ec5442c7d6e74ee2a60eabc33d405887e33433cb6f40b`.
  Header-v2 validation passed; not yet booted.
- The Wi-Fi MAC is a fixed stand-in. The stock DTB has no static MAC; ABL's
  runtime FDT `/chosen` has not been inspected. The DTB names both a PCIe
  Kiwi path (`wlan/qca_cld/kiwi_v2`) and `qca6750/wpss.mdt`; the actual WLAN
  part is unconfirmed.

## FP6 userspace stall after early boot (2026-10-21)

- Phone observation (user report, image from CI run `39545845250`): libignition
  at `ignition_level=1` prints "failed to write persona, ignition level
  insufficient" (a skipped stage, as on SWEET) and continues; level 3 fails on
  the missing Preboot volume, as on SWEET. Boot then reaches early boot
  complete: bindfs firmware mount message, MKB init passes, "Could not get
  options entry from the device tree" (no NVRAM node, also on SWEET), a
  bluetoothd/xpcproxy relaunch loop (no hardware, also on SWEET), `logd
  privilege 1002 denied` (0064 log), MobileGestalt AKS/IOKit call returning 0.
  No backboardd activity and no `SWEET SURF` lines.
- Source audit against SWEET's working path found FP6 lacked: the iPhone X
  identity (ADT root `FP6`, chip-id `0x7635`, no security-status or
  `display-scale`; 0059 kept the macOS `hw.machine`/`hw.model`), 0052
  RENAME_SWAP fallback (the fix before SWEET's backboardd milestone), 0031
  `rootrw=1` (passed by the FP6 package but compiled out), 0039 core dumps off,
  and the 0042/0043/0048 exec/crash/tee diagnostics.
- Commit `5e9a9a0` widens those patch guards to FP6; `90f6c55` gives the FP6
  ADT Sweet's D22AP / iPhone10,3 / D22 identity, chip-id `0x8015`, the
  security-status tuple and `display-scale` 3. The `disp0` canvas stays
  1116x2484 because AppleCLCD reports the native size when the panel is taller
  than 2436. `b043585` commits the pending 0041 HFS diagnostic cap for FP6.
  Local arm64 compile was not possible (no Apple clang here); CI is the build
  check.
- ADT-only test image (old kernel from CI `39545845250`, new local ADT with
  `/product`, stock DTB `16a9e60e...`, default UFS-root args):
  `/tmp/fp6-identity-39545845250/fp6-shim-ufs-root-identity.img`, SHA256
  `33e7f7c2624d45864408a374074a841c7bcd0a42a8b890175750bc362cf57420`.
  Header-v2 validation passed; not yet booted. It tests the ADT identity
  without the 0059 `hw.machine`/`hw.model` change or the other kernel fixes.
  A MobileGestalt cache written under the old FP6 identity may need clearing.
- CI run `39550549760` (ersascape/ios-extra, head `b8ad3fe`) passed: build and
  fp6-boot jobs green. Kernel SHA256SUMS verified; the build tree carries the
  FP6 guards in kpi_vfs.c, kern_mib.c, exception.c, kern_exec.c and
  vfs_subr.c, and the kernel contains the exec/CRASH/dirty-root strings.
  Packaged with the D22AP ADT (`dee5539e...`) and stock DTB:
  `/tmp/fp6-fixes-39550549760/img/fp6-shim-ufs-root-fixes.img`, SHA256
  `0129b2855762bf0b0f12c051fdc17ab7c735566880f85a11ec221578033e493f`,
  kernel `b894d3fc...`. Header-v2 validation passed; not yet booted.
- The never-booted Tegu root (`fp6-ios-root-tegu.simg` `a1c6f7da...`, raw
  `574cbad6...`) re-verified against the hashes above; it has no MobileGestalt
  cache and has the migration marker. Tegu's history shows a cache written
  under a wrong identity breaks SpringBoard until a clean root is used, so
  the clean root should first boot with the D22AP ADT. Not flashed.
- Phone observation (user): the fixes image showed a solid Apple logo (backboardd
  presenting; no progress bar, no flicker) and stayed there. Tegu hit the same
  stall: lsd's database seeding waited in MobileGestalt for a Wi-Fi identity
  (it reads `/chosen/mac-address-wifi0` first), so SpringBoard never drew;
  adding that CFData fixed it there. Added a locally administered
  `mac-address-wifi0` (`02:46:50:36:00:01`) to the FP6 ADT. Repacked with
  console text visible (no `sweetfb_noconsole`):
  `/tmp/fp6-fixes-39550549760/img-wifimac/fp6-shim-ufs-root-wifimac-console.img`,
  SHA256 `5ebfd2d58eeeeaaebca1796004190804e2eb9b7398790644e9419b49500851cd`.
  Not yet booted. No logo-to-UI duration is recorded for SWEET or Tegu; SWEET's
  only logo timing is the ~60 min data-migration bar (progress bar visible),
  and Tegu's logo stall did not clear by waiting (boots ended at ~4-6 min).
- Not changed, from review: 0108 with the macOS Edge scheduler leaves P cores
  4–7 mostly idle (E→P migration/steal disallowed; throughput only); 0100
  probe images ignore `ufsrw=1`; 0105 SMMU geometry decode and power-query
  timeout cleanup are latent; 0114 socket-first send can report success while
  ARP holds the packet, hiding the raw fallback; the persistent log flush
  (0047) stays SWEET-only.

## FP6/SWEET launch diagnostics and USB logger (2026-10-21)

- Patch 0111 replaces the kernel logger's routed UDP socket sends with complete
  Ethernet/IPv4/UDP frames addressed to the fixed USB-ECM host. This bypasses
  XNU route and ARP resolution, which were in the previous send path. It waits
  for the ECM data alternate setting, reports a full transmit queue as
  `ENOBUFS`, and keeps the ring cursor unchanged on failure so the chunk is
  retried. A clean replay of patches 0099–0112 applied successfully; the
  resulting `sweet_usb.c` passed syntax compilation against the CI build tree.
  CI run `39537652816` passed for patches 0111–0112; patch 0035 already
  registers the permissive Sandbox policy for FP6.
- Live test of the 0111 image disproved the assumption that the raw sender was
  fixed: USB Ethernet came up and ping worked, but the host captured no UDP
  packets. The phone then reported raw UDP error 55, which is `ENOBUFS` on
  XNU/Darwin. This is consistent with transmit-queue or mbuf-buffer pressure
  while the logger sends its backlog. Patch 0114 adds
  socket-first delivery with the raw frame path as fallback and retries the
  same ring position after a 10 ms queue-drain delay when raw output returns
  `ENOBUFS`. Commit `1788b20` passed CI run `39545845250` (XNU build green).
  Extracted the matching stock DTB from `/home/ersa/Downloads/vendor_boot.img`
  with `unpack_bootimg`; its SHA256 matches the previously verified FP6 DTB.
  Packaged header-v2 UFS-root image
  `/tmp/fp6-usb-log-39545845250/fp6-shim-usb-log-retry.img`, SHA256
  `2e753c95582967f57dcd23090002ec83c333e76729b5fc0f856c6a3eefac490c`.
  `fastboot devices` showed no attached device. The new image has not been
  booted; confirm delivery with a host UDP capture before calling the logger
  fixed.
- Patch 0112 adds `sweet_noconsole=1` as an alias for
  `sweetfb_noconsole=1`. Both mute framebuffer console drawing after the first
  GUI swap; persistent logging and panic drawing are preserved.
- The attempted patch 0113 was redundant: existing patch 0035 already registers
  `sweet_amfi_policy_register()` for SWEET and FP6. CI applied 0035 and then
  failed when 0113 tried to rewrite the same call site. Removed 0113 from the
  series. This registers the permissive policy but does not provide individual
  sandbox profile files or container metadata.
- `tools/fp6-package.py` now puts the README's kernel diagnostics into the
  default FP6 images (`debug=0xc`, serial console, symbols, and kprintf spam),
  starts the FP6 USB logger with `fp6usb=2`, and uses the UFS-root/write,
  launchd, watchdog, and framebuffer arguments used in the previous test
  packages. SWEET-only `sweetnull`/heap-scan/IOKit-trace selectors are not
  treated as active FP6 diagnostics.
- Commit `fe6a8dc` builds successfully in CI run `39539461187`. The CI boot
  packaging job skipped because the stock FP6 DTB is not stored in CI; using
  the existing local `/tmp/fp6-stock.dtb`, the CI kernel and generated ADT
  were packaged and header-v2 contents verified at
  `/tmp/fp6-debug-build-39539461187/ufs-root-debug/fp6-shim-ufs-root-debug.img`.
  SHA-256: `f420d3d25ddab3e013b2159fc62b05b9be1c8506c52e90322f8a764d39805333`.
  The package uses `cpus=8`, `fp6usb=2`, verbose diagnostics, UFS-root/write,
  watchdog, and framebuffer arguments; it has not yet been phone-tested.
- Updated `tools/sweet-root-tweaks.py` to change any launchd stdout/stderr
  override from `/dev/console` to `/dev/null`; the diagnostic-only
  `tools/patch-launchd-plist.py` uses `/dev/null` as well. The current local
  Tegu HFS image was inspected directly: `backboardd` has neither explicit
  path, and no launchd job points either stream to `/dev/console` (two WebKit
  jobs use `/dev/null`). Therefore the old confirmed spawn failure is not
  present in this root image; no rootfs rebuild is needed for that fix.
- Existing SWEET patches already capture a `backboardd` abort: 0043–0044 log
  crash registers/backtrace, 0051/0053 scan writable heap text for exception
  reasons, 0048 tees selected `/dev/null` output, and 0049/0054 trace IOKit
  lookups and opens. These hooks are SWEET-only; the README SWEET profile uses
  their defaults. For the FP6 image, patch 0111 supplies the USB kernel logger
  but the current SWEET-only crash/IOKit hooks are not enabled.
- ADT audit: the local D22AP IPSW tree supplies the 61 usable `/product`
  properties copied by `tools/mkadt.py`; no Apple-format SWEET ADT was found.
  The generated SWEET ADT currently describes all eight CPUs as homogeneous,
  while the SWEET Linux DT describes six efficiency and two performance cores.
  This is a topology metadata gap, not an identified cause of the present
  `backboardd` exception. Qualcomm peripheral nodes require matching XNU
  drivers and should not be copied wholesale from the iPhone tree.

## FP6 watchdog/framebuffer boot-argument package (2026-10-21)

- The earlier USB-log UFS boot image omitted `wdt=-1`,
  `wdt_test=no_user_checkin`, `sweetfb_noconsole=1`, and `sweetfb_hz=30`.
  Repacked the same CI kernel (run `39472658322`, commit
  `698cc43ed79a9f8e3c53af4b436872bd764dfa60`), D22AP-product ADT, and stock
  FP6 DTB. The new arguments also disable the SWEET touch/button drivers and
  retain USB debug. `cpus=8` is retained for FP6's eight-core topology.
- `wdt=-1` is an XNU boot argument; `wdt_test=no_user_checkin` is read by
  watchdogd from the boot arguments. They were already used by the SWEET
  profile; their effect on this FP6 boot is not yet device-verified. This does
  not establish that a physical SoC watchdog has been disabled.
- Image `shim/out/fp6-wdt-fb-39472658322/fp6-shim-ufs-root-wdt-fb.img`, SHA256
  `f2ca0c938d9dc86a9a4dcc01d28e48700e2fcaf71481cf55186d37902be04b5a`.
  Header-v2 package validation passed, including embedded kernel shim and
  stock DTB checks. It has not been booted; the current phone boot was left
  untouched. USB log delivery remains unverified; the host capture was empty.

## FP6 Tegu-style iOS 16 root image (2026-10-21)

- Rebuilt the iOS 20H392 root from the locally extracted OS, SystemOS, and
  AppOS images using a Tegu-style Linux guest copy (`rsync -aH --numeric-ids`).
  `/dev/kvm` is unavailable here, so QEMU used TCG; the OS copy took about 22
  minutes. The earlier host-built image with invalid HFS index/thread records
  remains rejected and must not be flashed.
- Applied `tools/sweet-root-tweaks.py` through Tegu's isolated guest. Readback
  confirmed the Setup skip, launchd crash-policy rename and CommCenter removal,
  migration marker, audio/recorder disables, SpringBoard settings, containers,
  and ownership/mode requirements. The image has no mobileactivationd system
  container yet, so the tweak script warned that it skipped the data ark; FP6
  activation still depends on the ADT `/chosen` security-status properties.
- Tegu's read-only verifier passed for launchd, dyld, SystemVersion, all 44
  shared-cache aliases (matching inode numbers to the cryptex copies), the two
  trampoline libraries, cryptex symlinks, log directories/owners, and the
  system keybag. Linux `fsck.hfsplus -fy` repaired the volume; subsequent
  `-fn` reports only the documented journaled-volume-header minor-repair
  warning (status 8), with catalog, multi-linked-file, hierarchy, extents,
  attributes, and bitmap checks clean. Tegu's temporary local check accepts
  only this specific header-only warning.
- Linux HFS+ still does not set Apple's hard-link chain bit on these links;
  XNU can log/repair that bit at lookup, and patch 0041 only limits repeated
  diagnostics. The Tegu check proves the cache paths share inodes, not that the
  HFS catalog contains Apple's chain-bit metadata. This is the known Linux HFS+
  limitation and was also present in the earlier successful Tegu path.
- Raw image: `research/fp6-rootfs-tegu-20261021/fp6-ios-root-tegu.hfs`, SHA256
  `574cbad62a794a5e8f69cb118a37c0cf915ffe4e66ab1a5a296175c1a216296d`.
  Fastboot sparse image: `research/fp6-rootfs-tegu-20261021/fp6-ios-root-tegu.simg`,
  SHA256 `a1c6f7da616520841c4d56ac2a147940c5c93a0b4406cb1c9ae6832d64338f7c`;
  sparse header is v1, 4 KiB blocks, 4,194,304 blocks. Neither image has been
  flashed or booted on the phone.

## FP6 `mount[3]` boot-task panic (2026-10-20)

- The latest phone photo shows `mount[3] exited -- no exit reason available --
  (signal 0, exit status 1)`. The backtrace resolves in the exact CI kernel
  (`39468219112`, text base `0xfffffe0007004000`) through
  `proc_prepareexit`/`proc_handle_critical_exit`; this is launchd panicking
  because the required `mount -P 1` task returned failure, not a SweetFB or
  SweetSurface fault. Those services registering confirms matching only.
- The known SWEET `mount -P 1` failure was fixed by supplying a writable HFS
  root; the FP6 launchd-fix package omitted `ufsrw=1 rootrw=1`. The exact
  mount subcommand failure is not in this photo, so read/write root is the
  leading source-based diagnosis, not confirmed phone evidence. The packaged
  IPSW-product ADT does contain `/chosen/boot-manifest-hash`, so the earlier
  missing-hash failure is not explained by that ADT omission.
- Repacked the same CI kernel, D22AP-product ADT, and stock DTB, changing only
  boot arguments to add `ufsrw=1 rootrw=1 fp6usb=2 launchd_unsecure_cache=1`
  while retaining `unentitled_ios_sim_launch=1`. Header-v2 package:
  `/tmp/fp6-mount-fix-39468219112/fp6-shim-d22ap-product-ufs-rw-mount-fix.img`,
  SHA256 `af8e26a51deded4c1d14e5996fa73735be85553fea69a7ff8e0e8c4cf2a1f528`.
  Package construction passed; it has not been booted. `ufsrw=1 rootrw=1`
  permits writes to the existing userdata HFS volume.

## FP6 CPU cluster topology (2026-10-20)

- Source review confirms the Volcano DTS uses MPIDRs `0x000` through `0x700`,
  with efficiency CPUs 0–3 and performance CPUs 4–7 arranged as 4/3/1 clusters.
  The generated ADT preserved those MPIDRs and cluster IDs, but set every
  `cluster-type` to integer 0.
- XNU's parser in patch 0099 recognizes ASCII `E`/`P` values for those types.
  Updated `tools/mkadt.py` to emit `E` for CPUs 0–3 and `P` for CPUs 4–7. This
  corrects the topology metadata. Patch 0108 now defines `__ARM_AMP__` in the
  FP6 header so XNU builds its AMP/Edge scheduler and forms E/P scheduling sets.
  With `HAS_CLUSTER` unset, the 4/3/1 physical layout is represented to the
  scheduler as one E set (CPUs 0–3) and one P set (CPUs 4–7).
- The ADT was generated locally; CI build and phone validation are pending.
  User previously reported eight CPUs up, but did not provide the startup log
  that would verify each per-core PSCI and IPI message. Scheduling on P cores
  and a measured performance improvement remain unverified.

## FP6 boot log repetition (2026-10-20)

- The user's latest FP6 observation is only AKS calls from `backboardd`; there
  is no confirmation yet for other AKS clients, SpringBoard, or UI startup.
  The separate MediaTek-device screenshot is not FP6 evidence. AKS is the
  AppleKeyStore interface; this tree already provides a built-in no-passcode
  compatibility implementation without SEP-backed protection. `backboardd`
  reaching it indicates the request path is present, but does not identify
  whether the returned state is sufficient for display startup.
- Repeated HFS hardlink messages and daemon-spawn output were seen earlier.
  HFS patch 0041's limiter only caps diagnostic output and does not repair
  catalog metadata. The user asked to defer that cap for now, so the FP6 guard
  is removed from patch 0041 for the next build; SWEET's existing cap remains.

## FP6 SWEET userspace-enablement patch audit (2026-10-20)

- Patch 0035 registers `sweet_amfi_policy_register()` for SWEET and FP6. A
  later local replay gave a conflicting result, but the CI failure log confirms
  patch 0035 is applied before the redundant 0113 call-site rewrite. The
  permissive stand-in does not supply individual sandbox profile files or
  container metadata that some services may request.
- The FP6 `MASTER.arm64.fp6` config introduced by patch 0099 already omits
  `config_ext_resolver`, matching the effective SWEET configuration from
  patch 0057. Patch 0108 enables the AMP scheduler. Its CI build passed; phone
  testing is pending. The FP6 HFS diagnostic limiter was deferred for that
  scheduler build, then re-enabled in the follow-up HFS patch comparison below.
- Patch 0108 enables the AMP scheduler. Its CI build passed; phone testing is
  pending. The FP6 HFS diagnostic limiter was deferred for that scheduler
  build, then re-enabled in the follow-up HFS patch comparison below.

## D22AP product metadata recovery and FP6 boot package (2026-10-20)

- Located the iPhone X iOS 16.7.16 IPSW locally and extracted its D22AP device
  tree to the ignored `research/ipsw-x/` directory. The FP6 ADT generator copied
  all 61 non-placeholder `/product` properties; a parsed comparison confirmed
  they match the IPSW tree exactly and syscfg placeholders are excluded.
- Packaged `/tmp/fp6-ipsw-product-boot/fp6-shim-d22ap-product-ufs-root.img`
  with the existing AMP kernel from CI run 39461451126 (source commit
  `590b4bc05bfa574f4bfdb3fa4f101308c5ce5548`), stock FP6 DTB and the prior
  UFS-root command line. Header v2 packaging and embedded kernel/DTB/payload
  checks passed. Image SHA-256:
  `2cb4f1b8cbe2bd46a6771c648897931d0efc0e8b462a4dcb644c94e3878c0579`.
- No fastboot device was connected when checked, so this image has not been
  booted. The GitHub workflow still lacks the local D22AP ADT input; its normal
  generated ADT omits `/product` until that input is provisioned there.
- The current FP6 userdata root image is not available locally. The IPSW is
  present, but this work only extracted its device tree; it did not inspect the
  phone's userdata or validate its current HFS volume.

## FP6 HFS patch comparison and root image status (2026-10-20)

- Shallow-cloned SWEET at `11da58b` for read-only comparison. FP6 already has
  the relevant HFS support: staged Apple OSS HFS (0026), unsealed-root handling
  (0029), read/write root support (0031), rename-swap (0052), and UFS performance
  work (0069). FP6's 0106 enables `SWEET_HFS` in its own master config; SWEET's
  generic `config/MASTER` change is therefore not needed.
- SWEET's 0041 patch already limits repeated hardlink-catalog diagnostics to
  eight messages. Re-enabled that behavior for FP6 as well, per the user's new
  request to bring in SWEET's HFS patches. It suppresses repeated log output;
  it does not repair catalog records or filesystem corruption.
- No FP6 root image or extracted OS/SystemOS/AppOS images are present in the
  available local paths, so the current userdata HFS volume could not be
  inspected here. Earlier notes record a pre-boot `fsck.hfsplus -fy` as OK;
  that is not a check of the volume after the phone mounted it read-write.
- The user's Nord 2 report is separate: Apple userland and eight CPUs were
  already running there before the MediaTek framebuffer handoff was added. It
  does not establish the integrity of FP6's root volume.

## FP6 IOSurface and framebuffer enablement (2026-10-20)

- Patch 0109 enables the existing `SweetSurface` and `SweetFramebuffer`
  implementations for the FP6 build and adds the FP6 IOKit personalities for
  `IOCoreSurfaceRoot` and `AppleCLCD`. The FP6 ADT already publishes
  `/arm-io/disp0` as `sweet,display`; the shim supplies `PE_current_console`
  video fields from the bootloader FDT's `0xe3940000` framebuffer node.
- Replayed syntax compilation for `SweetSurface.cpp`, `SweetFramebuffer.cpp`,
  and `KernelConfigTables.cpp` against the prior CI build tree with clang 23;
  all three passed. The repository helper's pinned Swift clang path is absent
  on this host, so the replay used the installed clang. Full CI build and phone
  presentation test are pending.
- The image packaged before patch 0109 does not contain this driver enablement.
  The new code only copies CPU-rendered IOSurface frames to the framebuffer ABL
  left active; no FP6 DSI/panel initialization is added here.
- CI initially rejected 0109 because its context-free hunks used stale line
  numbers after patches 0101 and 0107. Added surrounding context in commit
  `3a500436979d8c3debbe07ed8d58f5ccfc5f55de`; patch application and the full
  XNU build then passed in Actions run `39468219112` (5m42s).
- Packaged that run's kernel with the verified stock FP6 DTB and an FP6 ADT
  carrying all 61 non-placeholder `/product` properties from the local D22AP
  IPSW ADT. Image:
  `/tmp/fp6-display-build-39468219112/fp6-shim-d22ap-product-ufs-root.img`,
  SHA-256 `84aad4e03bc396e684dcd45219200a744745dd1681219a80c71d2276c7c4865a`.
  Header-v2 unpack/metadata checks passed. CI's automatic phone-image packaging
  skipped because `FP6_STOCK_DTB_URL` is unset; this local package uses the
  verified DTB. It has not been booted on the phone.

## FP6 watchdogd service discovery (2026-10-20)

- The FP6 DT/ADT does not expose a verified APSS/MSM watchdog resource, so do
  not map or write Qualcomm watchdog MMIO. The user's ADSP/WPSS `wdog` IRQs
  belong to those remote processors and are unrelated to the AP watchdog.
- Added patch `0107-fp6-dummy-iowatchdog.patch`: it compiles the existing
  watchdogd-facing `IOWatchdog` user-client for FP6 and registers its IOKit
  personality in the FP6 kernel table. It preserves the known dummy behavior,
  including the `IOPMUPrimary` marker, but explicitly logs that hardware
  watchdog control is disabled. This is an interim service-discovery fix, not
  a hardware watchdog driver.
- First CI attempt `39455499092` exposed context failures in patch 0107 before
  compilation; the new patch had guessed source line positions from earlier
  hunks. Reworked the hunks to include surrounding exact context. The corrected
  commit `9c3c2f7b49c908840fc46108c6db12628e27e779` passed CI run
  `39456160901` (XNU build and FP6 packaging job). CI skipped image upload
  because `FP6_STOCK_DTB_URL` is unset. The matching kernel and ADT were
  downloaded locally and their SHA256 values verified; the known matching
  stock DTB was reused (`16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`).
- Locally packaged and header-v2 validated a UFS-root image preserving the
  prior iOS userspace boot arguments:
  `/tmp/fp6-watchdog-39456160901/ufs-root/fp6-shim-ufs-root-watchdog.img`,
  SHA256 `e31d60c0b1323f70829a3aab41ad31ad16a2dc3d8bf230a8833ecfcda61e2680`.
  It embeds kernel SHA256
  `e2c08fa79086456dfc5d24bf4c519895a1246237f7f0e50a92812fe26db40fbc` and ADT
  SHA256 `9f6030208a39700f508f34fd01c6ec5f95376fa1efb25dbdeeeb202e9322496d`.
  The command line retains `rd=ufsroot0 ufsrw=1 fp6usb=2
  unentitled_ios_sim_launch=1 launchd_unsecure_cache=1`. Header-v2 checksum,
  unpacked payload and embedded DTB checks pass. This is package validation;
  the new dummy watchdog personality has not yet been observed on the phone.

## FP6 unsealed HFS root authentication (2026-10-20)

- The user reports that the HFS root mounted, then XNU panicked with
  `rootvp not authenticated after mounting` at `bsd_init.c:947`. This advances
  past the prior journal-write failure; it is the sealed-root authentication
  check, not evidence of an HFS mount failure.
- The existing patch 0029 already permits an unauthenticated HFS root on the
  unsigned SWEET development boot. Extended that original patch's guard to
  include FP6, where the unsigned shim boot also has no Image4 trust chain and
  the development HFS root is unsealed. It now reports the auth error and
  continues through this check. This does not authenticate the volume or prove
  later userspace startup.
- A follow-on patch 0107 failed in CI because it targeted `bsd_init.c` after
  prior patch edits shifted the context. Removed it and folded the same one-line
  board guard into patch 0029, which introduces this block early in the series.
  Commit `11e3311dec6aebdcdf40f167c05316fc29601169` passed CI run
  `39444642284` (both XNU build and FP6 boot job). The workflow's generic boot
  image was skipped because `FP6_STOCK_DTB_URL` is unset.
- The intended next test image should retain `rd=ufsroot0 ufsrw=1` to allow the
  journal/root writes required by this image, and USB diagnostics. No device
  action has been run from this workspace. Locally packaged and header-v2
  validated the matching CI kernel and ADT with the verified local stock DTB:
  `/tmp/fp6-unsealed-394446/ufs-root/fp6-shim-ufs-root-rw.img`, 23,396,352
  bytes, SHA256 `e0143993d89b656cdb7094bc323d57ce32941c59c7e8b5f3bab6f2f8e0596bee`.
  Kernel SHA256 `e9568a5aa790b88c2a773483e4717d7c1ba307d91ba79f7a32c62b08e7c80750`,
  ADT SHA256 `5f273d7248d288e77f0cde2cfd118acd39f5008502e8f8b4d0db52dfee3a4a84`,
  stock DTB SHA256 `16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`.
  Command line is `debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress rd=ufsroot0
  ufsrw=1 fp6usb=2`. This opts in to writes to userdata for the HFS journal;
  The user boot-tested it and confirmed root authentication was passed far
  enough to reach launchd; launchd then failed with the wrong-platform reason
  below.

## FP6 launchd platform rejection (2026-10-20)

- On the first `fp6-shim-ufs-root-rw.img` test, the user reports that root mount
  progressed to launchd, then panicked:
  `unexpected SIGKILL of launchd (CS_KILLED) with reason namespace 9 code 0xe`.
  XNU `bsd/sys/reason.h` maps namespace 9 to `OS_REASON_EXEC`; code 14 (`0xe`)
  is `EXEC_EXIT_REASON_WRONG_PLATFORM`. This is the macOS-targeted kernel
  rejecting the iOS platform binary, not a code-signature validation failure.
- Reused the DEVELOPMENT boot argument
  `unentitled_ios_sim_launch=1` from the existing SWEET iOS userspace bring-up
  and locally repackaged the same CI kernel/ADT/stock DTB. New image:
  `/tmp/fp6-unentitled-394446/ufs-root/fp6-shim-ufs-root-rw-unentitled.img`,
  SHA256 `ae4b86c91208e56a28d9230a80b6262f6a824431b41ff25d74e2daafe0628b82`.
  It retains `rd=ufsroot0 ufsrw=1 fp6usb=2`; header-v2 packaging completed.
  This development bypass has not yet been tested on the phone.

## FP6 boot-task platform classification (2026-10-20)

- The user booted the unentitled image and reports a new panic:
  `boot task is not a platform binary /sbin/fsck`. The iOS platform rejection
  was bypassed and launchd advanced to its boot-task sequence.
- Source inspection found patch 0035 registers the built-in AMFI MAC policy
  from `bsd_init.c` only under `ARM64_BOARD_CONFIG_SWEET`. Patch 0099 compiles
  the AMFI implementation for FP6, but does not register its MAC policy there.
  As a result, its `vnode_check_signature` hook never marks root-filesystem
  binaries `CS_PLATFORM_BINARY`; the boot-task check rejects `/sbin/fsck`.
- Extended patch 0035's policy-registration guard to include FP6. This is the
  targeted source fix. Commit `8c423bf0bd8917e0a49787eac2b40bfb5385625f`
  passed CI run `39447341232` (XNU build and FP6 boot job).
- `launchd_unsecure_cache=1` is also included, as in the known-good SWEET
  userspace boot args; it lets launchd use its job cache without AMFI's
  trust-cache service. Packaged and header-v2 validated the matching kernel and
  ADT plus verified stock DTB as
  `/tmp/fp6-platform-394473/ufs-root/fp6-shim-ufs-root-amfi.img`, SHA256
  `34ac69fbdef9e3d32d4d0dbb6dc0b28ba4264590a1b71dca026a4aa347509c0a`.
  Kernel SHA256 `38c525fe8753ee2a456ad684bd38264d70e582846a12e17bc04d30d500bc3cb4`,
  ADT SHA256 `f228d71be97a8f6525819282745dd92d1ef7fecbd26a86aaaa6c4d8f8f46b35b`.
  Command line retains UFS writes and USB diagnostics and adds both
  `unentitled_ios_sim_launch=1 launchd_unsecure_cache=1`. Phone validation is
  pending.

## FP6 MKB/keybag initialization (2026-10-20)

- After the AMFI/platform image, the user reports `hfs: set hardlink bit` lines,
  then a fatal keybag error during `MKB_INIT`, followed by
  `Halt/Restart Timed Out @IOPlatformExpert.cpp`. HFS's link-chain repair is
  informational here; the fatal MKB init is the active blocker. The restart
  timeout is secondary: this FP6 bring-up does not yet provide a working
  platform restart implementation.
- Source audit found the existing built-in `AppleKeyStore`/libaks test service
  is compiled and registered only for SWEET. FP6 therefore has no service to
  satisfy keybagd's `aks_get_system` path. The ADT builder already sets
  `/defaults/no-effaceable-storage`, and `mkiosroot.sh` adds the plain system
  keybag plist; those are the established SWEET keybag prerequisites.
- Extending the built-in no-passcode AppleKeyStore service and IOKit match entry
  to FP6. This is a development stub, not SEP-backed keybag security. CI and
  phone validation are pending.
- First CI run `39449649400` failed before compilation because the modified
  patch 0099 hunk count was short by one line (`corrupt patch at line 696`).
  Corrected its hunk header; retry pending.

Last updated 2026-10-20 after adding the FP6 ADT profile. Read [HANDOFF.md](HANDOFF.md) for how to
continue and [AGENTS.md](AGENTS.md) for the rules. The per-step history (images,
hashes, CI runs, raw numbers) is [docs/GPU_LOG.md](docs/GPU_LOG.md); the hardware and
mainline reference is [docs/GPU_GMU_BOOT.md](docs/GPU_GMU_BOOT.md); the per-patch
design is [docs/GPU_CX_EXPERIMENT.md](docs/GPU_CX_EXPERIMENT.md).

## FP6 panic from probe image (2026-10-20)

- User tested image `fp6-shim-touch-ufs-probe.img` from CI run 39423526775, SHA256
  `f5abf0c8697aebef950f1d1fa6d997d6eae1d3a770caacd3b3377b0d26928198`. The phone
  displayed a kernel data abort. Photo state: PC `0xfffffe0007948c14`, LR
  `0xfffffe000793efc4`, ESR `0x96000005` (translation fault, level 1), FAR zero.
- Symbolication against that run's exact `kernel.development.fp6` resolves PC to
  `IOUserResources::resources()` and LR to `IODTMapInterruptsSharing`. This occurs
  during IOKit device-tree interrupt mapping, before the optional UFS/GPIO/touch
  probes in `IOKitBSDInit` run; those probes are not implicated by this trace.
- Source inspection found FP6's generated GIC node had an `AAPL,phandle` and was
  referenced by SPI0/TLMM interrupt-parent properties, but omitted `#interrupt-cells`.
  XNU only indexes interrupt-controller phandles that provide that property, so
  interrupt-parent resolution can return null and fault at address zero. Added
  `#interrupt-cells = 3` to the FP6 GIC profile. The corrected ADT serializes and
  dumps that property; a rebuilt image and phone retest are still pending. This is
  a source-based diagnosis until the corrected build reaches the same boot stage.

## FP6 root panic and USB debug path (2026-10-20)

- A second phone photo's backtrace was symbolicated against the exact kernel
  from CI run 39423526775. `IOFindBSDRoot` reaches its explicit panic branch:
  `QCOM UFS root %s unavailable: %d`; the visible panic-stack `Assert` frame is
  secondary. This identifies the failure as UFS root selection. The photo is
  cropped before the formatted error number, so the specific UFS init/GPT error
  remains unknown. This differs from the earlier GIC interrupt-cell panic.
- Source inspection found the SWEET DWC3 ECM gadget and UDP log sender already
  exist, but their controller power/clock probe uses SWEET-only GCC offsets.
  Patch 0101 adds an opt-in FP6 entry (`fp6usb=1` for DWC3 handoff diagnostics,
  `fp6usb=2` to start the ECM gadget and UDP console log at
  `192.168.7.1:5140`). The FP6 path does not read or write SWEET GCC offsets or
  change SMMU registers. USB DMA/IOMMU operation is not yet measured.
- Patch 0101 also hooks the existing 4 MiB in-memory console ring for FP6 from
  the first serial-console output, before UFS root setup can panic. This gives
  the USB log sender access to root-selection diagnostics. A separate USB
  debug boot image uses `fp6usb=2`; the ordinary RAM-disk image keeps USB
  disabled. Both use `debug=0xc keepsyms=1` for runtime diagnostics.
- CI run 39427603634 confirmed the patch series applied and the FP6 ADT
  generated, but the compile failed in seven existing `DEBUG`-profile units
  (DTrace `MUTEX_HELD`, ARM `bad_page_cnt`, scheduler `max_unsafe_rt_quanta`,
  and VM `uple_create_btref`). No errors were reported from the USB changes.
  The workflow default is restored to `DEVELOPMENT`, which has built previously;
  the diagnostic boot flags and USB debug image remain enabled.
- CI run 39428369953 passed for commit `207b1d8f3ee632c3cc3c3404007230752473ca0d`.
  It built `kernel.development.fp6` (SHA256
  `ea460a064820ac507e202e82ab26c1ba87d3174d2cd3b948a0662dbc82e1336e`) and the
  corrected FP6 ADT (SHA256
  `cc7891f4b863eaea02343c5624e4f9249010e6010641f03149ad23d9775be3fa`). The
  kernel compiled with `DEVELOPMENT`; runtime debug args are enabled. CI's boot
  packaging step skipped because `FP6_STOCK_DTB_URL` is unset.
- Packaged `/tmp/fp6-usb-394283/usb-debug/fp6-shim-usb-debug.img` locally using
  that run's kernel and ADT plus the existing stock DTB (SHA256
  `16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`). The
  header-v2 unpack check verified payload, shim and embedded DTB. Image SHA256
  is `81de2706d9094cc9f539a45fcaae60ffae2e346702d748c408319db18d3d7eb5`; boot
  args are `debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress rd=md0 fp6usb=2`.
  `hardware_tested` is false: USB enumeration, DMA and log delivery have not
  been observed on the phone. The host can listen with
  `tools/sweet-usbnet.sh /tmp/fp6-usb-394283/usb-debug/fp6-usb.log`.

- The user subsequently confirmed that the SWEET USB gadget appeared on the
  host. Packaged a second image from the same CI kernel/ADT and local stock DTB
  with `rd=ufsroot0 fp6usb=2`, so the existing UDP log sender starts before
  UFS root selection. Header-v2 validation confirmed the image payload, shim
  and embedded DTB. Image:
  `/tmp/fp6-ufs-usb-debug/fp6-shim-ufs-usb-debug.img`, 22,900,736 bytes,
  SHA256 `f0a8cadcd3e717fc819605db518dbfcd0e8e77dcbb356ec5719ebf8565366e05`.
  It has not been booted. The UFS initializer defaults to read-only without
  `ufsrw`; it does not flash or modify userdata. No UFS panic log has been
  captured yet, so the numeric initializer error and failing stage remain
  unknown. `fastboot devices` returned no device at packaging time.
- The user ran the host logger with the UFS-root image: the USB Ethernet
  interface appeared, but no UDP log arrived. Likely limitation: the UFS-root
  panic occurs before the background log thread gets a chance to transmit; this
  is not proof of the underlying UFS fault. Packaged a read-only UFS probe
  image that continues into the known RAM-disk init, allowing the UDP logger to
  stay alive after the same UFS initialization path. Image:
  `/tmp/fp6-ufs-probe-usb-debug/fp6-shim-ufs-probe-usb-debug.img`,
  22,917,120 bytes, SHA256
  `1a6831822a695c88e3537b48a71ec7c3a176bdd150d3ffc587153743e2764e8f`.
  Header-v2 payload/shim/DTB validation passed. It has not been booted; this is
  a diagnostic image, not a UFS-root fix.
- The user clarified that the probe logs are not files on `md0`; correct. The
  intended destination is the host-side UDP capture, which remained empty.
  The latest panic photo confirms `EIO` (errno 5), but does not distinguish
  request-list takeover from a failed SCSI completion. Patch 0102 records the
  failing UFS stage and command/status detail and adds them to the panic text,
  so the next UFS-root attempt can identify the underlying failure without a
  working UDP stream. This is diagnostic instrumentation, not yet an UFS fix;
  it still needs a CI build and phone boot.
- Patch 0102 CI run `39431367035` succeeded on commit
  `cd38bdead498c0dd7e687aa169490ad723f781a5`. Kernel SHA256:
  `cc1462c718fa2c8280c8426b0cca4eb87cac2a35a01a74437ac5558b003df334`;
  matching FP6 ADT SHA256: `2a9500cfffd003771621b6ea0afbea573f3e43eabff748f2777c2032b49b76ff`.
  CI boot packaging skipped because `FP6_STOCK_DTB_URL` is unset. Locally
  packaged and header-v2 validated a temporary UFS-root image using those
  artifacts and local stock DTB:
  `/tmp/fp6-ufs-stage-394313/fp6-shim-ufs-stage-debug.img`, 22,900,736 bytes,
  SHA256 `3b9100a82b7576f8f9ebf6d4c7ea66593e9ce0cf3e88f3fcfed383d5e37825c5`.
  Command line includes `rd=ufsroot0 fp6usb=2`. The user booted it and reported
  `SCSI completion detail 0x2102` and panicked task pointer
  `0xfffffe1b4109ec10`.
- The reported `0x2102` detail decodes to response UPIU `0x21` and SCSI status
  `0x02` (CHECK CONDITION); OCS is zero and the command was TEST UNIT READY.
  Because the reported stage is still `SCSI completion` on the 0103 image, its
  earlier guard also saw nonzero response byte `resp[6]`, which the packed
  detail omits. The UFS transport completed, but the response byte and sense
  values remain unknown. The panicked-task pointer is not a fault diagnosis.
  Linux's UFS definitions confirm that sense data is embedded in the response
  UPIU, so a separate REQUEST SENSE command is unnecessary.
- Patch 0103 decodes the embedded sense key/ASC/ASCQ and reports them in the
  panic detail. It retries TEST UNIT READY for up to 3 seconds only for UNIT
  ATTENTION or NOT READY / becoming ready; other SCSI errors remain failures.
  CI run `39433706325` built successfully on commit
  `be6b8d176a83426b12697bc0c0a27d8fc4374744`. Packaged and header-v2 unpack
  validated `/tmp/fp6-sense-394337/ufs-root/fp6-shim-ufs-sense-debug.img`,
  SHA256 `1a55b0261c102fff887dfb9fd33c97d0c4705a9d59b56e054c0bf7d5fab6cf55`.
  It uses `rd=ufsroot0 fp6usb=2`, is read-only with respect to UFS by default,
  and was subsequently booted; it reproduced the SCSI completion panic below.
- The user then booted the 0103 image and still saw
  `ufsroot0 unavailable 5 at SCSI completion detail 0x2102`. The 0103 kernel
  binary contains the new check-condition path, so the reported stage means its
  earlier completion guard rejected a nonzero response byte (`resp[6]`) before
  sense decoding. The packed detail retains UPIU `0x21` and status `0x02` but
  omits that response byte. Linux's completion path consumes SCSI status from a
  response UPIU and copies the embedded sense for CHECK CONDITION; patch 0104
  now follows that flow and reports both response and sense. Exact values still
  await phone retest.
- Research against the local stock FP6 DTB found its UFS host node at
  `0x1d84000`, using two lanes, the Qualcomm UFS PHY, ICE, MCQ, and an SMMU
  stream (`iommus` stream ID `0x60`) with `qcom,iommu-dma = "fastmap"`. It also
  sets `qcom,broken-ahit-wa`. Linux's QCOM driver disables the auto-hibernation
  idle timer while commands are active on that quirk path; the current XNU
  handoff driver does not. This is a platform-confirmed candidate to address,
  though it does not by itself explain the TUR CHECK CONDITION. The existing
  TUR has no PRDT, so its completion has not validated data-buffer DMA through
  the SMMU; actual GPT/data reads remain untested.
- The QCOM Linux host also owns PHY initialization, regulators/clocks, link
  startup, device-init queries, and recovery. XNU currently assumes ABL leaves
  those initialized and takes over only the UTRL. Since TUR returns a UFS
  response with OCS zero, the live link and a response DMA work at least once;
  this does not validate post-handoff power-state handling or data DMA. No
  Apple-specific iPhone UFS host source was found in Apple's public XNU tree.
- Patch 0104 CI run `39435664153` succeeded on commit
  `0ff825a8f143aff1926e8071342ccba708057ad3`. Locally packaged and header-v2
  validated `/tmp/fp6-ufs-audit-394356/ufs-root/fp6-shim-ufs-response-debug.img`,
  SHA256 `6a61741e1c8a1853a6362f5ac7b2258ab65e91be869d4441612b42045e7e154b`.
  It uses `rd=ufsroot0 fp6usb=2`; it has not yet been booted. CI's own boot
  packaging was skipped because `FP6_STOCK_DTB_URL` is unset.
- Patch 0105 implements the FP6 UFS/SoC handoff basics using NativeUfs and the
  cloned SM7635 Linux sources: disable/restore the DT-confirmed broken AHIT
  timer around each completed transfer; read `bCurrentPowerMode`, wake a
  non-active device with START STOP UNIT on WLUN `0xD0`, then retry TUR for a
  bounded 3 seconds; decode fixed and descriptor sense; inspect FP6 SMMU stream
  `0x60` and preserve its live mapping, or configure only that stream through a
  checked Linux Qualcomm pass-through context when no mapping exists. The FP6
  ADT now carries the stock SMMU range `0x15000000..0x150fffff` and stream ID.
  Patch application and ADT generation were checked locally. The local XNU
  compile could not run because this Linux workspace lacks the Xcode kernel SDK
  clang expects; CI build and phone validation are pending. No device was
  touched, and this patch has not yet been committed.

## FP6 hardware bringup and pthread/gPanicBase fixes (2026-10-20)

- On-device observation with packaged header v2 boot image (containing stock DTB):
  ABL booted successfully into shim, simple-framebuffer splash activated at 0xe3940000 (1116x2484).
  XNU initialized console, IOKit matched platform and boot CPU ("1 of 1 CPUs initialized"),
  entered BSD, and halted with:
  `panic pthread kernel extension not loaded pthread_shims.c:318`.
  Also observed:
  `debug_log_init: Error!! gPanicBase is still not initialized` and
  `Serial requested, consistent debug disabled or debug boot arg not present`.
- Root causes:
  1. Built-in libpthread was guarded by `CURRENT_MACHINE_CONFIG == SWEET` and `ARM64_BOARD_CONFIG_SWEET`.
     `sweet_pthread_register` was never compiled or registered during early boot on FP6.
  2. `gPanicBase` was uninitialized because no `pram` node exists in the bootstrap ADT, causing
     `check_for_panic_log` to return early.
  3. `kdp_udp.c` fell back to serial KDP warning because `PE_consistent_debug_enabled()` returned false.
- Fixes staged in patch 0099:
  1. Enabled `sweet_libpthread` and `sweet_hfs` for `FP6` in `bsd/conf/Makefile.template`,
     `bsd/sys/pthread_internal.h`, `bsd/pthread/sweet_pthread_*.c`, `bsd/kern/sweet_amfi.c`,
     and `iokit/Kernel/IOService.cpp`.
  2. In `pexpert/arm/pe_init.c`, provided a 256 KiB static panic buffer fallback when `pram` is absent,
     initializing `gPanicBase` and `panic_info` cleanly.
  3. In `pexpert/arm/pe_consistent_debug.c`, provided a static debug registry fallback for FP6, and in
     `osfmk/kdp/kdp_udp.c`, bypassed serial KDP when serial is not explicitly requested.
  4. Registered `QcomPlatformExpert` and `QcomCPU` classes in `SweetPlatformExpert.cpp` and `SweetCPU.cpp`
     and added corresponding entries in `KernelConfigTables.cpp`.
  5. Verified patch 0099 applies with zero errors against the baseline.

## FP6 shim packaging (2026-10-20)

- Patch audit: Phoenix edits to 0016 broke later patch contexts. Restored 0016
  and placed board integration in 0099. A clean xnu-8796.141.3 replay applied
  all 99 local patches and four selected Ventura harness patches (103/103).
- Added explicit FP6/Phoenix MASTER configs and FP6 header export; FP6 shares
  portable crypto/RNG and architecture CPU/GIC code with a one-CPU limit.
  Sweet hardware driver registration remains disabled for FP6. These source
  changes await full CI compilation and hardware validation.
- Build preparation now selects the four applicable upstream patches, aborts
  on every patch failure, stages portable dependencies for FP6/Phoenix and
  defaults the workflow to FP6. Different targets have separate concurrency.

- Inspected user-selected successful CI run `39371823683` at `4e7fdf0`.
  Artifact `12242266868` contains `kernel.development.sweet`, SHA256
  `18f69070e456841cc4d400f6d6438b7ede02eb2e6b0429d4b231da88e7d9eddc`,
  and no FP6 ADT artifact. A source commit mentioning FP6 did not select FP6
  for this push build. Do not package that kernel for FP6.
- FP6 build run `39373440958` at `24370bb` generated the ADT, then failed during
  XNU compilation; the `fp6-boot` job was skipped, so no matching kernel/boot
  image exists. The failed compile pulled in SWEET HFS and pthread features
  through the shared master config, and the portable BearSSL include paths were
  only enabled for SWEET.
- Corrected the config scope: SWEET HFS is machine-specific; FP6 no longer
  enables Sweet HFS or its bundled pthread provider. FP6 still stages the
  portable crypto implementation, with compiler include paths enabled for
  FP6. Run `39374822879` reached patch 0031, which requires staged HFS source
  even when that filesystem is disabled. Restored HFS source staging for FP6;
  this stages files for later patch contexts but does not enable HFS in its
  machine config. Retry CI after this fix. Full build and phone boot are pending.
- Inspected failed CI run `39375193145` at `552b6b2`. All compilation units
  succeeded; the final link `kernel.development.fp6.unstripped` failed on two
  undefined symbols: `_sweet_sample_task` from `sweet_sample.o` (unconditionally
  compiled by bsd/conf/files while its implementation in osfmk/kern/exception.c
  was guarded by ARM64_BOARD_CONFIG_SWEET) and `_sweet_secondary_entry` from
  `SweetCPU.cpo` (PSCI CPU_ON stub in osfmk/arm64/start.s was guarded by SWEET).
  In patch 0099, guarded `bsd/dev/sweet_sample.c` under ARM64_BOARD_CONFIG_SWEET
  and added FP6 guards to `osfmk/arm64/start.s` for `sweet_secondary_entry`, MPIDR
  Aff1 extraction, TLB/cache invalidation and SCTLR check bypass. Patch 0099
  verified to apply cleanly against baseline `b097596`. Ready to commit and push.

- Local LLVM build now links the shim and packages an unsigned Android v4 image.
  The local packaging check used placeholder payload bytes only: shim and ramdisk
  unpack byte-for-byte. This is not a tested XNU boot image or a phone observation.
- `tools/fp6-package.py` consumes a kernel and ADT from the same CI run, builds
  the FP6 shim, verifies packaged components and writes hashes/provenance.
  The new `fp6-boot` CI job uploads `fp6-fastboot-boot` after an FP6 kernel build.
  Its first CI execution failed before packaging. Pushes now use the FP6 target
  by default; select other targets explicitly for manual runs.
- FP6 shim failures halt instead of entering Sweet diagnostic probes. Missing
  runtime framebuffer leaves the display untouched. The loader searches aligned
  payload headers after possible vendor ramdisks and validates segment extents.
- Header v4 relies on the installed vendor_boot/DTBO and ABL for the runtime FDT.
  Acceptance by FP6 ABL, live framebuffer availability and XNU handoff remain
  unmeasured. No flashing or phone commands were performed.
- User wants the new run's matching kernel/ADT, followed by driver bring-up one
  kext at a time after a working initial boot. Do not use the older kernel run.

## Fairphone 6 platform audit (2026-10-20)

- Began a source-only audit for Fairphone (Gen. 6), device name `FP6`.
  Fairphone identifies it as Snapdragon 7s Gen 3 / SM7635. Mainline Linux has
  `milos-fairphone-fp6.dts` with `fairphone,fp6` and `qcom,milos` compatibles.
- QCM6490 is Fairphone 5, not Fairphone 6. No QCM6490 code or FP5 target was
  added as part of this work.
- An experimental `MACHINE_CONFIG=FP6` compile target exists in patch 0004,
  using an ARMv8.2+crypto baseline and the sourced 8-core / 3 cluster counts.
  `tools/mkadt.py --device fp6` now generates an FP6 ADT profile with sourced
  CPU affinity/topology, GICv3 and UFS ranges, Fairphone identity, and the
  upstream Linux FP6 framebuffer address and dimensions. It requires
  no RAM arguments: the shim will read the bootloader FDT, exclude reserved
  ranges, initrd, framebuffer and its own image, then patch `dram-base` and
  `dram-size` in the ADT and boot args. The LineageOS DTS leaves RAM as
  `<0 0 0 0>`. The XNU workflow accepts `MACHINE_CONFIG=FP6` and emits the
  profile ADT artifact. Host syntax/serialization checks passed, but there has
  been no FP6 XNU build, CI run, FP6 shim image, or phone observation. See
  [docs/FAIRPHONE6.md](docs/FAIRPHONE6.md).
- Persistent LineageOS source checkouts are available under `/home/ersa/Dev`:
  `android_kernel_fairphone_sm7635` and
  `android_kernel_fairphone_sm7635-modules`. The device tree and vendor DTS
  reference remain under `/tmp/lineage-fp6-device` and
  `/tmp/lineage-fp6-devicetrees`.

## POCO X2 / Phoenix support (2026-10-20)

- Inspected `aospa-phoenix/android_kernel_xiaomi_phoenix` at
  `c01153e9ba446642640749077a19467e7e0094f5` in `/tmp` (source only; clone is
  not part of this repository). It confirms the shared SM7150 platform and
  Adreno 618 family. Phoenix and Sweet both have 1080x2400 panels with 120 Hz
  maximum timing; the Phoenix source describes WLED and 30–120 Hz modes, while
  Sweet uses OLED and 60/120 Hz modes.
- Added a `PHOENIX` XNU machine config that reuses the existing SM7150 board
  definition, platform expert and GPU path. Added `--device phoenix` to
  `tools/mkadt.py`; generated Phoenix trees use the `xiaomi,phoenix` compatible
  and a distinct synthetic ECID. The iOS-facing D22AP / iPhone10,3 identity is
  retained for the bundled iPhone X userland.
- This is source inspection and code editing only. No tests, XNU build, CI run,
  phone boot, or display observation was performed. The XNU/platform changes
  and Phoenix ADT have not yet been built or tested on hardware. See
  [docs/PHOENIX.md](docs/PHOENIX.md).

## What this repo is

Driver playground for the XNU/iOS 16 port to the Redmi Note 10 Pro (`sweet`,
SM7150, Adreno 618). The target is a real Adreno driver; the display today is
CPU-rendered. Public repo `dipa-studio/ios-extra`, branch `main`. The user made it
private overnight, then authorized restoring public visibility on 2026-10-19;
GitHub now confirms public. Kernel builds use this repo's GitHub Actions
(`.github/workflows/xnu.yml`, macOS runner, ~6 min).
`/home/dipa/ios-sweet` belongs to other agents: read-only for us.

## Where the GPU bring-up stands (all measured on the phone unless noted)

| Patch | `sweetgpu=` | What it does | CI run | Phone |
| --- | --- | --- | --- | --- |
| 0080 | 1 | read-only GCC/GPUCC clock + GDSC inventory | 39152959124 | ok |
| 0081 | 1 | cache that inventory, replay it over USB | 39154941656 | ok |
| 0082 | 2 | command-DB ARC level tables (`gfx/cx/mx.lvl`) | 39157726409 | ok |
| 0083 | 3 | MX+CX LOW_SVS votes via RPMh ARC, CX GDSC on/off, rollback | 39159151996 | ok |
| 0084 | 4 | GMU clock tree (GPLL0/2 gate, RCG 200 MHz, cx-gmu branch), rollback | 39161422925 | ok (first build refused: wrong precondition) |
| 0085 | 5 | GCC memnoc/ddrss-axi branches + first GMU register reads | 39162789741 | ok |
| 0086 | 6 | GMU firmware (`a630_gmu.bin`, staged at build) into ITCM/DTCM, readback | 39164168730 | ok, 0/8192 mismatches |
| 0087 | 7 | read-only GPU SMMU inventory | 39165446245 | ok |
| 0088-0089 | 8 | stream 5 -> CB3, tiny 4 KiB page table, ATOS check, restore (+ write transcript) | 39167833774 / 39168706195 | translations correct; S2CR3/CBAR3 refuse restore |
| 0090 | 9 | read-only RSC/PDC inventory | 39169517724 | ok |
| 0091 | 10 | mainline A618 RSC/PDC init (48 writes, readback), RSC stop handshake | 39170396365 | handshake ok, 9/48 writes did not read back |
| 0092 | 10 | same, logs every mismatch + reads the table first | 39171199100 | stop handshake ok; all 9 mismatches identified |
| 0093 | 11 | 13 GMU buffer pages, mainline HFI layout, 29 ATOS checks | 39293204273 **passed** | 29/29 ATOS; inactive=1, restored=0 |
| 0094 | 12 | read-only inventory of 29 pre-boot GMU registers | 39297388718 **passed** | 29/29 registers read; home screen confirmed |
| 0095 | 13 | bounded TCM retention + RSC wake/stop, CM3 reset | 39300239967 **passed** | wake/stop and full sampled state restore; home screen |
| 0096 | 14 | read-only GMU IRQ masks/status, fence and RPMH state | 39303111412 **passed** | 6/6 reads; home screen |
| 0097 | 15 | GMU interrupt mask/restore | 39305068882 **passed** | AO reads 0x3f; guard stops, restored; home screen |
| 0098 | 15 | exact measured AO readback; continue mask test | 39307039113 in progress | not tested; no image yet |

The user confirmed the home screen after every boot up to 0097. Each stage runs
inside the previous one's window (`sweetgpu=N` includes all lower modes) and undoes
itself except: SMMU `S2CR3`/`CBAR3` (left inert: `SMR3` invalid, `SCTLR` 0), the
GMU RCG (left at `0x602`), and the RSC/PDC configuration of 0091 (left in place).

**The GPU core (GX) has never been powered and nothing has executed on the GPU.**
Rendering is still CPU. The GMU processor has never been released from reset.

## Immediate next action

0095 phone test passed: RSC wake ACK=3 (bit 1 set), SEQ_BUSY=0, stop
STATUS=0x01010006, all six sampled control/state words restored. Retention 1->0,
CM3 reset remained 1 and GX GDSCR stayed 0x00222001. User confirmed home screen.
Raw values in GPU_LOG. No firmware execution or GPU command yet.

0096 (mode 14) passed at 18:39:28 UTC, user confirmed home screen. Both GMU
interrupt mask words=0, both status words=0, AO fence control=0, RPMH power
state=0x0f; raw values in GPU_LOG. All lower probes/cleanup still pass. Full CI
39303111412 built edd2b796ed7ff02434c42942c490543c17f95456 and artifacts match the
local source. 0097 separately tested the first mask with CM3 still reset (result below).
0097 (mode 15) reached the readback guard at 18:53:52 UTC: wrote AO mask
0xffffffff, got 0x3f, restored 0; second mask untouched. All sampled state/lower
cleanup restored, reset=1 and GX off. User confirmed the home screen. Green CI
39305068882 built 01dbc6e5571eacdca32f7c0d60bc34ce0d77ab00; artifacts matched.
0098 implements only that exact AO tuple exception, retaining mode 15 and the
mainline all-ones write. Normal and ASan/UBSan suites pass, including 42 rejected
alternative AO/HFI readbacks, all 20 zero-write refusals and failure/rollback tests;
arm64 compile 0 of 1 failed. Baseline c242eb7 (measured 0097); isolated diff equals
0098 patch, committed/pushed at edab65c998a917d5e450b730aa4d0ff2e8e6032e. CI 39307039113
is in progress at handoff; verify it succeeds and verify/package its artifacts before
the phone test. No 0098 image or phone result exists at this handoff.

An unvalidated first-start draft is external only (`ios-extra-work/gmu-first-start-draft.patch`),
based on 0095; do not apply it unchanged. It still needs IRQ-mask/clear gates,
complete host failure tests and reconciliation with 0096–0098 measurements before
full CI or phone use. It also needs SMMU global-fault interrupt containment: measured
sCR0=0x00200626 has GFIE/GCFGFIE set. No sCR0 write has been made. See GPU_GMU_BOOT
and the first-start review in HANDOFF. No first-start image exists.

## User-visible iOS observation (2026-10-19)

The user reports missing wallpaper and some white Settings/widgets in this image;
a separate image assembled from ios-sweet patches reportedly has working wallpaper
and widgets (still only three apps). The comparator build/root/assets have not
been identified or reproduced here; cause and relationship to GPU experiments
are unestablished. Home-screen arrival does not mean the UI is fully working.
The user asked to continue GPU bring-up; no userland repair or upstream-tree
changes are being made as part of this work.

## Additional source reference

The user supplied apple-silicon-anyos-project. Pinned source review at
59fd73aac4ae386939bc69dc58dffbce1b2167b2 is in GPU_EXTERNAL_DRIVERS: candidate
AIR/SPIR-V/Vulkan reuse for later integration, but a QEMU/macOS paravirtual
transport and no demonstrated sweet/Adreno path. No code imported or executed.

## Hard constraints (unchanged)

- Always check `fastboot devices` (serials redacted) before asking for fastboot.
  If exactly one device is already there, announce and run the authorized pending
  temporary test; ask only when none is present, stop if multiple are present.
- Temporary `fastboot boot` only. No flashing, no partition/GPT changes, keep
  bootloaders, recovery, modem, persist and the backups. Never `fastboot getvar`.
  The user must put the phone in fastboot; never reboot it unannounced.
- Keep serials, device dumps and Apple artifacts out of Git. The GMU firmware is
  downloaded at build time (`xnu/patches/0086-stage-gpu-firmware.sh`), never committed.
- Report source reading, a green build and a phone result as three different things.

## Workspace map (outside Git)

`/run/media/dipa/android/ios-extra-work/`: `buildtree/xnu` (isolated XNU tree; local
git commits mark each CI-validated baseline, `sweet_gpu_fw.h` is untracked there),
`out-NNNN/` + `ci-NNNN/` (latest CI kernel and build tree), `gpu-fw/` (linux-firmware
clone `lf/`, mainline v6.12 sources, register xml), `logs/` (`phone-*.pcap/.txt`,
`ci-0081.log` which `tools/xnu-cc.py` needs, sanitized fastboot output), `objects/`,
`shim-out/` (symlinked as `shim/out`). Keep only the latest image/kernel; old ones are
reproducible from the manifests. 136 GB free on the external drive; the home disk is
small, so keep large files external.

## Tools (all tracked, `tools/`)

`gpu-package.py` (kernel -> temporary boot image + manifest), `gpu-phone-test.py`
(capture, boot once, replay window, decode), `gpu-decode-pcap.py` (UDP log from a
pcap), `phone-ecm-host.py` (host side of the USB ECM link), `xnu-cc.py` (single-file
arm64 compile against the CI build tree). Host tests: `python3 -W
error::ResourceWarning -m unittest discover -s tests` (also with
`IOS_EXTRA_CFLAGS="-fsanitize=address,undefined -fno-sanitize-recover=all -g"`).

## FP6 Actions failure review (2026-10-20)

- Reviewed failed FP6 run `39412735706` at `83a712822ef0855bf653f00ee2938b8845766352`.
  The compile reached the XNU build and reported an undefined `kDbgIdTopLevelHeader`
  in the FP6 consistent-debug fallback, plus missing staged `sweet_libpthread/kern/*.c`
  includes. Downloaded that run's `xnu-buildtree` artifact and confirmed XNU 8796's
  `consistent_debug.h` documents the top-level record field but does not define that
  symbol. The fallback now supplies a local CDBG-HDR record ID. The libpthread staging
  script now stages the immutable matching provider for FP6, consistent with patch
  0099 compiling its provider sources. Pending a new Actions result.
- Reviewed FP6 Qualcomm constants in patch 0099 and the generated ADT: FP6 uses
  GIC redistributor stride `0x40000`, virtual timer INTID 27, one CPU for initial
  bring-up, and SM7635/Volcano compatible strings. Patch 0099 corrects the initial
  FP6 header's placeholder stride. No device or display driver behavior is inferred
  from these build definitions; the framebuffer splash is bootloader-provided.

- Follow-up run `39413914090` at `6da7325` staged pthread successfully and compiled all
  XNU objects, then failed at final link: `sweet_amfi.o` referenced seven
  `sweet_entitlements_*` functions absent from `SweetEntitlements.cpp` because that
  implementation was SWEET-only. Expanded its build guard to FP6 in patch 0035;
  this preserves XML entitlement support and resolves the specific undefined symbols.
  New CI build pending.
- Run `39414717734` at `48b58a5948a7c23e46022406eb5134e0da7f314d` completed successfully:
  both the FP6 XNU build and `fp6-boot` packaging job passed. The run uploaded
  `fp6-fastboot-boot` (shim boot image, SHA256SUMS and manifest), plus `xnu-kernel`
  and `fp6-adt`. This confirms a kernel build and temporary-boot-image package only;
  no phone boot has been performed for this image.
- The user expanded the FP6 port goal to staged XNU support for CPU/SMP, timer/GIC,
  display console, UFS storage, graphics/software rendering and USB/DWC3 networking
  or serial. Work these subsystems one at a time; distinguish bootloader-provided
  framebuffer splash from an XNU display driver. Fairphone 6 is SM7635 (Snapdragon
  7s Gen 3), so the user's table's SM7450 label should not be used for this target.
- SMP source review: LineageOS `qcom/volcano.dtsi` has eight CPU nodes with MPIDRs
  `0x000` through `0x700` and a 4+3+1 cpu-map. The generated FP6 ADT matches those
  IDs. Existing PSCI CPU_ON, secondary reset entry, redistributor lookup and SGI
  startup path are present in patch 0099; enabled its ceiling for all eight CPUs
  and changed the generated FP6 image command line to `cpus=8`. This is source
  inspection only until the next CI result and a phone boot; each secondary must
  report initialized/SGI-ready before XNU publishes all CPUs initialized.
- Separate boot observations reported by the user: XNU waits for
  `IOProviderClass IOMedia AppleHFS`, and the boot picker failed to write its
  reason to NVRAM. Neither observation verifies secondary CPU startup. Root media
  publication and NVRAM persistence remain separate issues. The wait is emitted
  by `IOFindBSDRoot`'s fallback HFS-media matcher when no `rd=` root was selected.
  For the next FP6 image, package a minimal Mach-O init as the existing virtual
  `RAMDisk`/`rd=md0` root. This deliberately bypasses UFS; it does not implement or
  validate the FP6 UFS host driver. The CI packager now builds and includes that
  init. The known header-v2 packaging path still requires the local stock DTB.
- Correction after reviewing the earlier FP6 boot notes: the known on-device path used
  Android boot header v2 with the stock DTB embedded. CI run `39414717734` uploaded a
  5,626,548-byte compressed artifact, but that artifact expands to a 16,203,776-byte
  header v4 image without a DTB; it is not the previously tested packaging format.
  Repacked that run's successful kernel and matching ADT with `/tmp/fp6-stock.dtb`
  using `tools/fp6-package.py --dtb`, which selects header v2. The resulting image is
  22,896,640 bytes, SHA256 `3dcc03f79b4fb6b775ebbb1612509a772e54b78d45301e20bdd72ce95861e59e`;
  unpack validation confirmed the 192,512-byte shim kernel, 16,003,456-byte XNU
  payload and embedded DTB exactly match their inputs. This rebuilt v2 image has not
  been booted. CI run `39417320648` repeated the same v4/no-DTB mistake. The user
  tested its image and ABL rejected it with `Failed to load/authenticate boot image:
  Invalid Parameter`. Confirmed the header version at offset 40 is 4 and there is no
  embedded DTB. Repacked this run's eight-CPU kernel and matching ADT with the local
  stock DTB and RAM-disk init: `/tmp/fp6-repack/fp6-shim-boot.img`, 22,913,024 bytes,
  SHA256 `4a528a4cec90f772685fd740484636b2fc8c61b23d0d840e825872e4c8a896e0`.
  Package validation confirms header v2 and exact kernel, payload, and DTB bytes.
  `tools/fp6-package.py` now requires a DTB and rejects header v4. CI publishes a
  fastboot image only when repository variable `FP6_STOCK_DTB_URL` is configured;
  without it, the workflow warns and skips the image artifact. The corrected local
  image was then booted on the phone; the user reports that all 8 CPUs came up.
  The exact image SHA and boot log have not yet been provided, so this observation
  is not attributed to a particular package.

## FP6 iOS userspace image and Qualcomm subsystem audit (2026-10-20)

- Built a local iOS 16.7.16 (`20H392`) HFS+ root image from the user-provided
  iPhone X IPSW. The raw image is 16 GiB; `img2simg` produced a 12 GiB Android
  sparse image. The final `fsck.hfsplus -fy` reported the volume appeared OK;
  `file` recognized the output as Android sparse v1. This is host-side image
  construction only. It has not been flashed or mounted by FP6 XNU.
- Do not flash this image to `userdata` yet. That operation overwrites the
  phone's existing userdata, while the current FP6 image boots a tiny `rd=md0`
  RAM-disk init and has no FP6 UFS block driver/root-media path. The iOS HFS+
  image therefore cannot yet be used by the running kernel. Raw and sparse
  images remain under Downloads and are not tracked.
- User clarified that the current debugging goal is USB debugging. Source review
  confirms FP6's Qualcomm DWC3 wrapper at `0xa600000`, generic DWC3 core at
  `0xa600000`, eUSB2 PHY at `0x088e3000`, EUD registers at `0x088e2000` and
  `0x0c278000`, and QMP USB/DP combo PHY at `0x088e8000`. It uses OTG/role
  switching, extcon/EUD and PDC interrupts. Existing CDC-ECM/live-log patches
  0072–0077 are SWEET/SM7150-specific and cannot simply be enabled for FP6.
  See [FP6 Qualcomm subsystem audit](docs/FP6_QUALCOMM_SUBSYSTEMS.md).
- Source review also finds the next practical subsystem priorities: FP6 UFS
  block/root support for iOS userspace, USB CDC-ECM for debug logs, then the
  board-specific power/regulator path and touch input. The bootloader framebuffer
  is separate from a live panel driver; Adreno 618/740 code is not a drop-in for
  FP6's Adreno 810 Gen8.3 GPU. Wi-Fi, Bluetooth, audio, camera and cellular depend on more
  firmware/DSP and transport work.
- No FP6 USB code was changed or tested in this audit, and no new CI run or phone
  boot was started. The next USB code change should first gather a read-only
  FP6 DWC3/clock/PHY state report, then test endpoint-zero enumeration before
  adding CDC-ECM. The new root image must not be presented as a phone-tested
  result.


## FP6 Qualcomm UFS and GPIO ADT (2026-10-20)

- Started `0100-fp6-qcom-ufs-root.patch`: enables the existing UFSHCI driver
  for FP6, labels its output QCOM UFS, keeps Sweet-only log/GPU/USB/touch/key
  startup behind the SWEET board guard, rejects failed controller MMIO maps,
  and adds an idempotent initializer with a read-only probe entry point. The
  probe ignores `ufsrw`; root mode honors it only when explicitly requested.
- `IOKitBSDInit.cpp` gains an opt-in `fp6ufsprobe=1` hook and FP6 `rd=ufsroot0`
  routing. The probe image retains `rd=md0`; the root image omits the RAM disk
  and leaves the existing Android `userdata` untouched. At the initial source
  change, neither image had been built or booted; follow-up CI/package results
  are recorded below.
- Corrected `tools/mkadt.py` to match the FP6 stock DTB's Cliffs TLMM:
  physical base `0x0f000000`, 16 MiB range, SPI 208, 179 GPIOs, reserved 56–60.
  This replaces an incorrect Volcano-compatible/reserved-pin guess.
- The FP6 bugreport identifies the touch controller as ESWIN EPH86xx on SPI0.0
  at QUPv3 SE0 `0xa80000`; the Fairphone SM7635 modules contain its SPI driver.
  The matching FP6 SKU overlay includes the Volcano MTP touch description:
  SPI mode 3 at 2 MHz, IRQ TLMM GPIO 19, reset GPIO 20, SPI pins 94–97, L22B
  and L9B supplies, plus `EPH86XX_fw.bin`. Linux's GPIO number 364 corresponds
  to the source reset pin in that overlay, although XNU must use the TLMM-local
  pin number 20.
- Updated the generated FP6 ADT to mark QUPv3 SPI0 and its ESWIN touch child
  present, with the overlay's GPIO and panel metadata. The controller still
  needs a GENI driver, pinmux/clock/regulator support and a HID event service;
  marking the ADT node present does not turn on the physical bus.
- Added opt-in `fp6gpio=1` and `fp6touch=1` passive probes to the UFS-probe
  image. They sample Cliffs GPIO input states (skipping reserved pins 56–60)
  and report the ESWIN touch ADT node. They do not access SPI MMIO or write pin
  mux, clock, reset, or SPI command registers.
  The successful build contains these paths; no phone observation exists yet.
  They are diagnostics, not a touch event driver.
- The corrected workflow run `39423526775` succeeded on source commit
  `d50bbff0304a365ee2972e3c041b2a9936e53591`. CI kernel SHA256:
  `2736519b29b5b6737aa40ddbf2377affea27d3a0adc5db7279677bc90a061181`; FP6
  ADT SHA256: `da9a1f5881207ac946db3f64cbd4165b8828a899019a049a04bb49081d3529f4`.
- The CI `fp6-boot` job skipped packaging because `FP6_STOCK_DTB_URL` is not
  configured. Using the verified CI kernel/ADT and local matching stock DTB
  (`16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`),
  locally packaged Android boot header-v2 images in
  `/tmp/fp6-ci-39423526775/images/`. The recommended read-only probe image is
  `touch-probe/fp6-shim-touch-ufs-probe.img`, 22,917,120 bytes, SHA256
  `f5abf0c8697aebef950f1d1fa6d997d6eae1d3a770caacd3b3377b0d26928198`; its
  command line keeps `rd=md0` and enables `fp6ufsprobe=1 fp6gpio=1 fp6touch=1`.
  Baseline and `rd=ufsroot0` images are alongside it. Package validation
  confirmed embedded kernel/payload/DTB and all SHA256SUMS; no image has been
  booted. Current Android `userdata` is not the iOS HFS+ root image.
- FP6 USB gadget/debug transport and active EPH86xx SPI/HID input remain
  unported; Sweet's SM7150 implementations are still guarded from FP6.

## FP6 Qualcomm UFS SOC bring-up (2026-10-20)

- Added and pushed commit `b1d8734` (`feat(fp6): initialize UFS power and SMMU
  handoff`). Patch `0105-fp6-ufs-soc-basics.patch` adds FP6-only handling for
  the UFS SMMU stream, the Qualcomm `broken-ahit-wa`, UFS power-mode query and
  wake-up, fixed/descriptor sense parsing, and bounded readiness retries. The
  FP6 ADT now includes SMMU base `0x15000000`, size `0x100000`, and UFS stream
  ID `0x60`. The SMMU path preserves a pre-existing stream mapping and only
  creates a bypass context for this stream when it is unmapped; it does not
  alter global SMMU settings or other streams.
- GitHub Actions run `39439447885` built the FP6 kernel successfully (build
  job `118685115137`, 6m57s) and generated/uploaded the matching ADT. The
  `fp6-boot` packaging step skipped because repository variable
  `FP6_STOCK_DTB_URL` is unset.
- Downloaded CI kernel SHA256
  `9f7b6335a4d377779618832b22a49d8f69685ad1f133481218af11c61ecef3c7` and ADT
  SHA256 `9d9957b903bb091d91ab688788facee0432f2ddc8ade82081ad48239d65bc467`.
  Reused the exact stock FP6 DTB from the previous verified v2 boot image;
  its SHA256 `16a9e60e441772b5cf491a6b51dbe4829f5895fa284bcfa342623bc5b2287dc5`
  matches that image's manifest. Locally packaged the header-v2 UFS-root image
  at `/tmp/fp6-soc-39439447885/ufs-root/fp6-shim-ufs-root.img`, 22,917,120
  bytes, SHA256
  `3f557a3bbe16056d8e53a67dba70de89ba7aa693659be74946c77e33f41be2ad`.
  Its command line is `debug=0xc serial=3 cpus=8 keepsyms=1 -noprogress
  rd=ufsroot0`; packaging verified the embedded kernel, payload and DTB.
- Source/build/package results only. The new SMMU/UFS path has not been booted
  on hardware; the image leaves userdata and all partitions untouched. Next
  step is the user's temporary `fastboot boot` test, then use the resulting
  console/panic or root mount observation to tune the stream mapping and UFS
  command path.

## FP6 UFS root HFS mount fix (2026-10-20)

- User tested the UFS-root image from run `39439447885`. Phone output reported
  `userdata` on LUN 0, first block `0x666d88`, 213586 MiB, read-only, and an
  enabled SMMU stream entry for SID `0x60` (`SMR=0x80000060`). The selected
  `ufsroot0` device was then followed by root mount failure `errno 19`
  (`ENODEV`). This confirms discovery and root-device selection; SMMU mapping
  was already present and preserved.
- Traced the mount failure to FP6's generated master config: patch 0026 builds
  and registers the Apple OSS HFS implementation only when `SWEET_HFS` is
  enabled, but the new `MASTER.arm64.fp6` config omitted that option and the
  `sweet_hfs` filesystem selection. Added patch
  `0106-fp6-enable-hfs-root.patch` and pushed commit `4ce0c16`; it enables both
  for FP6 so `vfs_mountroot` registers HFS.
- CI run `39441508260` built successfully (build job `118692265513`, 7m30s).
  As before, automated boot packaging skipped because `FP6_STOCK_DTB_URL` is
  unset. Locally packaged the matching kernel/ADT and verified stock DTB as a
  header-v2 UFS-root image:
  `/tmp/fp6-hfs-39441508260/ufs-root/fp6-shim-ufs-root.img`, 23,396,352 bytes,
  SHA256 `ed7d3aeaa163215c375f1eb11b7068e3399f3c263831c5a9013533f41d2f19fd`.
  The manifest records kernel, ADT and DTB hashes and `rd=ufsroot0`; package
  validation confirmed the embedded components. This HFS-enabled image has
  not yet been booted on the phone.
- Follow-up phone output shows HFS finds an in-filesystem journal at offset
  `0x800000`, but journal-header update fails with `EINVAL` while the UFS
  device was initialized read-only. The root mount path deliberately defaults
  to read-only unless `ufsrw=1` is passed; HFS journal replay/update needs the
  custom userdata partition writable. Packaged a follow-up image with that
  explicit opt-in:
  `/tmp/fp6-hfs-rw-39441508260/ufs-root/fp6-shim-ufs-root-rw.img`, SHA256
  `74dda22095553a68ebd8cb61b2836b896440cb3908c728c02554fc075f839d30`.
  Its write path remains bounded to the GPT partition selected by `ufsroot`
  (`userdata` by default); it cannot address other UFS partitions. This
  read-write image has not yet been tested on the phone.

## UniXNU repository review (2026-10-20)

- Shallow-cloned the UniXNU build repository to `/home/ersa/Dev/UniXNU` with
  its shallow driver/kit submodules, the device repo to
  `/home/ersa/Dev/UniXNU-sheng` with its shallow touch/preflight submodules,
  and firmware repo to `/home/ersa/Dev/uefi-sheng`. Main repo commits at
  review: UniXNU `5725f11`, UniXNU-sheng `b409de2`, uefi-sheng `329b473`.
  All these checkouts were clean after cloning. Source review only: no build,
  tests or phone run was done.
- UniXNU-sheng targets Xiaomi Pad 6S Pro / SM8550 and boots through its own
  Mu-Silicium UEFI plus DarwinBoot flow. FP6 currently boots through the
  existing fastboot shim, so the UniXNU boot chain is a separate architecture
  choice; its driver repos can still be referenced or selectively ported.
- Most transferable source is at the interface/algorithm level: ARM CPU/GIC/
  timer, ADT matching, UFSHCI command handling, SMMUv2 4 KiB table code,
  framebuffer copy/present, GENI SPI transport, HID event publication and
  root-manifest verification. None should be assumed board-ready for FP6.
- Confirmed board-specific limits: NativeUfs matches `qcom,sm8550-ufshc` and
  hardcodes sheng GCC/UFS physical ranges and stream setup; NativeAdreno and
  AdrenoPM4 are A740-specific; NativeNovatekTouch is for the sheng NT36532E;
  NativeMobileDisplay uses firmware GOP/framebuffer scanout and has no hardware
  vblank. NativeMetal's demonstrated GPU path depends on the Adreno/Turnip stack.
- `kits/VerifiedRoot` implements an owner-key RSA-3072/SHA-256 block-manifest
  format; it is not Apple's Image4/APFS sealed-root authentication. NativeAES
  and NativeKeyStoreEvents do not implement QTEE communication or SEP-backed
  AppleKeyStore. Check each module's own license before copying; the collection
  mixes BSD-2-Clause-Patent, BSD-2-Clause, MIT, and Apache-2.0 code.
- The UniXNU organization page showed three top-level repositories at review;
  the build repo additionally pins 21 driver/kit submodules, and the sheng
  device repo adds two submodules. See the checked-out READMEs and source under
  `/home/ersa/Dev/UniXNU*` for exact per-module commits.

## FP6 USB log sender follow-up (2026-10-21)

- User reports the USB log stream is not usable for debugging and the Settings
  About page raises `RemoteMemoryException`. The crash is not diagnosed yet; a
  phone crash report or reliable kernel capture is needed before attributing it
  to the earlier SWEET `volumeTotalCapacity` issue.
- Patch 0125 removes socket-first delivery from the FP6 USB log sender. In 0114,
  `sock_send()` returning success advanced the ring cursor even if the packet was
  still queued behind route/ARP and never reached the host, so the raw Ethernet
  path was skipped. The sender now always emits the already-framed raw packet,
  retains its ring position on `ENOBUFS`, and waits 5 ms between successful
  packets to let the gadget's 32-entry TX queue drain.
- Source was based on CI build tree for run 39565043535 (success, head
  0755f4d2f6343b06cc0f5d31d31460b096330d3d). The modified `sweet_usb.c` passed
  `tools/xnu-cc.py` against that tree (`0 of 1 files failed`) using local Clang
  23. Initial CI run 39568643454 failed before compilation because the patch
  runner rejects zero-context diffs. Patch 0125 was regenerated with standard
  context, passed `git apply`, and built successfully in CI run 39569106154 on
  e21a51767ef7ca68ca796bb840431c8ef7810044. The CI build-tree `sweet_usb.c`
  matches the locally compiled file byte-for-byte (SHA-256
  `5f6d78f1a5f1120ee4e8f1b98de803a98d54e34a7490f2474e51cbf307e220c7`).
- CI's `fp6-boot` skipped packaging because `FP6_STOCK_DTB_URL` is unset. The
  kernel checksum passed (`601288b0a5ae4ac1af9d870a269673205be1856b75f72f7da48131c809bdf100`);
  ADT SHA-256 is `401b10b78b7d4d0480b630c76b78d3e2bbbfd2da1753bc1382e797ba54474f8a`.
  Locally packaged and header-v2 round-trip checked
  `/tmp/fp6-usb-39569106154/image/fp6-shim-ufs-root-pas-touch-usb-raw-paced.img`,
  SHA-256 `d25383cdb095111d6c8c600f2a0943eebc3f96ba31b37e1082a094945cdd6c01`,
  using the verified stock DTB (SHA-256
  `8198534128258bfe7b05bbb5b227affc181aa49b376884c08eae8564fce124e3`). Its
  args keep `fp6pas=1`, `fp6touch=2`, `fp6usb=2`, and the console visible.
- User's current tcpdump capture contained 233 UDP/5140 packets / 40,249 decoded
  bytes at inspection time. Decoded lines include kernel `CRASH assetsd` records
  and `exec ReportMemoryException`; this is not an About-specific stack trace.
  Capture remains active for the new-image test. `fastboot devices` returned
  zero, so this image has not been booted and the USB change is not yet
  phone-verified.

## FP6 battery and fuel-gauge source audit (2026-10-21)

- Inspected the exact stock DTB embedded in CI run 39569106154, decompiled to
  `/tmp/fp6-live.dts`, plus the Fairphone Volcano DTS and kernel sources. The
  DT has a PMK8550 ADC/RTC/PON/SDAM tree and a `qcom,power-telemetry` child
  marked `status = "disabled"`; it has no enabled local `qpnp-qg` fuel-gauge
  node. The battery-charger interface is instead a child of `qcom,pmic-glink`
  on `PMIC_RTR_ADSP_APPS`, with subsystem `lpass` and ADSP
  `msm/adsp/charger_pd` protection-domain dependency.
- The available `drivers/power/supply/qcom/qpnp-qg.c` only matches PM2250,
  PM6150, PMI632 and PM7250B configurations; its probe requires a parent
  regmap and battery-ID/thermistor ADC channels. It is not a PMK8550 driver
  that can be enabled by adding an XNU SPMI read. Historical SWEET
  `SweetBattery` in patch 0062 assumes a PM6150 fuel-gauge register map and
  estimates SOC from voltage; it must not be reused as FP6 telemetry.
- No FP6 code or device operation was made in this audit. Real SOC, current,
  charge state and temperature require the ADSP PMIC-GLink battery service
  (and its remote-processor/IPC prerequisites), or a separately validated
  PMK8550 telemetry implementation if the disabled QPT block's wire protocol
  can be established. An interim IOPMPowerSource would be a labeled static
  fallback, not a functioning fuel gauge.

## FP6 Adreno PAS ZAP loader patch correction (2026-10-21)

- CI run 39579222524 for commit 813e0ab failed while applying patch 0127 at
  `bsd/dev/sweet_ufs.c`: the patch used a zero-context declaration hunk that
  the strict patch runner could not locate. This was a patch-context failure;
  no compilation or phone test occurred in that run.
- A second attempt in commit f72c9d9 still failed at the first UFS hunk
  (line 56); no compile or phone test occurred. Rather than patch that file in
  a later step, remove the original UFS hook hunks from 0118 and 0122 as well
  as the attempted removal from 0127. The GPU inventory, PAS query and opt-in
  ZAP loader are registered together through `fp6_adreno_startup` at
  `EARLY_BOOT`. This eliminates all GPU references from the UFS driver and
  makes the patch series independent of that file's evolving context. Normal
  and ASan/UBSan host tests pass; a corrected CI build is still required before
  image packaging or phone testing.
- Commit e998189 built successfully in CI run 39581455083. The FP6 boot job
  skipped image packaging because the repository has no `FP6_STOCK_DTB_URL`.
  Locally packaged the matching kernel/ADT with the verified stock `tree-04`
  DTB and minimal RAM-disk init. Image
  `/tmp/fp6-zap-39581455083/image/fp6-shim-fp6zap.img` uses `fp6gpu=1`,
  `fp6pas=1`, `fp6zap=1`, `fp6touch=2`, and `fp6usb=2`; SHA256
  `2438d333a1d0a5e10ccf3ed8601916a0db61d010b0b535267beeeca83c27fc94`.
  The user booted it and reported this panic:
  `phystokv_range: illegal PA: 0x9ea9b000 phys base 0x900000000 size 0x100000000 @arm_vm_init.c:406`.
  Source audit confirms both ZAP cache-clean calls passed reserved carveout
  physical addresses with `phys=TRUE`; `clean_dcache` then calls
  `phystokv_range`, which rejects this carveout because it is outside XNU's
  managed RAM range. Fix patch 0127 to clean through the `ml_io_map_wcomb`
  virtual mapping (`phys=FALSE`). Updated the host harness to assert the mapped
  virtual addresses/flag. Normal and ASan/UBSan suites pass. This correction
  needs a new CI build and phone retest; the failed boot's USB NIC disappeared
  before capture started, so no PAS/ZAP SMC result is available.

## NativeUfs and Topaz cross-reference (2026-10-21)

- Read-only review of UniXNU/NativeUfs history: SMMU takeover entered in
  `31155a6`, with lower-context fallback in `04b748e`; later `33d9f64` and
  `af785c1` concern storage/FUA behavior. Its UFS driver quiesces requests,
  rejects stream conflicts, configures a pass-through context, fences writes,
  and validates readback. It does **not** build translation tables or program
  TTBR/TCR, TLBI, ATOS, Gunyah, or GPU DMA. Port its refusal/order/readback
  discipline only; its sheng addresses, SID and bypass mode are not FP6 values.
  Source: https://github.com/UniXNU/NativeUfs/commit/31155a6db21678df3c89d9d25b5711466d229369
- Read-only Topaz patch audit: its Wi-Fi patches 0113–0130 use Topaz's
  SM6225 modem/WLFW and GLINK/QRTR/QMI assumptions; no direct FP6 port is
  justified. Topaz README still reports no wallpaper provider, so there is no
  wallpaper implementation to lift. Surface patches 0131–0139 may inform the
  SweetSurface/CoreAnimation ABI after comparing with local 0109, but do not
  implement GPU execution. Display/DSI sequences target Topaz's 1080x2400
  panel; patch 0114's 1125x2436 logical canvas is a reference for the current
  FP6 status-bar work, not a physical panel configuration. Gold-cluster
  patches 0080–0082 are SM6225-specific; FP6 has its own 4/3/1 topology and
  those patches should not be copied.
  Source: https://github.com/MakrSas/ios-topaz
- FP6 translated-context patch 0131 host harness passes in normal and
  ASan/UBSan modes. RPMh ARC, GMU firmware, and XNU compile-helper tests pass.
  A local XNU object/syntax compile was attempted but could not start because
  `tools/xnu-cc.py` expects `/home/ersa/swift/usr/bin/clang`, which is absent
  on this host; only `/usr/bin/clang` is installed. Thus 0131 is not yet
  validated against the cached XNU compile commands or a CI kernel build, and
  no SMMU write has been tested on the phone. Do not claim GPU/Metal execution.

## FP6 iPhone X logical display canvas (2026-10-21)

- Status-bar experiment 0130 changes FP6's logical display provider to
  1125x2436 while preserving the stock 1116x2484 physical framebuffer. The
  framebuffer offset math centers the logical canvas (4-pixel horizontal crop
  per side and 24-pixel top/bottom bars); `present()` clears the unused rows.
  SweetHID now reports the same logical dimensions. This targets iPhone X
  userland layout and is separate from a native DSI/panel driver.
- `tools/mkadt.py` generated an ADT whose parsed `sweet,display` node reports
  canvas-width=1125 and canvas-height=2436. Patch 0130 applies cleanly to the
  cached XNU source. No XNU CI build or phone observation has tested this yet;
  it is included with the next GPU SMMU CI build at the user's request.

## FP6 GMU SMMU context programming correction (2026-10-21)

- Rechecked the `fp6smmu=2` context image against the local Fairphone
  `drivers/iommu/arm/arm-smmu` implementation. The initial probe omitted the
  AArch64/SEP fields in `TCR2` and Linux's S1 defaults in `CBAR`. It now uses
  `TCR2=0x00038011` (upstream SEP, AArch64 AS, 36-bit output PA) and
  `CBAR=0x0001f300` (S1 plus NSH walk configuration and WB fallback).
  `TCR=0x00802020` remains T0SZ=32, outer-shareable table walk, and EPD1;
  the 4 KiB TG0 encoding is zero. The probe refuses a context with nonzero
  FSR, clears stale W1C faults, invalidates/synchronizes its TLB before
  enabling the context, and installs the SID5 route last.
- Extended the FP6 MMIO harness to model FSR W1C behavior and require the
  expected `TCR2`, `CBAR`, and FSR-clear writes. The complete 11-test host suite
  passes; the GPU harness also passes ASan/UBSan, and `git diff --check` is
  clean. CI run 39611115127 failed on undeclared `delay()` calls. Added the
  missing XNU clock header; the next CI build is required to validate it. No
  SMMU write has been tested on the phone. Do not use the earlier 0131 build
  for a translated-context phone test.

## FP6 Adreno GPU TTBR1 allocator groundwork (2026-10-22)

- Added patch 0163's standalone GPU global-memory page-table core and a host
  harness. The core builds a 4 KiB, four-level TTBR1 tree for the Linux KGSL
  global aperture (`0x0001ff8000000000`, 20 MiB), limits output addresses to
  the measured 36-bit SMMU PA range, and emits Linux-style AF/nG/OSH/access
  permission/XN leaf attributes. The allocator also checks directly reserved
  ranges and supports live append plus republish for HFI MEM_ALLOC service.
- Patch 0163 also adds an external-backing entry point to the existing GMU
  domain, so a future `GFX_ACC | GMU_ACC` allocation can map the same physical
  pages in both domains. A one-off host C fixture verified the GMU PTE uses
  the supplied backing PA. The HFI service does not call either new API yet.
- `python3 tests/test_fp6_gpu_global_domain.py` passes, covering VA alignment,
  L3-boundary translation, permissions, idempotent replay, overlap refusal,
  bounds and live append. `git apply --check` passes for patch 0163. This is
  only the page-table component: it is not yet connected to `sweet_gpu.c`,
  does not configure GPU SID0/CB0, and does not yet service GFX_ACC requests.
- Linux source recheck confirms `arm_smmu_lpae_tcr()` shifts the LPAE TCR
  fields into TCR.T1, sets EPD0 and clears A1 for TTBR1. With 48-bit IAS,
  4 KiB TG1, outer-shareable noncoherent table walks and NC IRGN/ORGN, this
  yields candidate `TCR=0xa0100080`; the source encoding is now accounted for,
  but the value remains untested on FP6 hardware. GPU context activation and
  all firmware/GMU exchanges remain pending. No phone was accessed during
  this source and host-test pass.

## FP6 CB0 stage diagnostic host coverage (2026-10-23)

- Extended the GPU host harness to seed the measured disabled-but-nonzero CB0
  state, including TTBR/TCR/MAIR, and verify patch 0169's stage snapshot emits
  those values and an anomalous stream-group route without issuing any SMMU
  writes or changing any modeled register.
- `tests/test_gpu_probe.py` passed normally and under ASan/UBSan. The full
  Python test suite passed (13 tests, 5 skipped). The GMU runtime integration
  test now reports a skip when its pinned firmware blob is not present at
  `/tmp/fp6-firmware/gen80300_gmu.bin`; it still runs when that local artifact
  is available. This is host-only validation; it adds no new CI build or phone
  observation. Patch 0169 remains untested on the phone because fastboot was
  absent. The next useful hardware step remains its read-only CB0 stage image
  after the user has placed the FP6 in fastboot.

## FP6 Gen8.3 IOMMU/GPU boot ordering source review (2026-10-23)

- Fairphone source shows KGSL attaches its GPU user SMMU domain during IOMMU
  probe, then installs the default TTBR0 and SMMU aperture. Later
  `kgsl_iommu_start()` applies page-fault policy/PRR state. On cold boot,
  `gen8_hwsched_first_boot()` runs GMU first boot before GPU boot; GPU boot then
  starts MMU policy, takes GPU OOB, runs `gen8_start()`, enables IRQs, loads
  SQE/AQE bases and starts the scheduler. Ring startup programs the ring,
  starts SQE, sends Gen8 CP initialization, authenticates ZAP and leaves secure
  mode. This gives the ordering constraint for HFI MEM_ALLOC: complete and
  publish each requested GPU/GMU map before replying, then retain backing until
  a proven quiesce.
- This is source inspection only; it does not explain the measured disabled,
  nonzero CB0 state or prove the XNU mapping path. Keep the next 0169 phone boot
  read-only and compare CB0 at each stage before any first write. The detailed
  source references are in `docs/FP6_ADRENO_METAL_AUDIT.md`.
