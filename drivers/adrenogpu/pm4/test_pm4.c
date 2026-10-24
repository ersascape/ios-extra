/* SPDX-License-Identifier: MIT */
/* Host test of the PM4 builder: layout arithmetic here, stream contents in tests/test_adrenogpu_pm4.py. */
#define _POSIX_C_SOURCE 200809L /* strtok_r under -std=c11 */
#include "adrenogpu_pm4.h"
#include "Fp6A8xxRegs.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* scene DUMP PARAMS: a whole pass (begin with the optional clear, program, one auto draw, end) described by a text file
 * of "name value..." lines, the way tests/test_adrenogpu_pm4.py reads it out of a Turnip capture. */
static unsigned long long
num(const char *s)
{
	return strtoull(s, NULL, 0);
}

static void
set_xs(struct adrenogpu_xs *x, const char *key, char **v)
{
	if (!strcmp(key, "base_va")) x->base_va = num(v[0]);
	else if (!strcmp(key, "instrlen")) x->instrlen = (uint32_t)num(v[0]);
	else if (!strcmp(key, "constlen")) x->constlen = (uint32_t)num(v[0]);
	else if (!strcmp(key, "half_reg_footprint")) x->half_reg_footprint = (unsigned)num(v[0]);
	else if (!strcmp(key, "full_reg_footprint")) x->full_reg_footprint = (unsigned)num(v[0]);
	else if (!strcmp(key, "branchstack")) x->branchstack = (unsigned)num(v[0]);
	else if (!strcmp(key, "mergedregs")) x->mergedregs = (int)num(v[0]);
	else if (!strcmp(key, "early_preamble")) x->early_preamble = (int)num(v[0]);
	else if (!strcmp(key, "const_ubo_idx")) x->const_ubo_idx = atoi(v[0]);
	else if (!strcmp(key, "const_data_offset")) x->const_data_offset = (uint32_t)num(v[0]);
	else if (!strcmp(key, "const_data_size")) x->const_data_size = (uint32_t)num(v[0]);
	else if (!strcmp(key, "pvtmem_per_fiber_size")) x->pvtmem_per_fiber_size = (uint32_t)num(v[0]);
	else if (!strcmp(key, "pvtmem_per_sp_size")) x->pvtmem_per_sp_size = (uint32_t)num(v[0]);
	else if (!strcmp(key, "pvtmem_va")) x->pvtmem_va = num(v[0]);
	else if (!strcmp(key, "pvtmem_per_wave")) x->pvtmem_per_wave = (int)num(v[0]);
	else if (!strcmp(key, "bindless_tex")) x->bindless_tex = (int)num(v[0]);
	else if (!strcmp(key, "bindless_samp")) x->bindless_samp = (int)num(v[0]);
	else if (!strcmp(key, "bindless_uav")) x->bindless_uav = (int)num(v[0]);
	else if (!strcmp(key, "bindless_ubo")) x->bindless_ubo = (int)num(v[0]);
	else if (!strcmp(key, "num_samp")) x->num_samp = (unsigned)num(v[0]);
	else if (!strcmp(key, "num_uav")) x->num_uav = (unsigned)num(v[0]);
	else {
		fprintf(stderr, "unknown shader key %s\n", key);
		exit(2);
	}
}

static int
run_scene(const struct adrenogpu_chip *chip, const char *dump, const char *params)
{
	struct adrenogpu_gmem_config gmem, sysmem;
	struct adrenogpu_pass pass;
	struct adrenogpu_program prog;
	unsigned prim = 4, instances = 1, vertices = 3;
	int with_program = 1;
	char line[512];
	FILE *f = fopen(params, "r");
	assert(f);
	adrenogpu_calc_gmem_layout(chip, 622592, &gmem, &sysmem);
	memset(&pass, 0, sizeof pass);
	memset(&prog, 0, sizeof prog);
	prog.vs.const_ubo_idx = prog.fs.const_ubo_idx = -1;
	/* every register id defaults to "none"; the parameter file names the ones that are used */
	prog.vs_vertexid_regid = prog.vs_instanceid_regid = prog.vs_viewid_regid = prog.vs_primid_regid = ADRENOGPU_REGID_INVALID;
	prog.vs_position_regid = ADRENOGPU_REGID_INVALID;
	for (unsigned i = 0; i < ADRENOGPU_MAX_VS_ATTRS; i++) prog.vs_attr[i].regid = ADRENOGPU_REGID_INVALID;
	for (unsigned i = 0; i < ADRENOGPU_MAX_VARYINGS; i++) prog.fs_varying[i].vs_regid = ADRENOGPU_REGID_INVALID;
	prog.fs_face_regid = prog.fs_sampleid_regid = prog.fs_samplemask_in_regid = prog.fs_shading_rate_regid =
	    prog.fs_coord_regid = ADRENOGPU_REGID_INVALID;
	memset(prog.fs_ij_regid, ADRENOGPU_REGID_INVALID, sizeof prog.fs_ij_regid);
	memset(prog.fs_color_regid, ADRENOGPU_REGID_INVALID, sizeof prog.fs_color_regid);
	prog.fs_depth_regid = prog.fs_samplemask_regid = prog.fs_stencilref_regid = ADRENOGPU_REGID_INVALID;
	while (fgets(line, sizeof line, f)) {
		char *tok[8], *save;
		unsigned n = 0;
		for (char *t = strtok_r(line, " \t\r\n", &save); t && n < 8; t = strtok_r(NULL, " \t\r\n", &save)) tok[n++] = t;
		if (!n) continue;
		const char *k = tok[0];
		char **v = tok + 1;
		if (!strcmp(k, "no_program")) with_program = 0;
		else if (!strcmp(k, "width")) pass.width = (unsigned)num(v[0]);
		else if (!strcmp(k, "height")) pass.height = (unsigned)num(v[0]);
		else if (!strcmp(k, "color.va")) pass.color.va = num(v[0]);
		else if (!strcmp(k, "color.pitch")) pass.color.pitch = (uint32_t)num(v[0]);
		else if (!strcmp(k, "color.layer_bytes")) pass.color.layer_bytes = (uint32_t)num(v[0]);
		else if (!strcmp(k, "color.rb_format")) pass.color.rb_format = (unsigned)num(v[0]);
		else if (!strcmp(k, "color.swap")) pass.color.swap = (unsigned)num(v[0]);
		else if (!strcmp(k, "color.tile_mode")) pass.color.tile_mode = (unsigned)num(v[0]);
		else if (!strcmp(k, "border_color_va")) pass.border_color_va = num(v[0]);
		else if (!strcmp(k, "clear_mode")) pass.clear_mode = (unsigned)num(v[0]);
		else if (!strcmp(k, "clear_rgba")) for (unsigned i = 0; i < 4; i++) pass.clear_rgba[i] = (float)atof(v[i]);
		else if (!strcmp(k, "draw")) { prim = (unsigned)num(v[0]); instances = (unsigned)num(v[1]); vertices = (unsigned)num(v[2]); }
		else if (!strncmp(k, "vs.", 3)) set_xs(&prog.vs, k + 3, v);
		else if (!strncmp(k, "fs.", 3)) set_xs(&prog.fs, k + 3, v);
		else if (!strcmp(k, "vs_vertexid_regid")) prog.vs_vertexid_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "vs_instanceid_regid")) prog.vs_instanceid_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "vs_viewid_regid")) prog.vs_viewid_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "vs_primid_regid")) prog.vs_primid_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "vs_attr_in")) prog.vs_attr_in = (unsigned)num(v[0]);
		else if (!strcmp(k, "vs_attr")) {
			unsigned i = (unsigned)num(v[0]);
			assert(i < ADRENOGPU_MAX_VS_ATTRS);
			prog.vs_attr[i].regid = (uint8_t)num(v[1]);
			prog.vs_attr[i].writemask = (uint8_t)num(v[2]);
		} else if (!strcmp(k, "vs_position_regid")) prog.vs_position_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "fs_total_in")) prog.fs_total_in = (unsigned)num(v[0]);
		else if (!strcmp(k, "fs_varying")) {
			unsigned i = (unsigned)num(v[0]);
			assert(i < ADRENOGPU_MAX_VARYINGS);
			prog.fs_varying[i].inloc = (uint8_t)num(v[1]);
			prog.fs_varying[i].compmask = (uint8_t)num(v[2]);
			prog.fs_varying[i].flat = (uint8_t)num(v[3]);
			prog.fs_varying[i].vs_regid = (uint8_t)num(v[4]);
			if (i + 1 > prog.fs_num_varyings) prog.fs_num_varyings = i + 1;
		} else if (!strcmp(k, "fs_double_threadsize")) prog.fs_double_threadsize = (int)num(v[0]);
		else if (!strcmp(k, "fs_need_full_quad")) prog.fs_need_full_quad = (int)num(v[0]);
		else if (!strcmp(k, "fs_need_pixlod")) prog.fs_need_pixlod = (int)num(v[0]);
		else if (!strcmp(k, "fs_sample_shading")) prog.fs_sample_shading = (int)num(v[0]);
		else if (!strcmp(k, "fs_post_depth_coverage")) prog.fs_post_depth_coverage = (int)num(v[0]);
		else if (!strcmp(k, "fs_frag_face")) prog.fs_frag_face = (int)num(v[0]);
		else if (!strcmp(k, "fs_face_regid")) prog.fs_face_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "fs_sampleid_regid")) prog.fs_sampleid_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "fs_samplemask_in_regid")) prog.fs_samplemask_in_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "fs_shading_rate_regid")) prog.fs_shading_rate_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "fs_coord_regid")) prog.fs_coord_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "fs_ij_regid")) { for (unsigned i = 0; i < 7; i++) prog.fs_ij_regid[i] = (uint8_t)num(v[i]); }
		else if (!strcmp(k, "fs_fragcoord_compmask")) prog.fs_fragcoord_compmask = (uint8_t)num(v[0]);
		else if (!strcmp(k, "fs_color")) {
			unsigned i = (unsigned)num(v[0]);
			assert(i < 8);
			prog.fs_color_regid[i] = (uint8_t)num(v[1]);
			prog.fs_color_half[i] = (uint8_t)num(v[2]);
		} else if (!strcmp(k, "fs_aliased_components")) prog.fs_aliased_components = (uint32_t)num(v[0]);
		else if (!strcmp(k, "fs_depth_regid")) prog.fs_depth_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "fs_samplemask_regid")) prog.fs_samplemask_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "fs_stencilref_regid")) prog.fs_stencilref_regid = (uint8_t)num(v[0]);
		else if (!strcmp(k, "fs_dual_src_blend")) prog.fs_dual_src_blend = (int)num(v[0]);
		else {
			fprintf(stderr, "unknown key %s\n", k);
			return 2;
		}
	}
	fclose(f);
	uint32_t buf[4096];
	struct adrenogpu_cs cs;
	adrenogpu_cs_init(&cs, buf, 4096);
	adrenogpu_pm4_emit_pass_begin(&cs, &pass, &sysmem);
	if (with_program) adrenogpu_pm4_emit_program(&cs, chip, &prog);
	adrenogpu_pm4_emit_draw_auto(&cs, prim, instances, vertices);
	adrenogpu_pm4_emit_pass_end(&cs);
	if (cs.err) {
		fprintf(stderr, "stream error\n");
		return 1;
	}
	f = fopen(dump, "wb");
	assert(f && fwrite(buf, 4, cs.n, f) == cs.n);
	fclose(f);
	printf("scene: %zu dwords\n", cs.n);
	return 0;
}

int
main(int argc, char **argv)
{
	struct adrenogpu_chip chip = adrenogpu_chip_a810();
	struct adrenogpu_gmem_config gmem, sysmem;

	/* The 608 KiB layout the Turnip captures were made with (TU_GMEM=622592): offsets read back from cffdump. */
	unsigned low = adrenogpu_calc_gmem_layout(&chip, 622592, &gmem, &sysmem);
	assert(sysmem.depth_ccu_offset == 0 && sysmem.color_ccu_offset == 0x40000);
	assert(sysmem.vpc_pos_offset == 0x60000 && sysmem.vpc_attr_offset == 0x70000 && sysmem.vpc_bv_pos_offset == 0x90000);
	assert(low == gmem.depth_ccu_offset);
	/* GMEM-mode state of the same capture: RB_CCU_CACHE_CNTL colour 0x88000, depth 0x48000, VPC 0x8c000/0x8f000/0x93000. */
	assert(gmem.color_ccu_offset == 0x88000 && gmem.depth_ccu_offset == 0x48000);
	assert(gmem.vpc_pos_offset == 0x8c000 && gmem.vpc_attr_offset == 0x8f000 && gmem.vpc_bv_pos_offset == 0x93000);
	printf("PASS: GMEM layout equals the one Turnip emitted for 608 KiB\n");

	/* On the real 576 KiB the same layout needs 32 KiB more than exists: the lowest offset wraps. */
	low = adrenogpu_calc_gmem_layout(&chip, 576 * 1024, &gmem, &sysmem);
	assert((int)sysmem.depth_ccu_offset == -32768 && (int)low > 0);  /* sysmem overruns by 32 KiB, GMEM mode fits */
	printf("PASS: the A810 sysmem layout does not fit 576 KiB (lowest offset %d), GMEM mode does\n",
	    (int)sysmem.depth_ccu_offset);

	if (argc > 3 && !strcmp(argv[1], "scene")) return run_scene(&chip, argv[2], argv[3]);
	if (argc > 3 && !strcmp(argv[1], "fill2d")) {
		/* fill2d FILE VA WORDS VALUE: a 2D solid fill of a linear R32_UINT buffer, the stream of vkCmdFillBuffer. */
		uint32_t buf[64];
		struct adrenogpu_cs cs;
		struct adrenogpu_clear_2d c = { { strtoull(argv[2 + 1], NULL, 16), 0, A8XX_E_FMT6_32_UINT, A8XX_E_WZYX,
		    A8XX_E_TILE6_LINEAR, 0 }, A8XX_E_R2D_INT32, A8XX_E_OUTPUT_IFMT_2D_UINT, { 0 }, 0, 0,
		    (unsigned)atoi(argv[4]), 1 };
		c.words[0] = (uint32_t)strtoul(argv[5], NULL, 16);
		adrenogpu_cs_init(&cs, buf, 64);
		adrenogpu_pm4_emit_clear_2d(&cs, &c);
		assert(!cs.err);
		FILE *f = fopen(argv[2], "wb");
		assert(f && fwrite(buf, 4, cs.n, f) == cs.n);
		fclose(f);
		printf("fill2d: %zu dwords\n", cs.n);
		return 0;
	}
	if (argc > 11 && !strcmp(argv[1], "pass")) {
		/* pass FILE W H VA PITCH LAYER FMT SWAP TILE BORDER [CLEARMODE R G B A]: one pass (begin, draw, end) for
		 * the Turnip comparison. */
		adrenogpu_calc_gmem_layout(&chip, 622592, &gmem, &sysmem);
		struct adrenogpu_pass pass;
		memset(&pass, 0, sizeof pass);
		pass.width = (unsigned)atoi(argv[3]);
		pass.height = (unsigned)atoi(argv[4]);
		pass.color.va = strtoull(argv[5], NULL, 16);
		pass.color.pitch = (uint32_t)atoi(argv[6]);
		pass.color.layer_bytes = (uint32_t)atoi(argv[7]);
		pass.color.rb_format = (unsigned)atoi(argv[8]);
		pass.color.swap = (unsigned)atoi(argv[9]);
		pass.color.tile_mode = (unsigned)atoi(argv[10]);
		pass.border_color_va = strtoull(argv[11], NULL, 16);
		if (argc > 16) {
			pass.clear_mode = (unsigned)atoi(argv[12]);
			for (unsigned i = 0; i < 4; i++) pass.clear_rgba[i] = (float)atof(argv[13 + i]);
		}
		uint32_t buf[2048];
		struct adrenogpu_cs cs;
		adrenogpu_cs_init(&cs, buf, 2048);
		adrenogpu_pm4_emit_pass_begin(&cs, &pass, &sysmem);
		size_t begin = cs.n;
		adrenogpu_pm4_emit_draw_auto(&cs, 4, 1, 3);
		adrenogpu_pm4_emit_pass_end(&cs);
		assert(!cs.err);
		FILE *f = fopen(argv[2], "wb");
		assert(f && fwrite(buf, 4, cs.n, f) == cs.n);
		fclose(f);
		printf("pass: %zu dwords (%zu before the draw)\n", cs.n, begin);
		return 0;
	}
	if (argc > 1) {
		/* Dump the restore stream for the comparison against Turnip. */
		adrenogpu_calc_gmem_layout(&chip, 622592, &gmem, &sysmem);
		uint32_t buf[1024];
		struct adrenogpu_cs cs;
		adrenogpu_cs_init(&cs, buf, 1024);
		adrenogpu_pm4_emit_restore(&cs, &sysmem, argc > 2 ? strtoull(argv[2], NULL, 16) : 0);
		assert(!cs.err);
		FILE *f = fopen(argv[1], "wb");
		assert(f && fwrite(buf, 4, cs.n, f) == cs.n);
		fclose(f);
		printf("restore: %zu dwords\n", cs.n);
	}
	return 0;
}
