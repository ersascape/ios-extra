/* SPDX-License-Identifier: MIT */
/* AdrenoGPU submission framing: the PM4 words the kernel writes onto the ring around a user IB.
 *
 * The sequence is the one replayed on the phone (fp6_replay_submit in bsd/dev/sweet_gpu.c, patches 0201 to
 * 0214): reset the context state with both threads synchronised, run the user IB on the BR thread, restore both
 * threads (which also clears any CONCURRENT_BIN_DISABLE the IB left set), invalidate and clean the caches, and
 * write a fence. Pure C, no hardware access. */
#ifndef ADRENOGPU_RING_H
#define ADRENOGPU_RING_H
#include <stddef.h>
#include <stdint.h>

#define ADRENOGPU_SUBMIT_MAX_DWORDS 48u

enum adrenogpu_submit_flags {
	ADRENOGPU_SUBMIT_NO_INVALIDATE = 1u, /* skip the UCHE/CCHE invalidate before the IB (A/B tests only) */
	ADRENOGPU_SUBMIT_NO_CLEAN = 2u,      /* skip the CCU/UCHE clean before the fence (A/B tests only) */
};

struct adrenogpu_submit {
	uint64_t ib_va;
	uint32_t ib_dwords;     /* 1..0xfffff */
	uint64_t ib2_va;        /* optional second stream, 0 = none */
	uint32_t ib2_dwords;
	uint64_t fence_va;      /* dword-aligned address of the fence word */
	uint32_t fence_value;
	unsigned flags;
};

/* PM4 type-7 header with odd-parity bits for opcode and count (A6xx and later). */
uint32_t adrenogpu_pkt7(unsigned opcode, unsigned count);

/* Write the framing into out. Returns the number of dwords, or 0 for an invalid request or too little room
 * (nothing is written then). */
size_t adrenogpu_ring_build_submit(const struct adrenogpu_submit *, uint32_t *out, size_t capacity);
#endif
