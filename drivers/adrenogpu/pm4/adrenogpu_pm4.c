/* SPDX-License-Identifier: MIT */
#include "adrenogpu_pm4.h"
#include "Fp6A8xxRegs.h"
#include <string.h>

/* ---- stream writer ---- */
void
adrenogpu_cs_init(struct adrenogpu_cs *cs, uint32_t *buffer, size_t capacity)
{
	cs->w = buffer;
	cs->n = 0;
	cs->cap = capacity;
	cs->err = 0;
}

static void
put(struct adrenogpu_cs *cs, uint32_t word)
{
	if (cs->n >= cs->cap) {
		cs->err = 1;
		return;
	}
	cs->w[cs->n++] = word;
}

void
adrenogpu_cs_pkt7(struct adrenogpu_cs *cs, unsigned opcode, const uint32_t *payload, unsigned count)
{
	if (opcode > A8XX_PKT7_OPCODE_MASK || count > A8XX_PKT7_COUNT_MASK || (count && !payload)) {
		cs->err = 1;
		return;
	}
	put(cs, a8xx_pkt7_hdr(opcode, count));
	for (unsigned i = 0; i < count; i++) put(cs, payload[i]);
}

#define PKT7(cs, op, ...) do { const uint32_t _p[] = { __VA_ARGS__ }; \
	adrenogpu_cs_pkt7((cs), (op), _p, (unsigned)(sizeof _p / sizeof *_p)); } while (0)

void
adrenogpu_cs_event(struct adrenogpu_cs *cs, unsigned event)
{
	PKT7(cs, A8XX_E_CP_EVENT_WRITE7, A8XX_PKT_CP_EVENT_WRITE7_0__EVENT(event) |
	    A8XX_PKT_CP_EVENT_WRITE7_0__WRITE_SRC(A8XX_E_EV_WRITE_USER_32B) |
	    A8XX_PKT_CP_EVENT_WRITE7_0__WRITE_DST(A8XX_E_EV_DST_RAM));
}

void
adrenogpu_cs_wfi(struct adrenogpu_cs *cs)
{
	adrenogpu_cs_pkt7(cs, A8XX_E_CP_WAIT_FOR_IDLE, NULL, 0);
}

void
adrenogpu_regs_add(struct adrenogpu_regs *r, uint32_t offset, uint32_t value)
{
	if (r->n >= sizeof r->p / sizeof *r->p) {
		r->err = 1;
		return;
	}
	r->p[r->n].offset = offset;
	r->p[r->n].value = value;
	r->n++;
}

void
adrenogpu_cs_pkt4(struct adrenogpu_cs *cs, const struct adrenogpu_regs *r)
{
	if (r->err || !r->n || r->n > A8XX_PKT4_COUNT_MASK || r->p[0].offset > A8XX_PKT4_REG_MASK) {
		cs->err = 1;
		return;
	}
	for (unsigned i = 1; i < r->n; i++)
		if (r->p[i].offset != r->p[i - 1].offset + 1) {
			cs->err = 1;
			return;
		}
	put(cs, a8xx_pkt4_hdr(r->p[0].offset, r->n));
	for (unsigned i = 0; i < r->n; i++) put(cs, r->p[i].value);
}

void
adrenogpu_cs_crb(struct adrenogpu_cs *cs, const struct adrenogpu_regs *r)
{
	if (r->err || 2u * r->n > A8XX_PKT7_COUNT_MASK) {
		cs->err = 1;
		return;
	}
	put(cs, a8xx_pkt7_hdr(A8XX_E_CP_CONTEXT_REG_BUNCH, 2u * r->n));
	for (unsigned i = 0; i < r->n; i++) {
		put(cs, r->p[i].offset);
		put(cs, r->p[i].value);
	}
}

void
adrenogpu_cs_ncrb(struct adrenogpu_cs *cs, const struct adrenogpu_regs *r)
{
	if (r->err || 2u + 2u * r->n > A8XX_PKT7_COUNT_MASK) {
		cs->err = 1;
		return;
	}
	put(cs, a8xx_pkt7_hdr(A8XX_E_CP_NON_CONTEXT_REG_BUNCH, 2u + 2u * r->n));
	put(cs, 1);
	put(cs, 0);
	for (unsigned i = 0; i < r->n; i++) {
		put(cs, r->p[i].offset);
		put(cs, r->p[i].value);
	}
}

/* Register add with array bounds: R(&r, NAME, index, value). */
#define R(r, NAME, i, v) do { \
	_Static_assert(A8XX_REG_##NAME##__BIT_SIZE == 32, #NAME " is a 32-bit register"); \
	adrenogpu_regs_add((r), A8XX_REG_##NAME + (uint32_t)(i) * A8XX_REG_##NAME##__ARRAY_STRIDE, (uint32_t)(v)); \
	if ((unsigned)(i) >= A8XX_REG_##NAME##__ARRAY_COUNT) (r)->err = 1; } while (0)
/* 64-bit register: low then high dword. */
#define R64(r, NAME, i, v) do { \
	_Static_assert(A8XX_REG_##NAME##__BIT_SIZE == 64, #NAME " is a 64-bit register"); \
	uint32_t _o = A8XX_REG_##NAME + (uint32_t)(i) * A8XX_REG_##NAME##__ARRAY_STRIDE; \
	adrenogpu_regs_add((r), _o, (uint32_t)(uint64_t)(v)); adrenogpu_regs_add((r), _o + 1, (uint32_t)((uint64_t)(v) >> 32)); \
	if ((unsigned)(i) >= A8XX_REG_##NAME##__ARRAY_COUNT) (r)->err = 1; } while (0)
#define F(NAME, FIELD, v) A8XX_REG_##NAME##__##FIELD(v)

/* ---- chip parameters and layout ---- */
struct adrenogpu_chip
adrenogpu_chip_a810(void)
{
	struct adrenogpu_chip c;
	memset(&c, 0, sizeof c);
	c.num_ccu = 1;
	c.sysmem_vpc_attr = 131072; c.sysmem_vpc_pos = 65536; c.sysmem_vpc_bv_pos = 32768;
	c.sysmem_ccu_color_fraction = A8XX_E_CCU_CACHE_SIZE_FULL; c.sysmem_per_ccu_color = 128 * 1024;
	c.sysmem_ccu_depth_fraction = A8XX_E_CCU_CACHE_SIZE_FULL; c.sysmem_per_ccu_depth = 256 * 1024;
	c.gmem_vpc_attr = 16384; c.gmem_vpc_pos = 12288; c.gmem_vpc_bv_pos = 20480;
	c.gmem_ccu_color_fraction = A8XX_E_CCU_CACHE_SIZE_EIGHTH; c.gmem_per_ccu_color = 16 * 1024;
	c.gmem_ccu_depth_fraction = A8XX_E_CCU_CACHE_SIZE_FULL; c.gmem_per_ccu_depth = 256 * 1024;
	return c;
}

static unsigned
layout_from_top(const struct adrenogpu_chip *chip, unsigned offset, struct adrenogpu_gmem_config *c)
{
	unsigned n = chip->num_ccu;
	c->vpc_bv_pos_offset = offset - n * c->vpc_bv_pos_size;
	offset = c->vpc_bv_pos_offset;
	c->vpc_attr_offset = offset - n * c->vpc_attr_size;
	offset = c->vpc_attr_offset;
	c->vpc_pos_offset = offset - n * c->vpc_pos_size;
	offset = c->vpc_pos_offset;
	c->color_ccu_offset = offset - n * c->color_cache_size;
	offset = c->color_ccu_offset;
	c->depth_ccu_offset = offset - n * c->depth_cache_size;
	return c->depth_ccu_offset;
}

unsigned
adrenogpu_calc_gmem_layout(const struct adrenogpu_chip *chip, unsigned gmem_bytes,
    struct adrenogpu_gmem_config *gmem, struct adrenogpu_gmem_config *sysmem)
{
	memset(gmem, 0, sizeof *gmem);
	memset(sysmem, 0, sizeof *sysmem);
	gmem->depth_fraction = chip->gmem_ccu_depth_fraction;   gmem->depth_cache_size = chip->gmem_per_ccu_depth;
	gmem->color_fraction = chip->gmem_ccu_color_fraction;   gmem->color_cache_size = chip->gmem_per_ccu_color;
	gmem->vpc_attr_size = chip->gmem_vpc_attr; gmem->vpc_pos_size = chip->gmem_vpc_pos; gmem->vpc_bv_pos_size = chip->gmem_vpc_bv_pos;
	sysmem->depth_fraction = chip->sysmem_ccu_depth_fraction; sysmem->depth_cache_size = chip->sysmem_per_ccu_depth;
	sysmem->color_fraction = chip->sysmem_ccu_color_fraction; sysmem->color_cache_size = chip->sysmem_per_ccu_color;
	sysmem->vpc_attr_size = chip->sysmem_vpc_attr; sysmem->vpc_pos_size = chip->sysmem_vpc_pos; sysmem->vpc_bv_pos_size = chip->sysmem_vpc_bv_pos;
	(void)layout_from_top(chip, gmem_bytes, sysmem);
	return layout_from_top(chip, gmem_bytes, gmem);
}

/* ---- sequences ---- */
/* fd6_emit_gmem_cache_cntl for the sysmem configuration. */
static void
emit_gmem_cache_cntl(struct adrenogpu_cs *cs, const struct adrenogpu_gmem_config *c)
{
	struct adrenogpu_regs r = { 0 };
	R(&r, RB_CCU_CACHE_CNTL, 0, F(RB_CCU_CACHE_CNTL, DEPTH_CACHE_SIZE, c->depth_fraction) |
	    F(RB_CCU_CACHE_CNTL, DEPTH_OFFSET, c->depth_ccu_offset) |
	    F(RB_CCU_CACHE_CNTL, COLOR_CACHE_SIZE, c->color_fraction) |
	    F(RB_CCU_CACHE_CNTL, COLOR_OFFSET, c->color_ccu_offset));
	R(&r, VPC_ATTR_BUF_GMEM_SIZE, 0, F(VPC_ATTR_BUF_GMEM_SIZE, VALUE, c->vpc_attr_size));
	R(&r, VPC_ATTR_BUF_GMEM_BASE, 0, F(VPC_ATTR_BUF_GMEM_BASE, VALUE, c->vpc_attr_offset));
	R(&r, PC_ATTR_BUF_GMEM_SIZE, 0, F(PC_ATTR_BUF_GMEM_SIZE, VALUE, c->vpc_attr_size));
	R(&r, VPC_POS_BUF_GMEM_SIZE, 0, F(VPC_POS_BUF_GMEM_SIZE, VALUE, c->vpc_pos_size));
	R(&r, VPC_POS_BUF_GMEM_BASE, 0, F(VPC_POS_BUF_GMEM_BASE, VALUE, c->vpc_pos_offset));
	R(&r, PC_POS_BUF_GMEM_SIZE, 0, F(PC_POS_BUF_GMEM_SIZE, VALUE, c->vpc_pos_size));
	R(&r, VPC_BV_POS_BUF_GMEM_BASE, 0, F(VPC_BV_POS_BUF_GMEM_BASE, VALUE, c->vpc_bv_pos_offset));
	R(&r, VPC_BV_POS_BUF_GMEM_SIZE, 0, F(VPC_BV_POS_BUF_GMEM_SIZE, VALUE, c->vpc_bv_pos_size));
	R(&r, PC_BV_POS_BUF_GMEM_SIZE, 0, F(PC_BV_POS_BUF_GMEM_SIZE, VALUE, c->vpc_bv_pos_size));
	adrenogpu_cs_crb(cs, &r);
}

/* fd6_lrz_inv */
static void
emit_lrz_inv(struct adrenogpu_cs *cs)
{
	struct adrenogpu_regs r = { 0 };
	R(&r, GRAS_LRZ_CNTL, 0, F(GRAS_LRZ_CNTL, ENABLE, 1));
	R(&r, GRAS_LRZ_CNTL2, 0, F(GRAS_LRZ_CNTL2, DISABLE_ON_WRONG_DIR, 1) | F(GRAS_LRZ_CNTL2, FC_ENABLE, 1));
	R(&r, RB_LRZ_CNTL2, 0, 0);
	adrenogpu_cs_crb(cs, &r);
	adrenogpu_cs_event(cs, A8XX_E_LRZ_CACHE_FLUSH);
	memset(&r, 0, sizeof r);
	R(&r, GRAS_LRZ_CNTL, 0, 0);
	R(&r, GRAS_LRZ_CNTL2, 0, 0);
	R(&r, RB_LRZ_CNTL2, 0, 0);
	adrenogpu_cs_crb(cs, &r);
}

void
adrenogpu_pm4_emit_restore(struct adrenogpu_cs *cs, const struct adrenogpu_gmem_config *sysmem, uint64_t border_va)
{
	struct adrenogpu_regs r;
	PKT7(cs, A8XX_E_CP_SET_MODE, 0);
	PKT7(cs, A8XX_E_CP_THREAD_CONTROL, A8XX_PKT_CP_THREAD_CONTROL_0__THREAD(A8XX_E_CP_SET_THREAD_BR) |
	    A8XX_PKT_CP_THREAD_CONTROL_0__CONCURRENT_BIN_DISABLE(1));
	emit_lrz_inv(cs);
	adrenogpu_cs_event(cs, A8XX_E_CCU_INVALIDATE_COLOR);
	adrenogpu_cs_event(cs, A8XX_E_CCU_INVALIDATE_DEPTH);
	adrenogpu_cs_pkt7(cs, A8XX_E_CP_CCHE_INVALIDATE, NULL, 0);
	adrenogpu_cs_event(cs, A8XX_E_CACHE_INVALIDATE7);
	adrenogpu_cs_wfi(cs);
	memset(&r, 0, sizeof r);
	R(&r, SP_UPDATE_CNTL, 0, F(SP_UPDATE_CNTL, VS_STATE, 1) | F(SP_UPDATE_CNTL, HS_STATE, 1) |
	    F(SP_UPDATE_CNTL, DS_STATE, 1) | F(SP_UPDATE_CNTL, GS_STATE, 1) | F(SP_UPDATE_CNTL, FS_STATE, 1) |
	    F(SP_UPDATE_CNTL, CS_STATE, 1));
	adrenogpu_cs_pkt4(cs, &r);
	adrenogpu_cs_wfi(cs);
	/* fd6_emit_static_non_context_regs */
	memset(&r, 0, sizeof r);
	for (unsigned i = 0; i < 6; i++) R(&r, GRAS_BIN_FOVEAT_XY_FDM_OFFSET, i, 0);
	R(&r, RB_UNKNOWN_8818, 0, 0);
	R(&r, RB_UNKNOWN_8819, 0, 0);
	R(&r, RB_UNKNOWN_881A, 0, 0);
	R(&r, RB_UNKNOWN_881B, 0, 0);
	R(&r, RB_UNKNOWN_881C, 0, 0);
	R(&r, RB_UNKNOWN_881D, 0, 0);
	R(&r, RB_UNKNOWN_881E, 0, 0);
	R(&r, RB_LRZ_CNTL2, 0, 0);
	R(&r, RB_RESOLVE_CNTL_5, 0, 1);
	R(&r, SP_UNKNOWN_AB01, 0, 0);
	R(&r, SP_HLSQ_MODE_CNTL, 0, 0);
	R(&r, SP_UNKNOWN_AB23, 0, 0);
	R(&r, TPL1_PS_ROTATION_CNTL, 0, 4);
	R(&r, TPL1_PS_SWIZZLE_CNTL, 0, 0);
	R(&r, PC_UNKNOWN_980B, 0, 0x00800280);
	R(&r, PC_MODE_CNTL, 0, 0x00003F00);
	R(&r, SP_PERFCTR_SHADER_MASK, 0, F(SP_PERFCTR_SHADER_MASK, VS, 1) | F(SP_PERFCTR_SHADER_MASK, HS, 1) |
	    F(SP_PERFCTR_SHADER_MASK, DS, 1) | F(SP_PERFCTR_SHADER_MASK, GS, 1) | F(SP_PERFCTR_SHADER_MASK, FS, 1) |
	    F(SP_PERFCTR_SHADER_MASK, CS, 1));
	R(&r, GRAS_SC_SCREEN_SCISSOR_CNTL, 0, 0);
	R(&r, GRAS_BIN_FOVEAT, 0, 0);
	R(&r, RB_BIN_FOVEAT, 0, 0);
	R(&r, RB_A2D_DEST_BUFFER_ARRAY_PITCH, 0, 0);
	adrenogpu_cs_ncrb(cs, &r);
	/* fd6_emit_static_context_regs */
	memset(&r, 0, sizeof r);
	R(&r, SP_GFX_USIZE, 0, 0);
	R(&r, TPL1_PS_ROTATION_CNTL, 0, 0);
	R(&r, SP_UNKNOWN_A9A8, 0, 0);
	R(&r, VFD_MODE_CNTL, 0, F(VFD_MODE_CNTL, VERTEX, 1) | F(VFD_MODE_CNTL, INSTANCE, 1));
	R(&r, RB_MODE_CNTL, 0, 0x10);
	R(&r, GRAS_LRZ_PS_INPUT_CNTL, 0, 0);
	R(&r, GRAS_LRZ_PS_SAMPLEFREQ_CNTL, 0, 0);
	R(&r, GRAS_MODE_CNTL, 0, 0x2);
	R(&r, RB_UNKNOWN_8818, 0, 0);
	R(&r, VPC_REPLACE_MODE_CNTL, 0, 0);
	R(&r, VPC_ROTATION_CNTL, 0, 0);
	R(&r, VPC_SO_OVERRIDE, 0, F(VPC_SO_OVERRIDE, DISABLE, 1));
	R(&r, VPC_RAST_STREAM_CNTL, 0, 0);
	R(&r, PC_STEREO_RENDERING_CNTL, 0, 0);
	R(&r, TPL1_PS_SWIZZLE_CNTL, 0, 0);
	R(&r, GRAS_SU_CONSERVATIVE_RAS_CNTL, 0, 0);
	R(&r, GRAS_SU_VS_SIV_CNTL, 0, 0);
	R(&r, GRAS_SC_CNTL, 0, 0);
	R(&r, SP_REG_PROG_ID_3, 0, F(SP_REG_PROG_ID_3, LINELENGTHREGID, 0xFC) | F(SP_REG_PROG_ID_3, FOVEATIONQUALITYREGID, 0xFC));
	R(&r, VFD_RENDER_MODE, 0, F(VFD_RENDER_MODE, RENDER_MODE, A8XX_E_RENDERING_PASS));
	R(&r, VFD_STEREO_RENDERING_CNTL, 0, 0);
	R(&r, VPC_SO_CNTL, 0, 0);
	R(&r, GRAS_LRZ_CNTL, 0, 0);
	R(&r, GRAS_LRZ_CNTL2, 0, 0);
	R(&r, RB_LRZ_CNTL, 0, 0);
	R(&r, RB_DEPTH_PLANE_CNTL, 0, 0);
	R(&r, GRAS_SU_DEPTH_PLANE_CNTL, 0, 0);
	for (unsigned i = 0; i < 32; i++) R(&r, VFD_VERTEX_BUFFER_SIZE, i, F(VFD_VERTEX_BUFFER_SIZE, VALUE, 0));
	R64(&r, TPL1_GFX_BORDER_COLOR_BASE, 0, border_va);
	R64(&r, TPL1_CS_BORDER_COLOR_BASE, 0, border_va);
	R(&r, PC_DGEN_SU_CONSERVATIVE_RAS_CNTL, 0, 0);
	R(&r, VPC_UNKNOWN_CNTL, 0, 0);
	R(&r, PC_HS_BUFFER_SIZE, 0, 0x40000);
	R(&r, PC_TF_BUFFER_SIZE, 0, 0x4040);
	R(&r, GRAS_LRZ_QUALITY_LOOKUP_TABLE_REG, 0, 0x09510840);
	R(&r, GRAS_LRZ_QUALITY_LOOKUP_TABLE_REG, 1, 0x00000A62);
	R(&r, SP_PS_CNTL_0, 0, 0);
	adrenogpu_cs_crb(cs, &r);
	PKT7(cs, A8XX_E_CP_SET_DRAW_STATE, A8XX_PKT_CP_SET_DRAW_STATE__0__DISABLE_ALL_GROUPS(1), 0, 0);
	emit_gmem_cache_cntl(cs, sysmem);
}

/* ---- render pass ---- */
static void
emit_static_binning_regs(struct adrenogpu_cs *cs)
{
	struct adrenogpu_regs r = { 0 };
	R(&r, RB_BUFFER_CNTL, 0, F(RB_BUFFER_CNTL, Z_SYSMEM, 1) | F(RB_BUFFER_CNTL, S_SYSMEM, 1) |
	    F(RB_BUFFER_CNTL, RT0_SYSMEM, 1) | F(RB_BUFFER_CNTL, RT1_SYSMEM, 1) | F(RB_BUFFER_CNTL, RT2_SYSMEM, 1) |
	    F(RB_BUFFER_CNTL, RT3_SYSMEM, 1) | F(RB_BUFFER_CNTL, RT4_SYSMEM, 1) | F(RB_BUFFER_CNTL, RT5_SYSMEM, 1) |
	    F(RB_BUFFER_CNTL, RT6_SYSMEM, 1) | F(RB_BUFFER_CNTL, RT7_SYSMEM, 1));
	R(&r, GRAS_LRZ_CB_CNTL, 0, 0);
	R(&r, GRAS_MODE_CNTL, 0, 0x2);
	R(&r, RB_CLEAR_TARGET, 0, F(RB_CLEAR_TARGET, CLEAR_MODE, A8XX_E_CLEAR_MODE_SYSMEM));
	adrenogpu_cs_ncrb(cs, &r);
}

static void
emit_lrz_off(struct adrenogpu_cs *cs)
{
	struct adrenogpu_regs r = { 0 };
	R64(&r, GRAS_LRZ_BUFFER_BASE, 0, 0);
	R(&r, GRAS_LRZ_BUFFER_PITCH, 0, 0);
	R(&r, GRAS_LRZ_VIEW_INFO, 0, 0);
	R64(&r, GRAS_LRZ_FAST_CLEAR_BUFFER_BASE, 0, 0);
	R(&r, GRAS_LRZ_DEPTH_BUFFER_INFO, 0, 0);
	R(&r, GRAS_LRZ_CNTL2, 0, 0);
	R(&r, GRAS_LRZ_BUFFER_SLICE_PITCH, 0, 0);
	adrenogpu_cs_crb(cs, &r);
}

static void
emit_marker(struct adrenogpu_cs *cs, unsigned mode)
{
	PKT7(cs, A8XX_E_CP_SET_MARKER, A8XX_PKT_A8XX_CP_SET_MARKER_0__MODE(mode));
}

static void emit_pass_clear(struct adrenogpu_cs *cs, const struct adrenogpu_pass *p);

void
adrenogpu_pm4_emit_pass_begin(struct adrenogpu_cs *cs, const struct adrenogpu_pass *p,
    const struct adrenogpu_gmem_config *sysmem)
{
	struct adrenogpu_regs r;
	const unsigned W = p->width, H = p->height;
	if (!W || !H || W > 16384 || H > 16384) {
		cs->err = 1;
		return;
	}
	adrenogpu_pm4_emit_restore(cs, sysmem, p->border_color_va);
	/* fd6_emit_sysmem_prep */
	adrenogpu_cs_event(cs, A8XX_E_LRZ_CACHE_FLUSH);
	emit_marker(cs, A8XX_E_RM6_DIRECT_RENDER);
	memset(&r, 0, sizeof r);
	R(&r, GRAS_SC_WINDOW_SCISSOR_TL, 0, F(GRAS_SC_WINDOW_SCISSOR_TL, X, 0) | F(GRAS_SC_WINDOW_SCISSOR_TL, Y, 0));
	R(&r, GRAS_SC_WINDOW_SCISSOR_BR, 0, F(GRAS_SC_WINDOW_SCISSOR_BR, X, W - 1) | F(GRAS_SC_WINDOW_SCISSOR_BR, Y, H - 1));
	adrenogpu_cs_pkt4(cs, &r);
	memset(&r, 0, sizeof r);
	R(&r, GRAS_A2D_SCISSOR_TL, 0, F(GRAS_A2D_SCISSOR_TL, X, 0) | F(GRAS_A2D_SCISSOR_TL, Y, 0));
	R(&r, GRAS_A2D_SCISSOR_BR, 0, F(GRAS_A2D_SCISSOR_BR, X, W - 1) | F(GRAS_A2D_SCISSOR_BR, Y, H - 1));
	adrenogpu_cs_pkt4(cs, &r);
	memset(&r, 0, sizeof r);
	R(&r, RB_RESOLVE_CNTL_1, 0, F(RB_RESOLVE_CNTL_1, X, 0) | F(RB_RESOLVE_CNTL_1, Y, 0));
	R(&r, RB_RESOLVE_CNTL_2, 0, F(RB_RESOLVE_CNTL_2, X, W - 1) | F(RB_RESOLVE_CNTL_2, Y, H - 1));
	adrenogpu_cs_pkt4(cs, &r);
	memset(&r, 0, sizeof r);
	R(&r, GRAS_MODE_CNTL, 0, 0x2);
	adrenogpu_cs_pkt4(cs, &r);
	memset(&r, 0, sizeof r);
	R(&r, RB_WINDOW_OFFSET, 0, F(RB_WINDOW_OFFSET, X, 0) | F(RB_WINDOW_OFFSET, Y, 0));
	R(&r, RB_RESOLVE_WINDOW_OFFSET, 0, F(RB_RESOLVE_WINDOW_OFFSET, X, 0) | F(RB_RESOLVE_WINDOW_OFFSET, Y, 0));
	R(&r, SP_WINDOW_OFFSET, 0, F(SP_WINDOW_OFFSET, X, 0) | F(SP_WINDOW_OFFSET, Y, 0));
	R(&r, TPL1_WINDOW_OFFSET, 0, F(TPL1_WINDOW_OFFSET, X, 0) | F(TPL1_WINDOW_OFFSET, Y, 0));
	R(&r, TPL1_A2D_WINDOW_OFFSET, 0, F(TPL1_A2D_WINDOW_OFFSET, X, 0) | F(TPL1_A2D_WINDOW_OFFSET, Y, 0));
	R(&r, GRAS_SC_BIN_CNTL, 0, F(GRAS_SC_BIN_CNTL, BINW, 0) | F(GRAS_SC_BIN_CNTL, BINH, 0) |
	    F(GRAS_SC_BIN_CNTL, FORCE_BI_DIR_LRZ_DISABLE, 1) | F(GRAS_SC_BIN_CNTL, RENDER_MODE, A8XX_E_RENDERING_PASS) |
	    F(GRAS_SC_BIN_CNTL, LRZ_FEEDBACK_ZMODE_MASK, A8XX_E_LRZ_FEEDBACK_EARLY_Z_LATE_Z));
	R(&r, RB_CNTL, 0, F(RB_CNTL, BINW, 0) | F(RB_CNTL, BINH, 0) | F(RB_CNTL, RENDER_MODE, A8XX_E_RENDERING_PASS) |
	    F(RB_CNTL, LRZ_FEEDBACK_ZMODE_MASK, A8XX_E_LRZ_FEEDBACK_EARLY_Z_LATE_Z));
	R(&r, VFD_RENDER_MODE, 0, F(VFD_RENDER_MODE, RENDER_MODE, A8XX_E_RENDERING_PASS));
	R(&r, TPL1_BIN_SIZE, 0, F(TPL1_BIN_SIZE, BINW, 0) | F(TPL1_BIN_SIZE, BINH, 0));
	R(&r, TPL1_A2D_BIN_SIZE, 0, F(TPL1_A2D_BIN_SIZE, BINW, 0) | F(TPL1_A2D_BIN_SIZE, BINH, 0));
	R(&r, SP_BIN_SIZE, 0, F(SP_BIN_SIZE, BINW, 0) | F(SP_BIN_SIZE, BINH, 0));
	for (unsigned i = 0; i < 8; i++)
		R(&r, RB_MRT_GMEM_DIMENSION_REG, i, F(RB_MRT_GMEM_DIMENSION_REG, WIDTH, 0) | F(RB_MRT_GMEM_DIMENSION_REG, HEIGHT, 0));
	R(&r, RB_DEPTH_GMEM_DIMENSION, 0, F(RB_DEPTH_GMEM_DIMENSION, WIDTH, 0) | F(RB_DEPTH_GMEM_DIMENSION, HEIGHT, 0));
	R(&r, RB_STENCIL_GMEM_DIMENSION, 0, F(RB_STENCIL_GMEM_DIMENSION, WIDTH, 0) | F(RB_STENCIL_GMEM_DIMENSION, HEIGHT, 0));
	R(&r, RB_RESOLVE_CNTL_3, 0, F(RB_RESOLVE_CNTL_3, BINW, 0) | F(RB_RESOLVE_CNTL_3, BINH, 0));
	R(&r, RB_BUFFER_CNTL, 0, F(RB_BUFFER_CNTL, Z_SYSMEM, 1) | F(RB_BUFFER_CNTL, S_SYSMEM, 1) |
	    F(RB_BUFFER_CNTL, RT0_SYSMEM, 1) | F(RB_BUFFER_CNTL, RT1_SYSMEM, 1) | F(RB_BUFFER_CNTL, RT2_SYSMEM, 1) |
	    F(RB_BUFFER_CNTL, RT3_SYSMEM, 1) | F(RB_BUFFER_CNTL, RT4_SYSMEM, 1) | F(RB_BUFFER_CNTL, RT5_SYSMEM, 1) |
	    F(RB_BUFFER_CNTL, RT6_SYSMEM, 1) | F(RB_BUFFER_CNTL, RT7_SYSMEM, 1));
	R(&r, GRAS_LRZ_CB_CNTL, 0, 0);
	R(&r, VPC_SO_OVERRIDE, 0, F(VPC_SO_OVERRIDE, DISABLE, 0));
	adrenogpu_cs_crb(cs, &r);
	emit_marker(cs, A8XX_E_RM6_DIRECT_RENDER);
	PKT7(cs, A8XX_E_CP_SKIP_IB2_ENABLE_GLOBAL, 0);
	PKT7(cs, A8XX_E_CP_SKIP_IB2_ENABLE_LOCAL, 1);
	PKT7(cs, A8XX_E_CP_SET_VISIBILITY_OVERRIDE, 1);
	/* emit_zs (none), emit_mrt, emit_msaa */
	memset(&r, 0, sizeof r);
	R(&r, RB_DEPTH_BUFFER_INFO, 0, F(RB_DEPTH_BUFFER_INFO, DEPTH_FORMAT, A8XX_E_DEPTH6_NONE) |
	    F(RB_DEPTH_BUFFER_INFO, TILEMODE, A8XX_E_TILE6_LINEAR));
	R(&r, RB_DEPTH_BUFFER_PITCH, 0, F(RB_DEPTH_BUFFER_PITCH, VALUE, 0));
	R(&r, RB_DEPTH_BUFFER_ARRAY_PITCH, 0, F(RB_DEPTH_BUFFER_ARRAY_PITCH, VALUE, 0));
	R64(&r, RB_DEPTH_BUFFER_BASE, 0, 0);
	R(&r, RB_DEPTH_GMEM_BASE, 0, 0);
	R(&r, GRAS_SU_DEPTH_BUFFER_INFO, 0, F(GRAS_SU_DEPTH_BUFFER_INFO, DEPTH_FORMAT, A8XX_E_DEPTH6_NONE));
	R(&r, RB_STENCIL_BUFFER_INFO, 0, F(RB_STENCIL_BUFFER_INFO, TILEMODE, A8XX_E_TILE6_LINEAR));
	R(&r, RB_MRT_BUF_INFO, 0, F(RB_MRT_BUF_INFO, COLOR_FORMAT, p->color.rb_format) |
	    F(RB_MRT_BUF_INFO, COLOR_TILE_MODE, p->color.tile_mode) | F(RB_MRT_BUF_INFO, COLOR_SWAP, p->color.swap));
	R(&r, RB_MRT_PITCH, 0, F(RB_MRT_PITCH, VALUE, p->color.pitch));
	R(&r, RB_MRT_ARRAY_PITCH, 0, F(RB_MRT_ARRAY_PITCH, VALUE, p->color.layer_bytes));
	R64(&r, RB_MRT_BASE, 0, p->color.va);
	R(&r, RB_MRT_BASE_GMEM, 0, 0);
	R(&r, SP_PS_MRT_REG, 0, F(SP_PS_MRT_REG, COLOR_FORMAT, p->color.rb_format));
	R64(&r, RB_COLOR_FLAG_BUFFER_ADDR, 0, p->color.va);
	R(&r, RB_COLOR_FLAG_BUFFER_PITCH, 0, F(RB_COLOR_FLAG_BUFFER_PITCH, PITCH, 0) | F(RB_COLOR_FLAG_BUFFER_PITCH, ARRAY_PITCH, 0));
	R(&r, GRAS_LRZ_MRT_BUFFER_INFO_0, 0, F(GRAS_LRZ_MRT_BUFFER_INFO_0, COLOR_FORMAT, p->color.rb_format));
	R(&r, RB_SRGB_CNTL, 0, F(RB_SRGB_CNTL, SRGB_MRT0, p->color.srgb));
	R(&r, SP_SRGB_CNTL, 0, F(SP_SRGB_CNTL, SRGB_MRT0, p->color.srgb));
	R(&r, GRAS_CL_ARRAY_SIZE, 0, F(GRAS_CL_ARRAY_SIZE, VALUE, 0));
	R(&r, TPL1_RAS_MSAA_CNTL, 0, F(TPL1_RAS_MSAA_CNTL, SAMPLES, A8XX_E_MSAA_ONE));
	R(&r, TPL1_DEST_MSAA_CNTL, 0, F(TPL1_DEST_MSAA_CNTL, SAMPLES, A8XX_E_MSAA_ONE) | F(TPL1_DEST_MSAA_CNTL, MSAA_DISABLE, 1));
	R(&r, GRAS_SC_RAS_MSAA_CNTL, 0, F(GRAS_SC_RAS_MSAA_CNTL, SAMPLES, A8XX_E_MSAA_ONE));
	R(&r, GRAS_SC_DEST_MSAA_CNTL, 0, F(GRAS_SC_DEST_MSAA_CNTL, SAMPLES, A8XX_E_MSAA_ONE) | F(GRAS_SC_DEST_MSAA_CNTL, MSAA_DISABLE, 1));
	R(&r, RB_RAS_MSAA_CNTL, 0, F(RB_RAS_MSAA_CNTL, SAMPLES, A8XX_E_MSAA_ONE));
	R(&r, RB_DEST_MSAA_CNTL, 0, F(RB_DEST_MSAA_CNTL, SAMPLES, A8XX_E_MSAA_ONE) | F(RB_DEST_MSAA_CNTL, MSAA_DISABLE, 1));
	R(&r, RB_RESOLVE_GMEM_BUFFER_INFO, 0, F(RB_RESOLVE_GMEM_BUFFER_INFO, SAMPLES, A8XX_E_MSAA_ONE));
	adrenogpu_cs_crb(cs, &r);
	/* fd6_emit_sysmem */
	emit_gmem_cache_cntl(cs, sysmem);
	emit_static_binning_regs(cs);
	memset(&r, 0, sizeof r);
	R(&r, RB_RENDER_CNTL, 0, F(RB_RENDER_CNTL, RASTER_MODE, A8XX_E_TYPE_TILED) | F(RB_RENDER_CNTL, RASTER_DIRECTION, A8XX_E_LR_TB));
	R(&r, GRAS_SU_RENDER_CNTL, 0, 0);
	adrenogpu_cs_crb(cs, &r);
	emit_lrz_off(cs);
	emit_pass_clear(cs, p);
}

/* ---- load-action clear ---- */
/* Registers the generated A8XX header does not carry (its generator keeps the A8XX-variant view of a6xx.xml and
 * drops these): offsets and layouts are from Mesa a6xx.xml at the pinned commit, and the sequences below are
 * checked against Turnip's A810 stream. */
#define REG_RB_RESOLVE_CNTL_0 0x88d0u
#define REG_RB_RESOLVE_GMEM_BUFFER_BASE 0x88d6u
#define REG_RB_RESOLVE_SYSTEM_BUFFER_INFO 0x88d7u /* TILE_MODE 0-1, FLAGS 2, SAMPLES 3-4, SWAP 5-6, FORMAT 7-14 */
#define REG_RB_RESOLVE_SYSTEM_FLAG_BUFFER_BASE 0x88dcu
#define REG_RB_RESOLVE_CLEAR_COLOR_DW0 0x88dfu
#define REG_RB_RESOLVE_OPERATION 0x88e3u         /* TYPE 0-1, SAMPLE_0 2, DEPTH 3, CLEAR_MASK 4-7, LAST 8-9, BUFFER_ID 12-15 */
#define REG_RB_A2D_DEST_FLAG_BUFFER_BASE 0x8c20u
#define BLIT_EVENT_CLEAR 2u
#define COND_EXEC_RENDER_MODE_GMEM_SYSMEM 0x3c000000u /* CP_COND_REG_EXEC_0: MODE RENDER_MODE (3<<28), GMEM, SYSMEM */

/* Round to nearest even of x * 255 for x clamped to [0, 1]. */
static uint32_t
unorm8(float x)
{
	if (!(x > 0.0f)) return 0;
	if (x >= 1.0f) return 255;
	float v = x * 255.0f;
	uint32_t i = (uint32_t)v;
	float frac = v - (float)i;
	if (frac > 0.5f || (frac == 0.5f && (i & 1))) i++;
	return i;
}

void
adrenogpu_pack_clear_unorm8(const float rgba[4], uint32_t *packed, uint32_t words[4])
{
	uint32_t b[4];
	for (unsigned i = 0; i < 4; i++) b[i] = unorm8(rgba[i]);
	if (packed) *packed = b[0] | b[1] << 8 | b[2] << 16 | b[3] << 24;
	if (words) for (unsigned i = 0; i < 4; i++) words[i] = b[i];
}

/* tu7_generic_clear_attachment inside a CP_COND_REG_EXEC (GMEM or SYSMEM): blit scissor, clear value, the resolve
 * engine's buffer description and operation, then CCU_RESOLVE, and after the block CCU_END_RESOLVE_GROUP. */
static void
emit_clear_generic(struct adrenogpu_cs *cs, const struct adrenogpu_pass *p, uint32_t packed)
{
	uint32_t body[32];
	struct adrenogpu_cs sub;
	struct adrenogpu_regs r;
	const struct adrenogpu_color_target *c = &p->color;
	adrenogpu_cs_init(&sub, body, sizeof body / sizeof *body);
	/* tu6_emit_blit_scissor */
	memset(&r, 0, sizeof r);
	R(&r, RB_RESOLVE_CNTL_1, 0, F(RB_RESOLVE_CNTL_1, X, 0) | F(RB_RESOLVE_CNTL_1, Y, 0));
	R(&r, RB_RESOLVE_CNTL_2, 0, F(RB_RESOLVE_CNTL_2, X, p->width - 1) | F(RB_RESOLVE_CNTL_2, Y, p->height - 1));
	adrenogpu_cs_pkt4(&sub, &r);
	memset(&r, 0, sizeof r);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_CLEAR_COLOR_DW0, packed);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_CLEAR_COLOR_DW0 + 1, 0);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_CLEAR_COLOR_DW0 + 2, 0);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_CLEAR_COLOR_DW0 + 3, 0);
	adrenogpu_cs_pkt4(&sub, &r);
	/* event_blit_setup */
	memset(&r, 0, sizeof r);
	R(&r, RB_RESOLVE_GMEM_BUFFER_INFO, 0, F(RB_RESOLVE_GMEM_BUFFER_INFO, SAMPLES, A8XX_E_MSAA_ONE));
	adrenogpu_cs_pkt4(&sub, &r);
	memset(&r, 0, sizeof r);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_CNTL_0, 0);
	adrenogpu_cs_pkt4(&sub, &r);
	memset(&r, 0, sizeof r);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_OPERATION, BLIT_EVENT_CLEAR | 0xfu << 4); /* buffer id 0, mask 0xf */
	adrenogpu_cs_pkt4(&sub, &r);
	/* event_blit_run: system buffer (info, base, pitch>>6), flag buffer (base, pitch 0), GMEM base 0 */
	memset(&r, 0, sizeof r);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_SYSTEM_BUFFER_INFO, c->tile_mode | c->swap << 5 | c->rb_format << 7);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_SYSTEM_BUFFER_INFO + 1, (uint32_t)c->va);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_SYSTEM_BUFFER_INFO + 2, (uint32_t)(c->va >> 32));
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_SYSTEM_BUFFER_INFO + 3, (c->pitch >> 6) & 0xffffu);
	adrenogpu_cs_pkt4(&sub, &r);
	memset(&r, 0, sizeof r);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_SYSTEM_FLAG_BUFFER_BASE, (uint32_t)c->va);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_SYSTEM_FLAG_BUFFER_BASE + 1, (uint32_t)(c->va >> 32));
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_SYSTEM_FLAG_BUFFER_BASE + 2, 0);
	adrenogpu_cs_pkt4(&sub, &r);
	memset(&r, 0, sizeof r);
	adrenogpu_regs_add(&r, REG_RB_RESOLVE_GMEM_BUFFER_BASE, 0);
	adrenogpu_cs_pkt4(&sub, &r);
	adrenogpu_cs_event(&sub, A8XX_E_CCU_RESOLVE);
	if (sub.err) {
		cs->err = 1;
		return;
	}
	PKT7(cs, A8XX_E_CP_COND_REG_EXEC, COND_EXEC_RENDER_MODE_GMEM_SYSMEM, (uint32_t)sub.n);
	for (size_t i = 0; i < sub.n; i++) put(cs, body[i]);
	/* closing the resolve group is outside the conditional block (tu_emit_resolve_group) */
	adrenogpu_cs_event(cs, A8XX_E_CCU_END_RESOLVE_GROUP);
}

void
adrenogpu_pm4_emit_clear_2d(struct adrenogpu_cs *cs, const struct adrenogpu_clear_2d *c)
{
	struct adrenogpu_regs r;
	const struct adrenogpu_blit_dest *d = &c->dest;
	if (!c->w || !c->h || c->x + c->w > 16384 || c->y + c->h > 16384) {
		cs->err = 1;
		return;
	}
	/* r2d_setup_common (no sRGB, no UBWC, no rotation, no scissor) */
	memset(&r, 0, sizeof r);
	R(&r, RB_A2D_PIXEL_CNTL, 0, F(RB_A2D_PIXEL_CNTL, PIXEL_OP, A8XX_E_PIXEL_OP_DISABLED));
	adrenogpu_cs_pkt4(cs, &r);
	memset(&r, 0, sizeof r);
	R(&r, RB_A2D_BLT_CNTL, 0, F(RB_A2D_BLT_CNTL, ROTATE, A8XX_E_ROTATE_0) | F(RB_A2D_BLT_CNTL, SOLID_COLOR, 1) |
	    F(RB_A2D_BLT_CNTL, COLOR_FORMAT, d->rb_format) | F(RB_A2D_BLT_CNTL, MASK, 0xf) | F(RB_A2D_BLT_CNTL, IFMT, c->ifmt));
	adrenogpu_cs_pkt4(cs, &r);
	memset(&r, 0, sizeof r);
	R(&r, GRAS_A2D_BLT_CNTL, 0, F(GRAS_A2D_BLT_CNTL, ROTATE, A8XX_E_ROTATE_0) | F(GRAS_A2D_BLT_CNTL, SOLID_COLOR, 1) |
	    F(GRAS_A2D_BLT_CNTL, COLOR_FORMAT, d->rb_format) | F(GRAS_A2D_BLT_CNTL, MASK, 0xf) | F(GRAS_A2D_BLT_CNTL, IFMT, c->ifmt));
	adrenogpu_cs_pkt4(cs, &r);
	memset(&r, 0, sizeof r);
	R(&r, TPL1_A2D_BLT_CNTL, 0, F(TPL1_A2D_BLT_CNTL, TYPE, A8XX_E_A6XX_TEX_2D));
	adrenogpu_cs_pkt4(cs, &r);
	memset(&r, 0, sizeof r);
	R(&r, SP_A2D_OUTPUT_INFO, 0, F(SP_A2D_OUTPUT_INFO, IFMT_TYPE, c->output_ifmt) |
	    F(SP_A2D_OUTPUT_INFO, COLOR_FORMAT, d->rb_format) | F(SP_A2D_OUTPUT_INFO, MASK, 0xf));
	adrenogpu_cs_pkt4(cs, &r);
	/* r2d_clear_value */
	memset(&r, 0, sizeof r);
	R(&r, RB_A2D_CLEAR_COLOR_DW0, 0, c->words[0]);
	R(&r, RB_A2D_CLEAR_COLOR_DW1, 0, c->words[1]);
	R(&r, RB_A2D_CLEAR_COLOR_DW2, 0, c->words[2]);
	R(&r, RB_A2D_CLEAR_COLOR_DW3, 0, c->words[3]);
	adrenogpu_cs_pkt4(cs, &r);
	/* r2d_dst / r2d_dst_buffer: info, base, pitch as consecutive registers; images add the flag buffer base */
	memset(&r, 0, sizeof r);
	R(&r, RB_A2D_DEST_BUFFER_INFO, 0, F(RB_A2D_DEST_BUFFER_INFO, COLOR_FORMAT, d->rb_format) |
	    F(RB_A2D_DEST_BUFFER_INFO, TILE_MODE, d->tile_mode) | F(RB_A2D_DEST_BUFFER_INFO, COLOR_SWAP, d->swap) |
	    F(RB_A2D_DEST_BUFFER_INFO, SAMPLES, A8XX_E_MSAA_ONE));
	R64(&r, RB_A2D_DEST_BUFFER_BASE, 0, d->va);
	R(&r, RB_A2D_DEST_BUFFER_PITCH, 0, F(RB_A2D_DEST_BUFFER_PITCH, VALUE, d->pitch));
	adrenogpu_cs_pkt4(cs, &r);
	if (d->is_image) {
		memset(&r, 0, sizeof r);
		adrenogpu_regs_add(&r, REG_RB_A2D_DEST_FLAG_BUFFER_BASE, (uint32_t)d->va);
		adrenogpu_regs_add(&r, REG_RB_A2D_DEST_FLAG_BUFFER_BASE + 1, (uint32_t)(d->va >> 32));
		adrenogpu_regs_add(&r, REG_RB_A2D_DEST_FLAG_BUFFER_BASE + 2, 0);
		adrenogpu_cs_pkt4(cs, &r);
	}
	/* r2d_coords (no source coordinates for a solid fill) */
	memset(&r, 0, sizeof r);
	R(&r, GRAS_A2D_DEST_TL, 0, F(GRAS_A2D_DEST_TL, X, c->x) | F(GRAS_A2D_DEST_TL, Y, c->y));
	R(&r, GRAS_A2D_DEST_BR, 0, F(GRAS_A2D_DEST_BR, X, c->x + c->w - 1) | F(GRAS_A2D_DEST_BR, Y, c->y + c->h - 1));
	adrenogpu_cs_pkt4(cs, &r);
	/* r2d_run */
	PKT7(cs, A8XX_E_CP_BLIT, A8XX_PKT_CP_BLIT_0__OP(A8XX_E_BLIT_OP_SCALE));
}

/* Snapintosh's emit_flushes (fd6_emit_flushes<A8XX>) for the colour half, used around the 2D clear. */
static void
emit_color_flushes(struct adrenogpu_cs *cs, int cche_and_wfi)
{
	adrenogpu_cs_event(cs, A8XX_E_CCU_CLEAN_COLOR);
	adrenogpu_cs_event(cs, A8XX_E_CCU_INVALIDATE_COLOR);
	adrenogpu_cs_event(cs, A8XX_E_DUMMY_EVENT);
	adrenogpu_cs_event(cs, A8XX_E_SUBPASS_FENCE);
	adrenogpu_cs_event(cs, A8XX_E_DUMMY_EVENT);
	if (cche_and_wfi) {
		adrenogpu_cs_wfi(cs);
		adrenogpu_cs_pkt7(cs, A8XX_E_CP_CCHE_INVALIDATE, NULL, 0);
		adrenogpu_cs_wfi(cs);
	}
}

static void
emit_pass_clear(struct adrenogpu_cs *cs, const struct adrenogpu_pass *p)
{
	uint32_t packed, words[4];
	if (p->clear_mode == ADRENOGPU_CLEAR_NONE) return;
	/* Only the 8-bit UNORM path is implemented (and, for the generic clear, verified): other formats and sRGB
	 * need their own value packing, which is not derived from a Turnip capture yet. */
	if (p->color.rb_format != A8XX_E_FMT6_8_8_8_8_UNORM || p->color.srgb) {
		cs->err = 1;
		return;
	}
	adrenogpu_pack_clear_unorm8(p->clear_rgba, &packed, words);
	if (p->clear_mode == ADRENOGPU_CLEAR_GENERIC) {
		emit_clear_generic(cs, p, packed);
	} else if (p->clear_mode == ADRENOGPU_CLEAR_2D) {
		struct adrenogpu_clear_2d c = { { p->color.va, p->color.pitch, p->color.rb_format, p->color.swap,
		    p->color.tile_mode, 1 }, A8XX_E_R2D_UNORM8, A8XX_E_OUTPUT_IFMT_2D_FLOAT, { 0 }, 0, 0, p->width, p->height };
		memcpy(c.words, words, sizeof words);
		/* The 2D engine writes through the CCU colour cache: drain and clean before, clean after, as the
		 * Snapintosh emitter brackets it. */
		emit_color_flushes(cs, 1);
		adrenogpu_pm4_emit_clear_2d(cs, &c);
		emit_color_flushes(cs, 0);
		emit_color_flushes(cs, 1);
	} else {
		cs->err = 1;
	}
}

void
adrenogpu_pm4_emit_draw_auto(struct adrenogpu_cs *cs, unsigned prim_type, unsigned instances, unsigned vertices)
{
	/* INDEX_SIZE is not meaningful without an index buffer; Turnip leaves bits 10-11 set (cntl 0xd84 for a
	 * triangle list), and so does this. */
	PKT7(cs, A8XX_E_CP_DRAW_INDX_OFFSET, A8XX_PKT_CP_DRAW_INDX_OFFSET_0__PRIM_TYPE(prim_type) |
	    A8XX_PKT_CP_DRAW_INDX_OFFSET_0__SOURCE_SELECT(A8XX_E_DI_SRC_SEL_AUTO_INDEX) |
	    A8XX_PKT_CP_DRAW_INDX_OFFSET_0__VIS_CULL(A8XX_E_USE_VISIBILITY) | (3u << 10), instances, vertices);
}

void
adrenogpu_pm4_emit_pass_end(struct adrenogpu_cs *cs)
{
	/* The draw must drain before the cleans: a CP_WAIT_FOR_IDLE first (the measured fix), then the
	 * fd6_emit_sysmem_fini / emit_common_fini flushes. */
	adrenogpu_cs_wfi(cs);
	adrenogpu_cs_event(cs, A8XX_E_CCU_CLEAN_COLOR);
	adrenogpu_cs_event(cs, A8XX_E_CCU_CLEAN_DEPTH);
	adrenogpu_cs_event(cs, A8XX_E_CCU_INVALIDATE_COLOR);
	adrenogpu_cs_event(cs, A8XX_E_CCU_INVALIDATE_DEPTH);
	adrenogpu_cs_event(cs, A8XX_E_CACHE_CLEAN);
	adrenogpu_cs_event(cs, A8XX_E_DUMMY_EVENT);
	adrenogpu_cs_event(cs, A8XX_E_SUBPASS_FENCE);
	adrenogpu_cs_event(cs, A8XX_E_DUMMY_EVENT);
	adrenogpu_cs_wfi(cs);
	adrenogpu_cs_pkt7(cs, A8XX_E_CP_CCHE_INVALIDATE, NULL, 0);
	adrenogpu_cs_wfi(cs);
	adrenogpu_cs_event(cs, A8XX_E_CACHE_CLEAN);
	PKT7(cs, A8XX_E_CP_SKIP_IB2_ENABLE_GLOBAL, 0);
	adrenogpu_cs_event(cs, A8XX_E_LRZ_CACHE_FLUSH);
}
