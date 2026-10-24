/* SPDX-License-Identifier: MIT */
/* AdrenoGPU context: one GPU address space, the buffer objects mapped into it, and a fence timeline.
 *
 * A buffer object is a list of 4 KiB physical pages (from any allocator). A context maps whole buffer objects at
 * page-aligned GPU addresses inside its allowed range with explicit protection; the kernel checks an IB's address
 * and its fence address against these mappings before it submits. Pure C, built on adrenogpu_vm. */
#ifndef ADRENOGPU_CTX_H
#define ADRENOGPU_CTX_H
#include "adrenogpu_vm.h"

#define ADRENOGPU_CTX_MAX_MAPS 2048u

struct adrenogpu_bo {
	const uint64_t *pages; /* physical address of every 4 KiB page, borrowed for the life of its mappings */
	unsigned long npages;
	uint32_t id;
};

struct adrenogpu_mapping {
	uint64_t va;
	const struct adrenogpu_bo *bo;
	unsigned prot;
};

struct adrenogpu_ctx {
	struct adrenogpu_vm vm;
	struct adrenogpu_mapping maps[ADRENOGPU_CTX_MAX_MAPS];
	unsigned nmaps;
	uint64_t va_lo, va_hi; /* mappings must lie in [va_lo, va_hi) */
	uint32_t issued, retired; /* fence timeline; 0 is never issued */
};

enum {
	ADRENOGPU_CTX_OK = 0,
	ADRENOGPU_CTX_EINVAL = -1,
	ADRENOGPU_CTX_EOVERLAP = -2, /* the range touches an existing mapping */
	ADRENOGPU_CTX_ENOENT = -3,
	ADRENOGPU_CTX_EFULL = -4,    /* mapping table full */
	ADRENOGPU_CTX_EVM = -5,      /* the page-table core failed (see vm status), nothing stays mapped */
};

int adrenogpu_ctx_init(struct adrenogpu_ctx *, const struct adrenogpu_vm_ops *, uint64_t va_lo, uint64_t va_hi);
/* Unmaps everything and frees the page tables. The caller has already stopped the GPU using this context. */
void adrenogpu_ctx_destroy(struct adrenogpu_ctx *);

int adrenogpu_ctx_map(struct adrenogpu_ctx *, const struct adrenogpu_bo *, uint64_t va, unsigned prot);
/* Unmap the buffer object mapped at exactly `va`. */
int adrenogpu_ctx_unmap(struct adrenogpu_ctx *, uint64_t va);
/* The mapping that contains all of [va, va + bytes) with at least `prot`, or NULL. */
const struct adrenogpu_mapping *adrenogpu_ctx_find(const struct adrenogpu_ctx *, uint64_t va, uint64_t bytes, unsigned prot);

/* Fences: 32-bit, wrap-safe, strictly increasing per context. */
uint32_t adrenogpu_ctx_new_fence(struct adrenogpu_ctx *);
void adrenogpu_ctx_retire(struct adrenogpu_ctx *, uint32_t fence); /* fences retire in order */
int adrenogpu_ctx_fence_done(const struct adrenogpu_ctx *, uint32_t fence);
#endif
