/* SPDX-License-Identifier: MIT */
#include "adrenogpu_ctx.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned live;
static unsigned fail_after, allocs;

static struct adrenogpu_vm_table
alloc_table(void *c)
{
	(void)c;
	struct adrenogpu_vm_table t = { 0, 0 };
	if (fail_after && allocs >= fail_after) return t;
	allocs++;
	void *p = aligned_alloc(4096, 4096);
	memset(p, 0, 4096);
	live++;
	t.cpu = p;
	t.pa = (uint64_t)(uintptr_t)p;
	return t;
}
static void free_table(void *c, struct adrenogpu_vm_table t) { (void)c; free(t.cpu); live--; }
static const struct adrenogpu_vm_ops ops = { 0, alloc_table, free_table, 0, 0 };

int
main(void)
{
	static uint64_t pages_a[8], pages_b[600];
	for (unsigned i = 0; i < 8; i++) pages_a[i] = 0x80000000ull + 0x3000ull * i; /* not contiguous */
	for (unsigned i = 0; i < 600; i++) pages_b[i] = 0x90000000ull + 0x1000ull * i;
	struct adrenogpu_bo a = { pages_a, 8, 1 }, b = { pages_b, 600, 2 };
	struct adrenogpu_ctx ctx;

	assert(adrenogpu_ctx_init(&ctx, &ops, 0x100000000ull, 0x200000000ull) == 0);
	assert(adrenogpu_ctx_init(&ctx, &ops, 0x1004, 0x2000) == ADRENOGPU_CTX_EINVAL);
	assert(adrenogpu_ctx_map(&ctx, &a, 0x100010000ull, ADRENOGPU_VM_WRITE) == 0);
	uint64_t pa;
	for (unsigned i = 0; i < 8; i++) {
		assert(adrenogpu_vm_translate(&ctx.vm, 0x100010000ull + i * 4096 + 0x10, &pa, NULL) == 0);
		assert(pa == pages_a[i] + 0x10);
	}
	printf("PASS: a scattered buffer object is mapped page by page\n");

	/* Range, alignment and overlap rules. */
	assert(adrenogpu_ctx_map(&ctx, &b, 0x100010000ull, 0) == ADRENOGPU_CTX_EOVERLAP);
	assert(adrenogpu_ctx_map(&ctx, &b, 0x10000e000ull, 0) == ADRENOGPU_CTX_EOVERLAP);  /* tail overlaps a */
	assert(adrenogpu_ctx_map(&ctx, &b, 0x0ff000ull, 0) == ADRENOGPU_CTX_EINVAL);       /* below the range */
	assert(adrenogpu_ctx_map(&ctx, &b, 0x1ffff00000ull, 0) == ADRENOGPU_CTX_EINVAL);   /* runs past the end */
	assert(adrenogpu_ctx_map(&ctx, &b, 0x100020010ull, 0) == ADRENOGPU_CTX_EINVAL);    /* unaligned */
	assert(adrenogpu_ctx_map(&ctx, &b, 0x100100000ull, ADRENOGPU_VM_WRITE | ADRENOGPU_VM_EXEC) == 0);
	assert(ctx.nmaps == 2);
	printf("PASS: range, alignment and overlap are enforced\n");

	/* find(): the whole extent must sit in one mapping with the requested protection. */
	assert(adrenogpu_ctx_find(&ctx, 0x100010000ull, 8 * 4096, ADRENOGPU_VM_WRITE));
	assert(!adrenogpu_ctx_find(&ctx, 0x100010000ull, 8 * 4096 + 1, 0));              /* one byte too long */
	assert(!adrenogpu_ctx_find(&ctx, 0x100010000ull, 16, ADRENOGPU_VM_EXEC));        /* a is not executable */
	assert(adrenogpu_ctx_find(&ctx, 0x100100000ull + 4096, 100, ADRENOGPU_VM_EXEC));
	assert(!adrenogpu_ctx_find(&ctx, 0x100018000ull, 4, 0));                         /* the gap after a */
	assert(!adrenogpu_ctx_find(&ctx, 0x100010000ull, 0, 0));                         /* empty range */
	assert(!adrenogpu_ctx_find(&ctx, ~0ull - 3, 8, 0));                              /* wraps */
	printf("PASS: find() requires one mapping and the protection\n");

	/* Unmap releases the pages and the range can be reused. */
	assert(adrenogpu_ctx_unmap(&ctx, 0x100010004ull) == ADRENOGPU_CTX_ENOENT);
	assert(adrenogpu_ctx_unmap(&ctx, 0x100010000ull) == 0);
	assert(adrenogpu_vm_translate(&ctx.vm, 0x100010000ull, NULL, NULL) == ADRENOGPU_VM_ENOENT);
	assert(adrenogpu_ctx_map(&ctx, &a, 0x100010000ull, 0) == 0 && ctx.nmaps == 2);
	printf("PASS: unmap frees the range for reuse\n");

	/* A failing page-table allocation rolls the whole mapping back. */
	adrenogpu_ctx_destroy(&ctx);
	assert(live == 0);
	allocs = 0; fail_after = 0;
	assert(adrenogpu_ctx_init(&ctx, &ops, 0x100000000ull, 0x200000000ull) == 0);
	unsigned base = allocs;
	fail_after = base + 4;
	int rc = adrenogpu_ctx_map(&ctx, &b, 0x1001ff000ull, 0);   /* pages straddle a 2 MiB boundary after the first */
	assert(rc == ADRENOGPU_CTX_EVM && ctx.nmaps == 0 && ctx.vm.mapped_pages == 0);
	fail_after = 0;
	assert(adrenogpu_ctx_map(&ctx, &b, 0x1001ff000ull, 0) == 0 && ctx.vm.mapped_pages == 600);
	printf("PASS: a failed mapping leaves nothing behind and can be retried\n");
	adrenogpu_ctx_destroy(&ctx);
	assert(live == 0);

	/* Fence timeline: increasing, wrap-safe, in-order retire, 0 never issued. */
	allocs = 0; fail_after = 0;
	assert(adrenogpu_ctx_init(&ctx, &ops, 0x100000000ull, 0x200000000ull) == 0);
	uint32_t f1 = adrenogpu_ctx_new_fence(&ctx), f2 = adrenogpu_ctx_new_fence(&ctx), f3 = adrenogpu_ctx_new_fence(&ctx);
	assert(f1 == 1 && f2 == 2 && f3 == 3);
	assert(!adrenogpu_ctx_fence_done(&ctx, f1) && !adrenogpu_ctx_fence_done(&ctx, 0));
	adrenogpu_ctx_retire(&ctx, f2);
	assert(adrenogpu_ctx_fence_done(&ctx, f1) && adrenogpu_ctx_fence_done(&ctx, f2) && !adrenogpu_ctx_fence_done(&ctx, f3));
	adrenogpu_ctx_retire(&ctx, f1);                 /* an older value never moves the timeline back */
	assert(adrenogpu_ctx_fence_done(&ctx, f2));
	adrenogpu_ctx_retire(&ctx, 99);                 /* a fence never issued cannot be retired */
	assert(!adrenogpu_ctx_fence_done(&ctx, f3));
	ctx.issued = ctx.retired = 0xfffffffeu;         /* wrap */
	uint32_t w1 = adrenogpu_ctx_new_fence(&ctx), w2 = adrenogpu_ctx_new_fence(&ctx), w3 = adrenogpu_ctx_new_fence(&ctx);
	assert(w1 == 0xffffffffu && w2 == 1 && w3 == 2);
	adrenogpu_ctx_retire(&ctx, w2);
	assert(adrenogpu_ctx_fence_done(&ctx, w1) && adrenogpu_ctx_fence_done(&ctx, w2) && !adrenogpu_ctx_fence_done(&ctx, w3));
	printf("PASS: fences are ordered and survive 32-bit wrap\n");
	adrenogpu_ctx_destroy(&ctx);
	assert(live == 0);
	return 0;
}
