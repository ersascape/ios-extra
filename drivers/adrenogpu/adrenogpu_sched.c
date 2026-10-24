/* SPDX-License-Identifier: MIT */
#include "adrenogpu_sched.h"

int
adrenogpu_sched_init(struct adrenogpu_sched *s, volatile uint32_t *ring, uint32_t ring_dwords, uint32_t wptr,
    uint64_t fence_va, uint64_t timeout)
{
	if (!s || !ring || ring_dwords < 64u || (ring_dwords & (ring_dwords - 1u)) || wptr >= ring_dwords ||
	    !fence_va || (fence_va & 3u) || !timeout)
		return ADRENOGPU_SCHED_EINVAL;
	s->rb.base = ring;
	s->rb.size = ring_dwords;
	s->rb.wptr = wptr;
	s->fence_va = fence_va;
	s->timeout = timeout;
	for (unsigned i = 0; i < ADRENOGPU_SCHED_MAX_JOBS; i++) s->jobs[i].state = ADRENOGPU_JOB_FREE;
	s->head = s->count = 0;
	s->next_seq = s->retired_seq = 0;
	s->submitted = s->retired = s->failed = 0;
	return ADRENOGPU_SCHED_OK;
}

uint32_t
adrenogpu_rb_space(const struct adrenogpu_rb *rb, uint32_t rptr)
{
	return (rptr - rb->wptr - 1u) & (rb->size - 1u);
}

int
adrenogpu_sched_submit(struct adrenogpu_sched *s, struct adrenogpu_ctx *ctx, const struct adrenogpu_submit *job,
    uint32_t rptr, uint64_t now, uint32_t *new_wptr, uint32_t *ctx_fence)
{
	if (!s || !ctx || !job || !new_wptr || !ctx_fence || rptr >= s->rb.size) return ADRENOGPU_SCHED_EINVAL;
	if (!adrenogpu_ctx_find(ctx, job->ib_va, 4ull * job->ib_dwords, 0) ||
	    (job->ib2_va && !adrenogpu_ctx_find(ctx, job->ib2_va, 4ull * job->ib2_dwords, 0)))
		return ADRENOGPU_SCHED_EUNMAPPED;
	if (s->count == ADRENOGPU_SCHED_MAX_JOBS) return ADRENOGPU_SCHED_EBUSY;
	/* The framing carries this scheduler's own fence address and sequence, whatever the caller put there. */
	struct adrenogpu_submit framed = *job;
	uint32_t seq = s->next_seq + 1u ? s->next_seq + 1u : 1u;
	framed.fence_va = s->fence_va;
	framed.fence_value = seq;
	uint32_t words[ADRENOGPU_SUBMIT_MAX_DWORDS];
	size_t n = adrenogpu_ring_build_submit(&framed, words, ADRENOGPU_SUBMIT_MAX_DWORDS);
	if (!n) return ADRENOGPU_SCHED_EINVAL;
	if (n > adrenogpu_rb_space(&s->rb, rptr)) return ADRENOGPU_SCHED_EBUSY;
	uint32_t wptr = s->rb.wptr;
	for (size_t i = 0; i < n; i++) {
		s->rb.base[wptr] = words[i];
		wptr = (wptr + 1u) & (s->rb.size - 1u);
	}
	s->rb.wptr = wptr;
	s->next_seq = seq;
	struct adrenogpu_job *j = &s->jobs[(s->head + s->count) % ADRENOGPU_SCHED_MAX_JOBS];
	j->ctx = ctx;
	j->ctx_fence = adrenogpu_ctx_new_fence(ctx);
	j->seq = seq;
	j->end_wptr = wptr;
	j->deadline = now + s->timeout;
	j->state = ADRENOGPU_JOB_PENDING;
	s->count++;
	s->submitted++;
	*new_wptr = wptr;
	*ctx_fence = j->ctx_fence;
	return ADRENOGPU_SCHED_OK;
}

int
adrenogpu_sched_poll(struct adrenogpu_sched *s, uint64_t now, uint32_t fence_value)
{
	while (s->count) {
		struct adrenogpu_job *j = &s->jobs[s->head];
		if ((int32_t)(fence_value - j->seq) < 0) break; /* the GPU has not got there */
		adrenogpu_ctx_retire(j->ctx, j->ctx_fence);
		s->retired_seq = j->seq;
		j->state = ADRENOGPU_JOB_FREE;
		s->head = (s->head + 1u) % ADRENOGPU_SCHED_MAX_JOBS;
		s->count--;
		s->retired++;
	}
	if (s->count && now >= s->jobs[s->head].deadline) return ADRENOGPU_SCHED_HUNG;
	return ADRENOGPU_SCHED_OK;
}

unsigned
adrenogpu_sched_reset(struct adrenogpu_sched *s, uint32_t wptr)
{
	unsigned failed = 0;
	while (s->count) {
		struct adrenogpu_job *j = &s->jobs[s->head];
		adrenogpu_ctx_lose(j->ctx, j->ctx_fence);
		j->state = ADRENOGPU_JOB_FREE;
		s->head = (s->head + 1u) % ADRENOGPU_SCHED_MAX_JOBS;
		s->count--;
		failed++;
	}
	s->failed += failed;
	s->rb.wptr = wptr & (s->rb.size - 1u);
	s->retired_seq = s->next_seq; /* sequences up to here will never be written */
	return failed;
}
