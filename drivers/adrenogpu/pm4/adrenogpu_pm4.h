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

struct adrenogpu_pass {
	unsigned width, height;
	struct adrenogpu_color_target color;
	uint64_t border_color_va;
};

/* Restore, fd6_emit_sysmem_prep, the attachments and fd6_emit_sysmem, without the load-action clear (the 2D
 * clear is a later step). */
void adrenogpu_pm4_emit_pass_begin(struct adrenogpu_cs *, const struct adrenogpu_pass *,
    const struct adrenogpu_gmem_config *sysmem);
/* CP_DRAW_INDX_OFFSET, auto-index (no index buffer), visibility use as Turnip emits it. */
void adrenogpu_pm4_emit_draw_auto(struct adrenogpu_cs *, unsigned prim_type, unsigned instances, unsigned vertices);
/* End of pass. Measured on the Adreno 810 (NOTES.md, 2026-10-24): the draw must drain first, so a
 * CP_WAIT_FOR_IDLE comes before any CCU or cache clean; without it the last pixels are lost. */
void adrenogpu_pm4_emit_pass_end(struct adrenogpu_cs *);
#endif
