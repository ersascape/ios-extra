/* SPDX-License-Identifier: MIT */
#include "adrenogpu_ring.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

/* Independent walker: every header must carry correct parity and the stream must end exactly on a packet. */
static unsigned
popcount(unsigned x) { unsigned n = 0; while (x) { n += x & 1u; x >>= 1; } return n; }

static unsigned
walk(const uint32_t *w, size_t n, unsigned *opcodes, unsigned max)
{
	unsigned packets = 0;
	size_t i = 0;
	while (i < n) {
		uint32_t h = w[i];
		assert((h >> 28) == 7u);
		unsigned count = h & 0x3fffu, op = (h >> 16) & 0x7fu;
		assert(((h >> 15) & 1u) == ((popcount(count) & 1u) ^ 1u));
		assert(((h >> 23) & 1u) == ((popcount(op) & 1u) ^ 1u));
		assert(i + 1 + count <= n);
		if (packets < max) opcodes[packets] = op;
		packets++;
		i += 1 + count;
	}
	assert(i == n);
	return packets;
}

int
main(void)
{
	/* Known headers from real captures (cffdump: 70460001 = CP_EVENT_WRITE7 with one dword, 70268000 = WAIT_FOR_IDLE). */
	assert(adrenogpu_pkt7(0x46, 1) == 0x70460001u);
	assert(adrenogpu_pkt7(0x26, 0) == 0x70268000u);
	assert(adrenogpu_pkt7(0x17, 1) == 0x70970001u);       /* CP_THREAD_CONTROL, first packet of every capture */
	printf("PASS: type-7 headers match captured Turnip headers\n");

	struct adrenogpu_submit s = { 0x10002e000ull, 343, 0, 0, 0x7fff0400ull, 0x600dcafeu, 0 };
	uint32_t w[ADRENOGPU_SUBMIT_MAX_DWORDS];
	size_t n = adrenogpu_ring_build_submit(&s, w, ADRENOGPU_SUBMIT_MAX_DWORDS);
	unsigned ops[ADRENOGPU_SUBMIT_MAX_DWORDS];
	unsigned packets = walk(w, n, ops, ADRENOGPU_SUBMIT_MAX_DWORDS);
	const unsigned want_ops[] = { 0x17, 0x1f, 0x17, 0x17, 0x65, 0x17, 0x46, 0x3a, 0x26, 0x3f, 0x17, 0x26,
	    0x46, 0x46, 0x46, 0x26, 0x3d, 0x17 };
	assert(packets == sizeof want_ops / sizeof *want_ops);
	for (unsigned i = 0; i < packets; i++) assert(ops[i] == want_ops[i]);
	assert(n == 36);
	/* Payload spot checks: IB address split, size, fence address and value, event ids. */
	size_t ib = 0;
	while (!(((w[ib] >> 16) & 0x7f) == 0x3f)) ib += 1 + (w[ib] & 0x3fff);
	assert(w[ib + 1] == 0x0002e000u && w[ib + 2] == 1u && w[ib + 3] == 343u);
	size_t mw = ib;
	while (!(((w[mw] >> 16) & 0x7f) == 0x3d)) mw += 1 + (w[mw] & 0x3fff);
	assert(w[mw + 1] == 0x7fff0400u && w[mw + 2] == 0u && w[mw + 3] == 0x600dcafeu);
	/* Thread control: first both|sync, BR|sync, both, BR before the IB, both|sync after, both at the end. */
	assert(w[1] == 0x80000003u && w[5] == 0x80000001u && w[7] == 3u && w[11] == 1u);
	assert(w[n - 1] == 3u);
	printf("PASS: submission framing has the sequence the phone ran (%zu dwords, %u packets)\n", n, packets);

	/* Optional second stream, and the A/B switches. */
	struct adrenogpu_submit two = s;
	two.ib2_va = 0x100050000ull;
	two.ib2_dwords = 100;
	assert(adrenogpu_ring_build_submit(&two, w, ADRENOGPU_SUBMIT_MAX_DWORDS) == 40);
	walk(w, 40, ops, ADRENOGPU_SUBMIT_MAX_DWORDS);
	struct adrenogpu_submit lean = s;
	lean.flags = ADRENOGPU_SUBMIT_NO_INVALIDATE | ADRENOGPU_SUBMIT_NO_CLEAN;
	size_t nl = adrenogpu_ring_build_submit(&lean, w, ADRENOGPU_SUBMIT_MAX_DWORDS);
	assert(nl == 36 - 4 - 7);
	walk(w, nl, ops, ADRENOGPU_SUBMIT_MAX_DWORDS);
	printf("PASS: second stream and the invalidate/clean switches\n");

	/* Refusals leave the buffer untouched. */
	uint32_t guard[ADRENOGPU_SUBMIT_MAX_DWORDS];
	memset(guard, 0xa5, sizeof guard);
	struct adrenogpu_submit bad = s;
	bad.ib_dwords = 0;
	assert(adrenogpu_ring_build_submit(&bad, guard, ADRENOGPU_SUBMIT_MAX_DWORDS) == 0);
	bad = s; bad.ib_va = 0x1002; assert(adrenogpu_ring_build_submit(&bad, guard, ADRENOGPU_SUBMIT_MAX_DWORDS) == 0);
	bad = s; bad.fence_va = 0; assert(adrenogpu_ring_build_submit(&bad, guard, ADRENOGPU_SUBMIT_MAX_DWORDS) == 0);
	bad = s; bad.ib2_dwords = 4; assert(adrenogpu_ring_build_submit(&bad, guard, ADRENOGPU_SUBMIT_MAX_DWORDS) == 0);
	bad = s; bad.flags = 0x40; assert(adrenogpu_ring_build_submit(&bad, guard, ADRENOGPU_SUBMIT_MAX_DWORDS) == 0);
	assert(adrenogpu_ring_build_submit(&s, guard, 35) == 0);
	assert(adrenogpu_ring_build_submit(&s, guard, 36) == 36);
	printf("PASS: invalid requests and short buffers are refused\n");
	return 0;
}
