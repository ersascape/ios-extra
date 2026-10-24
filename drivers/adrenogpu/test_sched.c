/* SPDX-License-Identifier: MIT */
#include "adrenogpu_sched.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static struct adrenogpu_vm_table
alloc_table(void *c)
{
	(void)c;
	struct adrenogpu_vm_table t = { 0, 0 };
	void *p = aligned_alloc(4096, 4096);
	memset(p, 0, 4096);
	t.cpu = p;
	t.pa = (uint64_t)(uintptr_t)p;
	return t;
}
static void free_table(void *c, struct adrenogpu_vm_table t) { (void)c; free(t.cpu); }
static const struct adrenogpu_vm_ops ops = { 0, alloc_table, free_table, 0, 0 };

static uint32_t ring[256];
static const uint64_t FENCE_VA = 0xffffff0000001000ull;
#define FRAMING_DWORDS 36u

static uint32_t
word_at(uint32_t start, uint32_t i, uint32_t size)
{
	return ring[(start + i) & (size - 1)];
}

/* Find the fence MEM_WRITE in the framing that starts at ring position `start`, reading across the wrap. */
static int
fence_write(uint32_t start, uint32_t size, uint32_t n, uint64_t *va, uint32_t *value)
{
	uint32_t i = 0;
	while (i < n) {
		uint32_t h = word_at(start, i, size);
		assert((h >> 28) == 7u);
		unsigned count = h & 0x3fff, op = (h >> 16) & 0x7f;
		if (op == 0x3d) {
			*va = word_at(start, i + 1, size) | ((uint64_t)word_at(start, i + 2, size) << 32);
			*value = word_at(start, i + 3, size);
			return 1;
		}
		i += 1 + count;
	}
	return 0;
}

int
main(void)
{
	struct adrenogpu_ctx ctx;
	static uint64_t pages[4] = { 0x80000000ull, 0x80001000ull, 0x80002000ull, 0x80003000ull };
	struct adrenogpu_bo bo = { pages, 4, 1 };
	assert(adrenogpu_ctx_init(&ctx, &ops, 0x100000000ull, 0x200000000ull) == 0);
	assert(adrenogpu_ctx_map(&ctx, &bo, 0x100030000ull, ADRENOGPU_VM_WRITE) == 0);
	struct adrenogpu_submit job = { 0x100030000ull, 100, 0, 0, 0x1234, 0xdead, 0 }; /* fence fields must be ignored */
	struct adrenogpu_sched s;
	uint32_t wptr, fence;

	assert(adrenogpu_sched_init(&s, ring, 100, 0, FENCE_VA, 1000) == ADRENOGPU_SCHED_EINVAL);   /* not a power of two */
	assert(adrenogpu_sched_init(&s, ring, 128, 0, 0x1002, 1000) == ADRENOGPU_SCHED_EINVAL);     /* unaligned fence */
	assert(adrenogpu_sched_init(&s, ring, 128, 0, FENCE_VA, 0) == ADRENOGPU_SCHED_EINVAL);      /* no timeout */
	assert(adrenogpu_sched_init(&s, ring, 128, 0, FENCE_VA, 1000) == 0);
	printf("PASS: queue initialisation is validated\n");

	/* A submit writes the framing with the queue's own fence address and sequence. */
	assert(adrenogpu_sched_submit(&s, &ctx, &job, 0, 10, &wptr, &fence) == 0);
	assert(wptr == FRAMING_DWORDS && fence == 1 && s.count == 1 && s.next_seq == 1);
	uint64_t va;
	uint32_t value;
	assert(fence_write(0, 128, FRAMING_DWORDS, &va, &value) && va == FENCE_VA && value == 1);
	printf("PASS: submit frames the IB with the queue's fence address and sequence\n");

	/* Unmapped IBs and bad extents are refused without touching the ring or the queue. */
	memset(ring, 0xa5, sizeof ring);
	struct adrenogpu_submit bad = job;
	bad.ib_va = 0x100040000ull;
	assert(adrenogpu_sched_submit(&s, &ctx, &bad, 0, 10, &wptr, &fence) == ADRENOGPU_SCHED_EUNMAPPED);
	bad = job;
	bad.ib_dwords = 4 * 1024 + 1;
	assert(adrenogpu_sched_submit(&s, &ctx, &bad, 0, 10, &wptr, &fence) == ADRENOGPU_SCHED_EUNMAPPED);
	bad = job;
	bad.ib2_va = 0x100050000ull;
	bad.ib2_dwords = 4;
	assert(adrenogpu_sched_submit(&s, &ctx, &bad, 0, 10, &wptr, &fence) == ADRENOGPU_SCHED_EUNMAPPED);
	assert(ring[0] == 0xa5a5a5a5u && ring[FRAMING_DWORDS] == 0xa5a5a5a5u && s.rb.wptr == FRAMING_DWORDS && s.count == 1);
	printf("PASS: an IB outside the context's mappings is refused and the ring is untouched\n");

	/* Poll retires in order; a hang is reported once the deadline passes. */
	assert(adrenogpu_sched_submit(&s, &ctx, &job, 0, 20, &wptr, &fence) == 0 && fence == 2 && wptr == 2 * FRAMING_DWORDS);
	assert(adrenogpu_sched_poll(&s, 500, 0) == ADRENOGPU_SCHED_OK && s.count == 2);
	assert(adrenogpu_sched_poll(&s, 500, 1) == ADRENOGPU_SCHED_OK && s.count == 1);
	assert(adrenogpu_ctx_fence_done(&ctx, 1) && !adrenogpu_ctx_fence_done(&ctx, 2));
	assert(adrenogpu_sched_poll(&s, 1019, 1) == ADRENOGPU_SCHED_OK);                      /* deadline 20 + 1000 */
	assert(adrenogpu_sched_poll(&s, 1020, 1) == ADRENOGPU_SCHED_HUNG);
	assert(adrenogpu_sched_poll(&s, 1020, 2) == ADRENOGPU_SCHED_OK && s.count == 0);
	assert(adrenogpu_ctx_fence_done(&ctx, 2) && s.retired == 2);
	printf("PASS: jobs retire in order from the fence word and a stuck job is reported as hung\n");

	/* Free space: a job larger than the space is refused, and fits once the read pointer moves. */
	assert(adrenogpu_sched_init(&s, ring, 64, 50, FENCE_VA, 1000) == 0);
	assert(adrenogpu_rb_space(&s.rb, 50) == 63 && adrenogpu_rb_space(&s.rb, 51) == 0 && adrenogpu_rb_space(&s.rb, 20) == 33);
	assert(adrenogpu_sched_submit(&s, &ctx, &job, 20, 0, &wptr, &fence) == ADRENOGPU_SCHED_EBUSY);
	assert(s.count == 0 && s.rb.wptr == 50 && s.submitted == 0);
	printf("PASS: a job larger than the free space is refused\n");

	/* Wrap: the framing straddles the end of the ring and reads back intact. */
	memset(ring, 0, sizeof ring);
	assert(adrenogpu_sched_submit(&s, &ctx, &job, 49, 0, &wptr, &fence) == 0);
	assert(wptr == ((50 + FRAMING_DWORDS) & 63) && wptr == 22);
	assert(fence_write(50, 64, FRAMING_DWORDS, &va, &value) && va == FENCE_VA && value == 1);
	assert(ring[63] != 0 && ring[0] != 0 && ring[21] != 0 && ring[22] == 0);               /* both sides written, nothing beyond */
	printf("PASS: a job that straddles the end of the ring is written and read back intact\n");

	/* The job table is bounded. */
	assert(adrenogpu_sched_init(&s, ring, 256, 0, FENCE_VA, 1000) == 0);
	for (unsigned i = 0; i < ADRENOGPU_SCHED_MAX_JOBS; i++) {
		struct adrenogpu_submit small = job;
		small.ib_dwords = 4;
		assert(adrenogpu_sched_submit(&s, &ctx, &small, s.rb.wptr, 0, &wptr, &fence) == 0); /* rptr == wptr: ring empty */
	}
	assert(s.count == ADRENOGPU_SCHED_MAX_JOBS);
	assert(adrenogpu_sched_submit(&s, &ctx, &job, s.rb.wptr, 0, &wptr, &fence) == ADRENOGPU_SCHED_EBUSY);
	printf("PASS: the job table is bounded\n");

	/* Reset: pending jobs are abandoned, their fences wake waiters and read as lost, new work gets later fences. */
	struct adrenogpu_ctx ctx2;
	assert(adrenogpu_ctx_init(&ctx2, &ops, 0x100000000ull, 0x200000000ull) == 0);
	assert(adrenogpu_ctx_map(&ctx2, &bo, 0x100030000ull, ADRENOGPU_VM_WRITE) == 0);
	assert(adrenogpu_sched_init(&s, ring, 256, 0, FENCE_VA, 1000) == 0);
	uint32_t f1, f2, f3;
	assert(adrenogpu_sched_submit(&s, &ctx2, &job, 0, 0, &wptr, &f1) == 0);
	assert(adrenogpu_sched_poll(&s, 0, 1) == ADRENOGPU_SCHED_OK && adrenogpu_ctx_fence_done(&ctx2, f1) && !adrenogpu_ctx_fence_lost(&ctx2, f1));
	assert(adrenogpu_sched_submit(&s, &ctx2, &job, 0, 0, &wptr, &f2) == 0);
	assert(adrenogpu_sched_submit(&s, &ctx2, &job, 0, 0, &wptr, &f3) == 0);
	assert(adrenogpu_sched_reset(&s, 0) == 2 && s.count == 0 && s.rb.wptr == 0 && s.failed == 2);
	assert(adrenogpu_ctx_fence_done(&ctx2, f2) && adrenogpu_ctx_fence_done(&ctx2, f3));
	assert(adrenogpu_ctx_fence_lost(&ctx2, f2) && adrenogpu_ctx_fence_lost(&ctx2, f3) && !adrenogpu_ctx_fence_lost(&ctx2, f1));
	uint32_t f4;
	assert(adrenogpu_sched_submit(&s, &ctx2, &job, 0, 0, &wptr, &f4) == 0 && f4 == 4 && s.next_seq == 4);
	assert(adrenogpu_sched_poll(&s, 0, 4) == ADRENOGPU_SCHED_OK && adrenogpu_ctx_fence_done(&ctx2, f4) && !adrenogpu_ctx_fence_lost(&ctx2, f4));
	printf("PASS: a reset abandons pending jobs, wakes their waiters and marks the fences lost\n");

	/* The 32-bit sequence wraps, skipping 0. */
	assert(adrenogpu_sched_init(&s, ring, 256, 0, FENCE_VA, 1000) == 0);
	s.next_seq = 0xfffffffeu;
	adrenogpu_ctx_destroy(&ctx);
	assert(adrenogpu_ctx_init(&ctx, &ops, 0x100000000ull, 0x200000000ull) == 0);
	assert(adrenogpu_ctx_map(&ctx, &bo, 0x100030000ull, ADRENOGPU_VM_WRITE) == 0);
	for (unsigned i = 0; i < 3; i++) assert(adrenogpu_sched_submit(&s, &ctx, &job, s.rb.wptr, 0, &wptr, &fence) == 0);
	assert(s.jobs[0].seq == 0xffffffffu && s.jobs[1].seq == 1 && s.jobs[2].seq == 2);
	assert(adrenogpu_sched_poll(&s, 0, 1) == ADRENOGPU_SCHED_OK && s.count == 1 && s.retired_seq == 1);
	printf("PASS: the sequence wraps and skips zero\n");

	adrenogpu_ctx_destroy(&ctx);
	adrenogpu_ctx_destroy(&ctx2);
	return 0;
}
