/* SPDX-License-Identifier: MIT */
#include "adrenogpu_ring.h"

#define OP_WAIT_FOR_IDLE 0x26u
#define OP_CCHE_INVALIDATE 0x3au
#define OP_MEM_WRITE 0x3du
#define OP_INDIRECT_BUFFER 0x3fu
#define OP_THREAD_CONTROL 0x17u
#define OP_RESET_CONTEXT_STATE 0x1fu
#define OP_SET_MARKER 0x65u
#define OP_EVENT_WRITE7 0x46u

#define THREAD_BR 1u
#define THREAD_BOTH 3u
#define THREAD_SYNC (1u << 31)
#define EVENT_CCU_CLEAN_DEPTH 0x20u
#define EVENT_CCU_CLEAN_COLOR 0x21u
#define EVENT_CACHE_CLEAN 0x31u
#define EVENT_CACHE_INVALIDATE7 0x33u
#define MARKER_IFPC_DISABLE 0x101u
#define RESET_CONTEXT_ALL 0xfu /* CLEAR_ON_CHIP_TS | CLEAR_RESOURCE_TABLE | CLEAR_BV_BR_COUNTER | RESET_GLOBAL_LOCAL_TS */

static unsigned
odd(unsigned x)
{
	unsigned parity = 1;
	while (x) {
		parity ^= 1;
		x &= x - 1;
	}
	return parity;
}

uint32_t
adrenogpu_pkt7(unsigned opcode, unsigned count)
{
	return 0x70000000u | count | (odd(count) << 15) | ((opcode & 0x7fu) << 16) | (odd(opcode & 0x7fu) << 23);
}

struct writer {
	uint32_t *out;
	size_t capacity, n;
	int overflow;
};

static void
put(struct writer *w, uint32_t word)
{
	if (w->n >= w->capacity) {
		w->overflow = 1;
		return;
	}
	w->out[w->n++] = word;
}

static void pkt1(struct writer *w, unsigned op, uint32_t a) { put(w, adrenogpu_pkt7(op, 1)); put(w, a); }
static void pkt0(struct writer *w, unsigned op) { put(w, adrenogpu_pkt7(op, 0)); }

static void
indirect(struct writer *w, uint64_t va, uint32_t dwords)
{
	put(w, adrenogpu_pkt7(OP_INDIRECT_BUFFER, 3));
	put(w, (uint32_t)va);
	put(w, (uint32_t)(va >> 32));
	put(w, dwords);
}

size_t
adrenogpu_ring_build_submit(const struct adrenogpu_submit *s, uint32_t *out, size_t capacity)
{
	if (!s || !out || !s->ib_va || !s->ib_dwords || s->ib_dwords > 0xfffffu || (s->ib_va & 3u) ||
	    !s->fence_va || (s->fence_va & 3u) || (s->ib2_va && (!s->ib2_dwords || s->ib2_dwords > 0xfffffu || (s->ib2_va & 3u))) ||
	    (!s->ib2_va && s->ib2_dwords) || (s->flags & ~(unsigned)(ADRENOGPU_SUBMIT_NO_INVALIDATE | ADRENOGPU_SUBMIT_NO_CLEAN)))
		return 0;
	struct writer w = { out, capacity, 0, 0 };
	pkt1(&w, OP_THREAD_CONTROL, THREAD_BOTH | THREAD_SYNC);
	pkt1(&w, OP_RESET_CONTEXT_STATE, RESET_CONTEXT_ALL);
	pkt1(&w, OP_THREAD_CONTROL, THREAD_BR | THREAD_SYNC);
	pkt1(&w, OP_THREAD_CONTROL, THREAD_BOTH);
	pkt1(&w, OP_SET_MARKER, MARKER_IFPC_DISABLE);
	pkt1(&w, OP_THREAD_CONTROL, THREAD_BR);
	if (!(s->flags & ADRENOGPU_SUBMIT_NO_INVALIDATE)) {
		pkt1(&w, OP_EVENT_WRITE7, EVENT_CACHE_INVALIDATE7);
		pkt0(&w, OP_CCHE_INVALIDATE);
		pkt0(&w, OP_WAIT_FOR_IDLE);
	}
	indirect(&w, s->ib_va, s->ib_dwords);
	if (s->ib2_va) indirect(&w, s->ib2_va, s->ib2_dwords);
	/* Both threads, synchronised, before waiting for idle: waiting first stalls a stream that ends in BR-only
	 * concurrent-bin-disable mode. */
	pkt1(&w, OP_THREAD_CONTROL, THREAD_BOTH | THREAD_SYNC);
	pkt0(&w, OP_WAIT_FOR_IDLE);
	if (!(s->flags & ADRENOGPU_SUBMIT_NO_CLEAN)) {
		pkt1(&w, OP_EVENT_WRITE7, EVENT_CCU_CLEAN_COLOR);
		pkt1(&w, OP_EVENT_WRITE7, EVENT_CCU_CLEAN_DEPTH);
		pkt1(&w, OP_EVENT_WRITE7, EVENT_CACHE_CLEAN);
		pkt0(&w, OP_WAIT_FOR_IDLE);
	}
	put(&w, adrenogpu_pkt7(OP_MEM_WRITE, 3));
	put(&w, (uint32_t)s->fence_va);
	put(&w, (uint32_t)(s->fence_va >> 32));
	put(&w, s->fence_value);
	pkt1(&w, OP_THREAD_CONTROL, THREAD_BOTH);
	return w.overflow ? 0 : w.n;
}
