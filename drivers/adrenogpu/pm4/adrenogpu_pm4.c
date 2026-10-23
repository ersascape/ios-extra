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
