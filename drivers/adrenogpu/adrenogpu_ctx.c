/* SPDX-License-Identifier: MIT */
#include "adrenogpu_ctx.h"

static uint64_t
bo_bytes(const struct adrenogpu_bo *bo)
{
	return (uint64_t)bo->npages * ADRENOGPU_PAGE_SIZE;
}

int
adrenogpu_ctx_init(struct adrenogpu_ctx *ctx, const struct adrenogpu_vm_ops *ops, uint64_t va_lo, uint64_t va_hi)
{
	if (!ctx || (va_lo & (ADRENOGPU_PAGE_SIZE - 1)) || (va_hi & (ADRENOGPU_PAGE_SIZE - 1)) || va_lo >= va_hi ||
	    va_hi > (1ull << ADRENOGPU_VM_VA_BITS))
		return ADRENOGPU_CTX_EINVAL;
	int rc = adrenogpu_vm_init(&ctx->vm, ops);
	if (rc) return ADRENOGPU_CTX_EVM;
	ctx->nmaps = 0;
	ctx->va_lo = va_lo;
	ctx->va_hi = va_hi;
	ctx->issued = ctx->retired = 0;
	return ADRENOGPU_CTX_OK;
}

void
adrenogpu_ctx_destroy(struct adrenogpu_ctx *ctx)
{
	if (!ctx) return;
	adrenogpu_vm_destroy(&ctx->vm);
	ctx->nmaps = 0;
}

int
adrenogpu_ctx_map(struct adrenogpu_ctx *ctx, const struct adrenogpu_bo *bo, uint64_t va, unsigned prot)
{
	if (!ctx || !bo || !bo->pages || !bo->npages || (va & (ADRENOGPU_PAGE_SIZE - 1)) || va < ctx->va_lo ||
	    va >= ctx->va_hi || bo_bytes(bo) > ctx->va_hi - va)
		return ADRENOGPU_CTX_EINVAL;
	if (ctx->nmaps == ADRENOGPU_CTX_MAX_MAPS) return ADRENOGPU_CTX_EFULL;
	for (unsigned i = 0; i < ctx->nmaps; i++) {
		const struct adrenogpu_mapping *m = &ctx->maps[i];
		if (va < m->va + bo_bytes(m->bo) && m->va < va + bo_bytes(bo)) return ADRENOGPU_CTX_EOVERLAP;
	}
	for (unsigned long i = 0; i < bo->npages; i++) {
		if (adrenogpu_vm_map(&ctx->vm, va + i * ADRENOGPU_PAGE_SIZE, bo->pages[i], prot)) {
			while (i--) (void)adrenogpu_vm_unmap(&ctx->vm, va + i * ADRENOGPU_PAGE_SIZE);
			return ADRENOGPU_CTX_EVM;
		}
	}
	ctx->maps[ctx->nmaps].va = va;
	ctx->maps[ctx->nmaps].bo = bo;
	ctx->maps[ctx->nmaps].prot = prot;
	ctx->nmaps++;
	return ADRENOGPU_CTX_OK;
}

int
adrenogpu_ctx_unmap(struct adrenogpu_ctx *ctx, uint64_t va)
{
	if (!ctx) return ADRENOGPU_CTX_EINVAL;
	for (unsigned i = 0; i < ctx->nmaps; i++) {
		if (ctx->maps[i].va != va) continue;
		const struct adrenogpu_bo *bo = ctx->maps[i].bo;
		for (unsigned long p = 0; p < bo->npages; p++) (void)adrenogpu_vm_unmap(&ctx->vm, va + p * ADRENOGPU_PAGE_SIZE);
		ctx->maps[i] = ctx->maps[--ctx->nmaps];
		return ADRENOGPU_CTX_OK;
	}
	return ADRENOGPU_CTX_ENOENT;
}

const struct adrenogpu_mapping *
adrenogpu_ctx_find(const struct adrenogpu_ctx *ctx, uint64_t va, uint64_t bytes, unsigned prot)
{
	if (!ctx || !bytes || va + bytes < va) return NULL;
	for (unsigned i = 0; i < ctx->nmaps; i++) {
		const struct adrenogpu_mapping *m = &ctx->maps[i];
		uint64_t size = bo_bytes(m->bo);
		if (va >= m->va && va - m->va <= size && bytes <= size - (va - m->va) && (m->prot & prot) == prot)
			return m;
	}
	return NULL;
}

uint32_t
adrenogpu_ctx_new_fence(struct adrenogpu_ctx *ctx)
{
	if (++ctx->issued == 0) ctx->issued = 1; /* 0 means "no fence" */
	return ctx->issued;
}

void
adrenogpu_ctx_retire(struct adrenogpu_ctx *ctx, uint32_t fence)
{
	if ((int32_t)(fence - ctx->retired) > 0 && (int32_t)(ctx->issued - fence) >= 0) ctx->retired = fence;
}

int
adrenogpu_ctx_fence_done(const struct adrenogpu_ctx *ctx, uint32_t fence)
{
	return fence != 0 && (int32_t)(ctx->retired - fence) >= 0;
}
