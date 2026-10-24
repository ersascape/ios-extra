/* SPDX-License-Identifier: MIT */
/* AdrenoGPU PM4 builder for the Adreno 810 (A8xx gen 8.3): the command stream a user-space renderer submits.
 *
 * Structure and register sequences follow Mesa Turnip's A8XX sysmem path (fd6_emit_restore, fd6_emit_sysmem_prep,
 * fd6_emit_flushes) as ported by Snapintosh's MIT-licensed SnapMetal emitter; the GMEM layout calculation is
 * Mesa's fd6_calc_gmem_cache_offsets (MIT). Chip constants are explicit parameters, not the X2-90 numbers the
 * Snapintosh emitter writes inline. Every register comes from the generated Fp6A8xxRegs.h. Pure C. */
#ifndef ADRENOGPU_PM4_H
#define ADRENOGPU_PM4_H
#include <stddef.h>
#include <stdint.h>

/* ---- command stream writer ---- */
struct adrenogpu_cs {
	uint32_t *w;
	size_t n, cap;
	int err; /* set on overflow or a bad packet; the stream is then unusable */
};

void adrenogpu_cs_init(struct adrenogpu_cs *, uint32_t *buffer, size_t capacity_dwords);
void adrenogpu_cs_pkt7(struct adrenogpu_cs *, unsigned opcode, const uint32_t *payload, unsigned count);
void adrenogpu_cs_event(struct adrenogpu_cs *, unsigned event); /* CP_EVENT_WRITE7 with no memory write */
void adrenogpu_cs_wfi(struct adrenogpu_cs *);

struct adrenogpu_reg { uint32_t offset, value; };
struct adrenogpu_regs {
	unsigned n;
	struct adrenogpu_reg p[256];
	int err;
};
void adrenogpu_regs_add(struct adrenogpu_regs *, uint32_t offset, uint32_t value);
void adrenogpu_cs_pkt4(struct adrenogpu_cs *, const struct adrenogpu_regs *); /* consecutive registers */
void adrenogpu_cs_crb(struct adrenogpu_cs *, const struct adrenogpu_regs *);  /* CP_CONTEXT_REG_BUNCH pairs */
void adrenogpu_cs_ncrb(struct adrenogpu_cs *, const struct adrenogpu_regs *); /* CP_NON_CONTEXT_REG_BUNCH */

/* ---- chip parameters and the GMEM layout (Mesa fd_dev_info props, fd6_gmem_cache.h) ---- */
struct adrenogpu_chip {
	unsigned num_ccu;
	/* shader program state */
	unsigned prim_alloc_threshold;                      /* SP/RB_LB_PARAM_LIMIT.PRIMALLOCTHRESHOLD */
	int has_implicit_fragface_fragcoord_ij_linear;
	/* sysmem rendering */
	unsigned sysmem_vpc_attr, sysmem_vpc_pos, sysmem_vpc_bv_pos;
	unsigned sysmem_ccu_color_fraction, sysmem_per_ccu_color, sysmem_ccu_depth_fraction, sysmem_per_ccu_depth;
	/* GMEM (tiled) rendering */
	unsigned gmem_vpc_attr, gmem_vpc_pos, gmem_vpc_bv_pos;
	unsigned gmem_ccu_color_fraction, gmem_per_ccu_color, gmem_ccu_depth_fraction, gmem_per_ccu_depth;
};

struct adrenogpu_gmem_config {
	uint32_t color_ccu_offset, depth_ccu_offset;
	uint32_t vpc_attr_size, vpc_attr_offset, vpc_pos_size, vpc_pos_offset, vpc_bv_pos_size, vpc_bv_pos_offset;
	uint32_t depth_fraction, color_fraction, depth_cache_size, color_cache_size;
};

/* Mesa's A810 profile: num_ccu 1, a8xx gen1 sysmem sizes, GMEM-mode VPC sizes 16384/12288/20480. */
struct adrenogpu_chip adrenogpu_chip_a810(void);
/* Lay out sysmem and GMEM configs from the top of gmem_bytes downwards. Returns the lowest offset used,
 * which exceeds gmem_bytes (wraps negative) when the layout does not fit. */
unsigned adrenogpu_calc_gmem_layout(const struct adrenogpu_chip *, unsigned gmem_bytes,
    struct adrenogpu_gmem_config *gmem, struct adrenogpu_gmem_config *sysmem);

/* ---- sequences ---- */
/* fd6_emit_restore for sysmem rendering: LRZ and cache invalidation, static non-context and context state,
 * draw-state reset, and the sysmem GMEM cache configuration. */
void adrenogpu_pm4_emit_restore(struct adrenogpu_cs *, const struct adrenogpu_gmem_config *sysmem,
    uint64_t border_color_va);

/* ---- one sysmem render pass: one linear or tiled colour target, no depth, MSAA off ---- */
struct adrenogpu_color_target {
	uint64_t va;            /* GPU virtual address of level 0 */
	uint32_t pitch;         /* bytes per row */
	uint32_t layer_bytes;   /* bytes per layer (RB_MRT_ARRAY_PITCH) */
	unsigned rb_format;     /* A8XX_E_FMT6_* colour format */
	unsigned swap;          /* A8XX_E_WZYX or WXYZ */
	unsigned tile_mode;     /* A8XX_E_TILE6_* */
	unsigned srgb;
};

/* Load action of the colour target. GENERIC is what Turnip emits on the A810 (has_generic_clear: the resolve
 * engine's blit event with BLIT_EVENT_CLEAR, tu7_generic_clear_attachment); verified packet for packet. 2D is the
 * 2D-engine solid fill (r2d_ops, what Turnip uses for vkCmdFillBuffer and Snapintosh's emit_2d_clear uses for the
 * load action) with flush brackets around it; its register sequence is verified against Turnip's A810 2D fill. */
enum adrenogpu_clear_mode { ADRENOGPU_CLEAR_NONE = 0, ADRENOGPU_CLEAR_GENERIC, ADRENOGPU_CLEAR_2D };

struct adrenogpu_pass {
	unsigned width, height;
	struct adrenogpu_color_target color;
	uint64_t border_color_va;
	unsigned clear_mode;   /* enum adrenogpu_clear_mode */
	float clear_rgba[4];   /* linear RGBA, used when clear_mode is not NONE; 8-bit UNORM targets only */
};

/* UNORM8 clear words: packed is the generic clear's single word (R in the low byte), words the 2D clear's four
 * per-channel values. Rounds to nearest even like Mesa's _mesa_lroundevenf of the clamped value times 255. */
void adrenogpu_pack_clear_unorm8(const float rgba[4], uint32_t *packed, uint32_t words[4]);

/* ---- 2D engine solid fill (RB/GRAS/SP_A2D registers, CP_BLIT SCALE), as r2d_setup/clear_value/dst/coords/run ---- */
struct adrenogpu_blit_dest {
	uint64_t va;
	uint32_t pitch;       /* bytes per row; 0 for a one-row buffer fill */
	unsigned rb_format;   /* A8XX_E_FMT6_* */
	unsigned swap, tile_mode;
	int is_image;         /* images also get RB_A2D_DEST_FLAG_BUFFER_BASE (Turnip's r2d_dst), buffers do not */
};
struct adrenogpu_clear_2d {
	struct adrenogpu_blit_dest dest;
	unsigned ifmt;            /* A8XX_E_R2D_* */
	unsigned output_ifmt;     /* A8XX_E_OUTPUT_IFMT_2D_* */
	uint32_t words[4];        /* RB_A2D_CLEAR_COLOR_DW0..3 */
	unsigned x, y, w, h;
};
void adrenogpu_pm4_emit_clear_2d(struct adrenogpu_cs *, const struct adrenogpu_clear_2d *);

/* Restore, fd6_emit_sysmem_prep, the attachments and fd6_emit_sysmem, then the load-action clear when
 * pass->clear_mode asks for one (Turnip's order puts the clear before the attachment registers; this builder
 * emits it last, which leaves the register state at the draw identical). */
void adrenogpu_pm4_emit_pass_begin(struct adrenogpu_cs *, const struct adrenogpu_pass *,
    const struct adrenogpu_gmem_config *sysmem);
/* CP_DRAW_INDX_OFFSET, auto-index (no index buffer), visibility use as Turnip emits it. */
void adrenogpu_pm4_emit_draw_auto(struct adrenogpu_cs *, unsigned prim_type, unsigned instances, unsigned vertices);
/* ---- shader program state: a vertex + fragment shader pair ----
 *
 * A plain description of the compiled pair, to be filled by the shader compiler (every field is a value Turnip reads
 * from an ir3_shader_variant; the names say which). Registers are r<n>.<c> numbered as ir3 regid(n, c) = 4 * n + c,
 * ADRENOGPU_REGID_INVALID (regid(63, 0)) meaning "none". Supported: no tessellation, geometry shader, stream-out,
 * multiview, sampler prefetch, point size, layer, viewport index, clip/cull distances, primitive id or point sprites;
 * anything else is refused by setting cs->err rather than emitted unchecked. */
#define ADRENOGPU_REGID_INVALID 0xfcu
#define ADRENOGPU_MAX_VARYINGS 32
#define ADRENOGPU_MAX_VS_ATTRS 32

struct adrenogpu_xs {
	uint64_t base_va;           /* instruction memory, 128-byte aligned (SP_xS_BASE) */
	uint32_t instrlen;          /* ir3 instrlen, in 128-byte units (SP_xS_INSTR_SIZE) */
	uint32_t constlen;          /* constant file length in vec4 (SP_xS_CONST_CONFIG.CONSTLEN) */
	unsigned half_reg_footprint, full_reg_footprint; /* info.max_half_reg + 1, info.max_reg + 1 */
	unsigned branchstack;       /* ir3_shader_branchstack_hw */
	int mergedregs, early_preamble;
	/* constant data the shader reads through an UBO (const_state->consts_ubo), uploaded as a descriptor */
	int const_ubo_idx;          /* -1: none */
	uint32_t const_data_offset; /* from base_va (info.constant_data_offset) */
	uint32_t const_data_size;   /* bytes (xs->constant_data_size) */
	/* private memory (all zero when the shader has none) */
	uint32_t pvtmem_per_fiber_size, pvtmem_per_sp_size;
	uint64_t pvtmem_va;
	int pvtmem_per_wave;
	/* SP_xS_CONFIG: bindless flags, the number of samplers (tu_pipeline.cc writes it to both NTEX and NSAMP), UAVs */
	int bindless_tex, bindless_samp, bindless_uav, bindless_ubo;
	unsigned num_samp, num_uav;
};

struct adrenogpu_vs_attr { uint8_t regid, writemask; }; /* VFD_DEST_CNTL_INSTR; unused slot: invalid regid, mask 0 */

struct adrenogpu_varying {      /* one fragment-shader input and the vertex-shader output feeding it (ir3_link_shaders) */
	uint8_t inloc;              /* fs->inputs[i].inloc */
	uint8_t compmask;           /* fs->inputs[i].compmask */
	uint8_t flat;               /* fs->inputs[i].flat */
	uint8_t vs_regid;           /* register of the matching vs->outputs[k] */
};

struct adrenogpu_program {
	struct adrenogpu_xs vs, fs;
	/* vertex shader */
	uint8_t vs_vertexid_regid, vs_instanceid_regid, vs_viewid_regid, vs_primid_regid;
	unsigned vs_attr_in;                       /* vs->attr_in */
	struct adrenogpu_vs_attr vs_attr[ADRENOGPU_MAX_VS_ATTRS];
	uint8_t vs_position_regid;                 /* VARYING_SLOT_POS output, xyzw */
	/* fragment shader inputs */
	unsigned fs_total_in;                      /* fs->total_in: varying locations */
	unsigned fs_num_varyings;
	struct adrenogpu_varying fs_varying[ADRENOGPU_MAX_VARYINGS];
	int fs_double_threadsize, fs_need_full_quad, fs_need_pixlod, fs_sample_shading, fs_post_depth_coverage, fs_frag_face;
	uint8_t fs_face_regid, fs_sampleid_regid, fs_samplemask_in_regid, fs_shading_rate_regid, fs_coord_regid;
	uint8_t fs_ij_regid[7];                    /* enum ir3_bary order: persp pixel, persp sample, persp centroid,
	                                              persp center rhw, linear pixel, linear centroid, linear sample */
	uint8_t fs_fragcoord_compmask;
	/* fragment shader outputs */
	uint8_t fs_color_regid[8];                 /* ir3_get_output_regid without the half bit; invalid: none */
	uint8_t fs_color_half[8];
	uint32_t fs_aliased_components;            /* fragdata->aliased_components << (4 * rt), output taken from constants */
	uint8_t fs_depth_regid, fs_samplemask_regid, fs_stencilref_regid;
	int fs_dual_src_blend;
};
/* Emits the program groups Turnip builds for one pipeline's non-binning draw: program config, VS, VPC linkage, FS.
 * Returns through cs->err on anything unsupported (see above). */
void adrenogpu_pm4_emit_program(struct adrenogpu_cs *, const struct adrenogpu_chip *, const struct adrenogpu_program *);

/* End of pass. Measured on the Adreno 810 (NOTES.md, 2026-10-24): the draw must drain first, so a
 * CP_WAIT_FOR_IDLE comes before any CCU or cache clean; without it the last pixels are lost. */
void adrenogpu_pm4_emit_pass_end(struct adrenogpu_cs *);
#endif
