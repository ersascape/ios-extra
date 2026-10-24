/* SPDX-License-Identifier: MIT */
/* AdrenoGPU submission queue: a command ring with wrap-around and free-space accounting, and a table of in-flight
 * jobs. It validates a job's IB against its context's mappings, writes the submit framing (adrenogpu_ring) into the
 * ring, hands back the new write pointer for the caller to program, retires jobs in order from the fence word the
 * GPU writes, and reports a hang when the oldest job outlives its deadline. No hardware access, no clock: the caller
 * passes `now` (any monotonic unit) and the ring read pointer and fence value it read. */
#ifndef ADRENOGPU_SCHED_H
#define ADRENOGPU_SCHED_H
#include "adrenogpu_ctx.h"
#include "adrenogpu_ring.h"

#define ADRENOGPU_SCHED_MAX_JOBS 16u

struct adrenogpu_rb {
	volatile uint32_t *base; /* CPU view of the ring */
	uint32_t size;           /* dwords, a power of two */
	uint32_t wptr;           /* next dword to write */
};

enum adrenogpu_job_state { ADRENOGPU_JOB_FREE = 0, ADRENOGPU_JOB_PENDING };

struct adrenogpu_job {
	struct adrenogpu_ctx *ctx;
	uint32_t ctx_fence;  /* the fence the context's client waits for */
	uint32_t seq;        /* the value written to the shared fence word */
	uint32_t end_wptr;   /* ring position after this job */
	uint64_t deadline;
	enum adrenogpu_job_state state;
};

struct adrenogpu_sched {
	struct adrenogpu_rb rb;
	uint64_t fence_va;   /* GPU address of the shared fence word, in the kernel's own mapping */
	uint64_t timeout;    /* job runtime allowed before it counts as hung */
	struct adrenogpu_job jobs[ADRENOGPU_SCHED_MAX_JOBS];
	unsigned head, count; /* oldest job and number in use (ring of jobs) */
	uint32_t next_seq, retired_seq;
	unsigned long submitted, retired, failed;
};

enum {
	ADRENOGPU_SCHED_OK = 0,
	ADRENOGPU_SCHED_EINVAL = -1,
	ADRENOGPU_SCHED_EUNMAPPED = -2, /* the IB (or the second stream) is not inside one mapping of the context */
	ADRENOGPU_SCHED_EBUSY = -3,     /* no free job slot or not enough ring space */
	ADRENOGPU_SCHED_HUNG = 1,       /* poll(): the oldest job passed its deadline */
};

int adrenogpu_sched_init(struct adrenogpu_sched *, volatile uint32_t *ring, uint32_t ring_dwords, uint32_t wptr,
    uint64_t fence_va, uint64_t timeout);
/* Free ring space in dwords given the read pointer (one slot stays unused so full differs from empty). */
uint32_t adrenogpu_rb_space(const struct adrenogpu_rb *, uint32_t rptr);

/* Queue one job. On success *new_wptr is the write pointer to program and *ctx_fence the fence to wait for.
 * Nothing is written to the ring on failure. */
int adrenogpu_sched_submit(struct adrenogpu_sched *, struct adrenogpu_ctx *, const struct adrenogpu_submit *job,
    uint32_t rptr, uint64_t now, uint32_t *new_wptr, uint32_t *ctx_fence);
/* Retire every job whose sequence the GPU has written; returns HUNG if the oldest unfinished job is past its
 * deadline, OK otherwise. */
int adrenogpu_sched_poll(struct adrenogpu_sched *, uint64_t now, uint32_t fence_value);
/* After a GPU reset: the ring is empty again at `wptr`; every pending job fails and its context fence retires so
 * waiters wake. Returns the number of jobs failed. */
unsigned adrenogpu_sched_reset(struct adrenogpu_sched *, uint32_t wptr);
#endif
