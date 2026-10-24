# AdrenoGPU PM4 builder

`Fp6A8xxRegs.h` is generated: the A8XX view of Mesa's freedreno register database (pinned Mesa
`6a7d3020a781`, the tree our Turnip captures come from), written by `tools/gen-a8xx-regs.py`.

    python3 tools/gen-a8xx-regs.py --mesa <mesa checkout> --out drivers/adrenogpu/pm4/Fp6A8xxRegs.h

The generator is the MIT-licensed `tools/gen-a8xx-regs.py` of the Snapintosh project, copied unchanged
(upstream `2c60b47`); the header keeps Mesa's own licence notice. Regenerating must give byte-identical output.

The builder checks its streams against Turnip's with `tools/fp6-pm4-state.py`, which walks a capture
(following indirect buffers and draw-state groups) and returns the register state at the draw, or with `--packets`
every packet in stream order, and with `--sysmem` skips draw-state groups that are not enabled for direct rendering
(the binning-only VS group otherwise overwrites the render-pass VS state).
Rule learned on the phone (see `NOTES.md`, 2026-10-24): after a draw, `CP_WAIT_FOR_IDLE` and then
`CCU_CLEAN_COLOR`, `CCU_CLEAN_DEPTH`, `CACHE_CLEAN` before anything reads the draw's output, otherwise the last
pixels are lost on this part (textures, depth and vertex scenes came out wrong).

## What exists (`adrenogpu_pm4.{h,c}`, tests in `tests/test_adrenogpu_pm4*.py`)

Verified means: compared with a Turnip A810 capture (fixtures `tests/fixtures/turnip-a810-*.rd`, Mesa through the
noop shim, no device data) and equal. Ported means: written from Turnip's or Snapintosh's source without a capture
to check it against.

| piece | status |
|---|---|
| restore sequence, GMEM layout, sysmem pass begin, auto draw, drained pass end | verified (134 registers of the draw state, as before) |
| load-action clear, `ADRENOGPU_CLEAR_GENERIC` | verified packet for packet on flat, blend and flatclr (three clear colours) |
| load-action clear, `ADRENOGPU_CLEAR_2D` register sequence | verified packet for packet against Turnip's A810 `vkCmdFillBuffer` (the only 2D solid fill Turnip emits on this part; linear R32_UINT buffer); the image-destination flag-buffer block is verified against the texture capture's buffer-to-image copy |
| flush brackets around the 2D clear | ported from Snapintosh, not in any Turnip stream, not tested on the phone |
| shader program (VS + FS pair) | verified: the register writes of Turnip's program groups (config, VS, HS/DS/GS placeholders, VPC, FS), in order, for flat and varying; whole draw state for flat, varying, blend, flatclr |
| the other program features (flat interpolation, vertex attributes, sysvals, outputs, private memory, bindless/sampler counts) | ported; the capture scenes have none of them, so the paths run but only their zero values are checked |

### The clear is not a 2D clear on the A810

The task description (and `HANDOFF.md`) assumed Turnip clears a sysmem colour target with the 2D engine, as the
Snapintosh emitter does. It does not on this part: `a7xx_gen3` (inherited by the A810) sets `has_generic_clear`, and
`tu_emit_subpass_begin_sysmem` returns early. Turnip clears render-pass attachments through the resolve engine
(`tu7_generic_clear_attachment`): a blit event with `BLIT_EVENT_CLEAR` in a `CP_COND_REG_EXEC` for GMEM or sysmem,

    CP_COND_REG_EXEC 0x3c000000, 27 dwords
      RB_RESOLVE_CNTL_1/2 (blit scissor)   RB_RESOLVE_CLEAR_COLOR_DW0..3   RB_RESOLVE_GMEM_BUFFER_INFO
      RB_RESOLVE_CNTL_0   RB_RESOLVE_OPERATION (TYPE=2, mask 0xf, buffer id 0)
      RB_RESOLVE_SYSTEM_BUFFER_INFO/BASE/PITCH   RB_RESOLVE_SYSTEM_FLAG_BUFFER_BASE/PITCH   RB_RESOLVE_GMEM_BUFFER_BASE
      CCU_RESOLVE
    CCU_END_RESOLVE_GROUP                                   (outside the conditional block)

That is the builder's default clear; it is what the phone ran when it replayed Turnip's captures (`NOTES.md`,
2026-10-23: "clear, draw and blit all produced the expected values"). Snapintosh uses the 2D engine because the
generated A8XX header has none of the `RB_RESOLVE_*` registers beyond `CNTL_1/2/3` and `GMEM_BUFFER_INFO`: the generator
keeps only the A8XX variant view of `a6xx.xml` and drops the rest. The builder defines the missing offsets locally
(`REG_RB_RESOLVE_*`, `REG_RB_A2D_DEST_FLAG_BUFFER_BASE`, the VPC stereo and stream-out registers), from `a6xx.xml`
and checked by the captures, and does not touch the generated header. `RB_RESOLVE_SYSTEM_BUFFER_INFO` keeps the
A6XX field layout (tile mode 0-1, flags 2, samples 3-4, swap 5-6, format 7-14).

Colour clear values: `adrenogpu_pack_clear_unorm8` rounds `x * 255` to nearest even. The generic clear takes the four
bytes packed in `RB_RESOLVE_CLEAR_COLOR_DW0` (R in the low byte for every RGBA/BGRA target, the swap applies on
output), the 2D clear one byte per `RB_A2D_CLEAR_COLOR_DWn`. Only `FMT6_8_8_8_8_UNORM` linear-colour targets are
supported; sRGB, 10-bit, float and integer targets make the builder set `cs->err` instead of guessing.

Where the 2D clear differs from Snapintosh's `emit_2d_clear`, following Turnip's A810 `fill2d` stream (the truth):
the registers are written as `pkt4` packets in `r2d_setup_common` / `r2d_clear_value` / `r2d_dst` / `r2d_coords` order
(Snapintosh puts them in non-context register bunches, around a `RM6_BLIT2DSCALE` marker that Turnip does not emit);
an image destination also gets `RB_A2D_DEST_FLAG_BUFFER_BASE` (0x8c20, base = the image address, pitch 0); the
sRGB case Snapintosh handles (encoded value through the plain UNORM path) is refused here because Turnip would use
`R2D_UNORM8_SRGB` and `SP_A2D_OUTPUT_INFO.SRGB`, and neither path has a capture. The flush brackets
(`CCU_CLEAN/INVALIDATE_COLOR`, `DUMMY`, `SUBPASS_FENCE`, `CCHE_INVALIDATE`, drains) are Snapintosh's; the host test only
checks their shape (a drain before and after the fill, a clean after). The clear is emitted after the attachment
registers (Turnip emits it first); every register it sets reaches the same final value either way, and the draw
state still matches.

### Shader program state

`struct adrenogpu_program` is what the shader compiler fills: per stage the instruction base address, `instrlen`,
`constlen`, register footprints (`max_reg + 1`, `max_half_reg + 1`), branch stack, merged-regs / early-preamble flags,
the constant-data UBO (index, offset from the binary, size), private memory and bindless/sampler counts; for the VS the
vertex-id / instance-id / view-id / primitive-id registers, the attribute inputs and the position output register;
for the FS the varyings (`inloc`, component mask, flat, and the VS output register feeding each), `total_in`, thread size,
the system-value registers (barycentrics, coordinates, face, sample id/mask, shading rate) and the colour outputs
with their aliased-constant components, depth/sample-mask/stencil output registers. Register ids are ir3 `regid(n, c)`
with `ADRENOGPU_REGID_INVALID` (0xfc) for none. `adrenogpu_pm4_emit_program` ports `tu6_emit_program_config`,
`tu6_emit_xs` / `tu6_emit_vs` / `tu6_emit_vfd_dest` (VS), `tu6_emit_hs/ds/gs` with no shader, `tu6_emit_vpc` (with
`ir3_link_shaders` and `tu6_vpc_varying_mode` for a VS as the last geometry stage), `tu6_emit_fs` /
`tu6_emit_fs_inputs` / `tu6_emit_fs_outputs`, and the constant-data `CP_LOAD_STATE6` UBO descriptor of
`tu6_emit_xs_constants`. The chip parameters it needs (`prim_alloc_threshold` 7,
`has_implicit_fragface_fragcoord_ij_linear`) are in `struct adrenogpu_chip`.

The tests read the program fields back out of each capture's registers (and the `CP_LOAD_STATE6` packet), build a
`struct adrenogpu_program` from them, emit pass and program, and compare:
the builder's program section equals the register writes of Turnip's non-binning program groups (`PROGRAM_CONFIG`, `VS`,
`HS`, `DS`, `GS`, `VPC`, `FS`), write for write and in order, for flat and varying; the whole register state at the draw
equals Turnip's for every register the builder writes, except `GRAS_SC_BIN_CNTL` / `RB_CNTL` (LRZ feedback mode),
`VPC_SO_OVERRIDE` and `SP_UPDATE_CNTL` (set by pipeline and descriptor-set state, outside the program); and every
register Turnip has that the builder does not write is on an explicit list of fixed-function state (rasteriser,
viewport, scissor, depth, stencil, blend, MRT control, per-draw offsets, a few static registers). That list is the
work that remains before the builder can draw anything other than the flat/varying triangles.

Differences from Snapintosh's `emit_program_config` / `emit_shader_regs` / `emit_program_linkage` /
`emit_interp_regs` found by reading it against Turnip's A810 stream (Snapintosh was not run):

- `PC_STEREO_RENDERING_CNTL` is written 0 there; Turnip writes 6 (`DISABLEMULTIPOS`, one view) and also
  `VFD_STEREO_RENDERING_CNTL` 6, and the A7XX `VPC_STEREO_RENDERING_CNTL` (0x931a) 6 and `..._VIEWMASK` (0x90c1) 0.
- The streamout-off registers (`VPC_SO_MAPPING_WPTR` 0x9180, `VPC_SO_CNTL`, `PC_DGEN_SO_CNTL` 0x9b0b) are written by
  Turnip's `tu6_emit_vpc` and not by Snapintosh's linkage.
- `VPC_VARYING_INTERP_MODE_MODE` / `REPLACE_MODE` are written for all eight words there; Turnip writes only as many
  words as the varyings reach, and none for a pair without varyings (flat).
- `SP_LB_PARAM_LIMIT` / `RB_LB_PARAM_LIMIT` carry a literal 7; here it is the chip's `prim_alloc_threshold`.
- `SP_PS_CNTL_1.SYSVAL_REGS_COUNT` there ignores the shading-rate register; Turnip counts it.
- `RB_PS_INPUT_CNTL` / `GRAS_LRZ_PS_INPUT_CNTL` fix `FRAGCOORD_CENTER` there; Turnip selects `FRAGCOORD_SAMPLE` for sample shading.
- `SP_RENDER_CNTL` is written inside the linkage there; in Turnip it belongs to the rasteriser group, so it is not in
  the program here.
- Snapintosh links a point size output (`PSIZELOC`, `PC_VS_CNTL.PSIZE`); the builder refuses VS outputs other than position.

Not supported, and refused with `cs->err` instead of emitted unchecked: tessellation, geometry shaders, stream-out,
multiview, sampler prefetch, point size, layer/viewport/shading-rate outputs, clip/cull distances, primitive id,
point sprites, double-thread-size fragment shaders (`SP_PS_WAVE_CNTL` has no thread-size field in the A8XX layout; the
A6XX one is not checked), more than 32 VPC outputs, misaligned shader addresses. Driver-parameter UBOs, immediate constants
and dynamic-offset constants (the other `tu6_emit_xs_constants` / `tu6_emit_dynamic_offset` packets) are not built.
Flat interpolation modes and vertex attributes are ported but no scene exercises them; the next captures to add are
`vertexbuf` (attributes) and a flat-varying scene.

### Fixtures

All made by `tools/fp6-vk-scenes.c` (scene runner) with Mesa `6a7d3020a781` Turnip through the freedreno noop shim,
`FD_GPU_ID=810 TU_GMEM=622592 TU_DEBUG=sysmem,noubwc,syncdraw`, recipe in `HANDOFF.md`. `FD_RD_DUMP_PATH` must name an
existing directory, otherwise Turnip spins in `fd_rd_output_write`. New scenes: `flatclr` (flat, cleared to
0.25/0.5/0.75/1) and `fill2d` (`vkCmdFillBuffer`, no pass or draw).

| fixture | scene |
|---|---|
| `turnip-a810-flat.rd` | flat triangle, clear (0, 0, 0, 1) |
| `turnip-a810-varying.rd` | one smooth varying (vec4, location 0) |
| `turnip-a810-blend.rd` | blend scene, clear (0, 0, 1, 1) |
| `turnip-a810-flatclr.rd` | flat, clear (0.25, 0.5, 0.75, 1) |
| `turnip-a810-fill2d.rd` | `vkCmdFillBuffer`: Turnip's 2D solid fill |
| `turnip-a810-texture.rd` | texture scene; supplies the 2D image-destination block |
