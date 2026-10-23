/* SPDX-License-Identifier: MIT */
/* Host test of the PM4 builder: layout arithmetic here, stream contents in tests/test_adrenogpu_pm4.py. */
#include "adrenogpu_pm4.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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
