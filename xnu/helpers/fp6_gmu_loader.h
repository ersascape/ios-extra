/* Gen8.3 firmware upload, following KGSL gen8_gmu_process_prealloc/load_fw.
 * Include after fp6_gmu_fw.h. Caller owns DMA mappings and power sequencing.
 * No callback may release CM3 reset. Failure leaves it held in reset.
 * Caller retains all reservations on failure until the master is quiescent;
 * reserve must accept an already-backed contained range on retry.
 */
#ifndef FP6_GMU_LOADER_H
#define FP6_GMU_LOADER_H

struct fp6_gmu_loader_ops {
	/* Reserve zeroed backing and install a GMU IOVA mapping. */
	int (*reserve)(void *, uint32_t address, uint32_t size, int cached);
	/* Copy into an existing mapping; never create a mapping implicitly. */
	int (*copy)(void *, uint32_t address, const uint8_t *, uint32_t size);
	/* Register index is in GPU dwords, NOT a physical byte address. */
	int (*write_tcm)(void *, uint32_t register_index, uint32_t value);
	/* Verify CM3 reset and mapped/powered register access before upload. */
	int (*ready)(void *);
	/* Publish CPU writes to GMU (cache maintenance plus write barrier). */
	int (*publish)(void *);
};

/* Return VMA kind: 1 ITCM, 2 cached, 3 DTCM, 4 uncached kernel. */
static int fp6_gmu_loader_vma(uint32_t address, uint32_t size)
{
	uint64_t end = (uint64_t)address + size;
	if (!size) return 0;
	if (end <= 0x4000u) return 1;
	if (address >= 0x4000u && end <= 0x1000000u) return 2;
	if (address >= 0x10004000u && end <= 0x10008000u) return 3;
	if (address >= 0x60000000u && end <= 0x80000000u) return 4;
	if (address >= 0xc0000000u && end <= 0xe0000000u) return 4;
	return 0;
}

static int fp6_gmu_loader_upload(const struct fp6_gmu_loader_ops *ops, void *ctx)
{
	unsigned i;
	if (!ops || !ops->ready || !ops->reserve || !ops->copy ||
	    !ops->write_tcm || !ops->publish || ops->ready(ctx)) return -1;
	/* Validate the complete descriptor set before allocating or writing. */
	for (i = 0; i < FP6_GMU_FW_PREALLOCATION_COUNT; i++) {
		const struct fp6_gmu_fw_preallocation *p = &fp6_gmu_fw_preallocations[i];
		if ((p->type != 1 && p->type != 7) ||
		    !fp6_gmu_loader_vma(p->address, p->size)) return -2;
	}
	for (i = 0; i < FP6_GMU_FW_BLOCK_COUNT; i++) {
		const struct fp6_gmu_fw_block *b = &fp6_gmu_fw_blocks[i];
		if (!b->data || (b->address & 3) || (b->size & 3) ||
		    b->type != 0xefbeaddeu || b->value != 0xefbeaddeu ||
		    !fp6_gmu_loader_vma(b->address, b->size)) return -2;
	}
	for (i = 0; i < FP6_GMU_FW_PREALLOCATION_COUNT; i++) {
		const struct fp6_gmu_fw_preallocation *p = &fp6_gmu_fw_preallocations[i];
		int kind = fp6_gmu_loader_vma(p->address, p->size);
		if ((kind == 2 || kind == 4) &&
		    ops->reserve(ctx, p->address, p->size, kind == 2)) return -3;
	}
	for (i = 0; i < FP6_GMU_FW_BLOCK_COUNT; i++) {
		const struct fp6_gmu_fw_block *b = &fp6_gmu_fw_blocks[i];
		int kind = fp6_gmu_loader_vma(b->address, b->size);
		uint32_t offset;
		if (kind == 2 || kind == 4) {
			if (ops->copy(ctx, b->address, b->data, b->size)) return -4;
			continue;
		}
		for (offset = 0; offset < b->size; offset += 4) {
			const uint8_t *d = b->data + offset;
			uint32_t word = (uint32_t)d[0] | ((uint32_t)d[1] << 8) |
			    ((uint32_t)d[2] << 16) | ((uint32_t)d[3] << 24);
			uint32_t base = kind == 1 ? 0x1b400u : 0x1c400u;
			uint32_t start = kind == 1 ? 0 : 0x10004000u;
			if (ops->write_tcm(ctx, base + (b->address - start + offset) / 4,
			    word)) return -5;
		}
	}
	return ops->publish(ctx) ? -6 : 0;
}
#endif
