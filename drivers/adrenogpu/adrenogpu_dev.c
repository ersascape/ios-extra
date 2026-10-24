/* SPDX-License-Identifier: MIT */
#include "adrenogpu_dev.h"

#define HANDLE_SLOT(h) ((unsigned)((h) & 0xffffu))
#define HANDLE_GEN(h) ((uint16_t)((h) >> 16))
#define MAKE_HANDLE(gen, slot) (((uint32_t)(gen) << 16) | ((uint32_t)(slot) + 1u))
#define CLIENT_SLOT(id) ((unsigned)((id) & 0xffu))
#define MAX_VA (1ull << ADRENOGPU_VM_VA_BITS)
#define MAX_JOB_DWORDS 0xfffffu

int
adrenogpu_arg32(uint64_t v, uint32_t *out)
{
	if (v > 0xffffffffull) return ADRENOGPU_DEV_EINVAL;
	*out = (uint32_t)v;
	return ADRENOGPU_DEV_OK;
}

void
adrenogpu_dev_default_config(struct adrenogpu_dev_config *cfg, uint64_t timeout)
{
	cfg->va_lo = 0x100000ull;
	cfg->va_hi = 1ull << 47;
	cfg->max_ctx_per_client = 8;
	cfg->max_bo_per_client = 256;
	cfg->max_bo_bytes = 256ull << 20;
	cfg->max_client_bytes = 1ull << 30;
	cfg->close_timeout = timeout;
}

static uint64_t
sat_add(uint64_t a, uint64_t b)
{
	return a + b < a ? ~0ull : a + b;
}

/* The page-table core calls these with the device as context. */
static struct adrenogpu_vm_table
vm_alloc_table(void *c)
{
	struct adrenogpu_dev *dev = c;
	return dev->mem.alloc_table(dev->mem.context);
}

static void
vm_free_table(void *c, struct adrenogpu_vm_table t)
{
	struct adrenogpu_dev *dev = c;
	dev->mem.free_table(dev->mem.context, t);
}

static void
vm_publish(void *c, void *cpu, size_t bytes)
{
	struct adrenogpu_dev *dev = c;
	if (dev->mem.publish) dev->mem.publish(dev->mem.context, cpu, bytes);
}

static void
vm_invalidate(void *c, uint64_t va, uint64_t bytes)
{
	struct adrenogpu_dev *dev = c;
	dev->hw.tlb_invalidate(dev->hw.context, va, bytes);
}

int
adrenogpu_dev_init(struct adrenogpu_dev *dev, const struct adrenogpu_mem_ops *mem, const struct adrenogpu_hw_ops *hw,
    const struct adrenogpu_hw_info *info, const struct adrenogpu_dev_config *cfg)
{
	if (!dev || !mem || !hw || !info || !cfg) return ADRENOGPU_DEV_EINVAL;
	if (!mem->alloc || !mem->free || !mem->alloc_table || !mem->free_table || !mem->bo_alloc || !mem->bo_free ||
	    !hw->read_rptr || !hw->read_fence || !hw->write_wptr || !hw->tlb_invalidate || !hw->activate || !hw->reset)
		return ADRENOGPU_DEV_EINVAL;
	if ((cfg->va_lo & (ADRENOGPU_PAGE_SIZE - 1)) || (cfg->va_hi & (ADRENOGPU_PAGE_SIZE - 1)) ||
	    cfg->va_lo >= cfg->va_hi || cfg->va_hi > MAX_VA || !cfg->max_ctx_per_client || !cfg->max_bo_per_client ||
	    !cfg->max_bo_bytes || cfg->max_client_bytes < cfg->max_bo_bytes)
		return ADRENOGPU_DEV_EINVAL;
	if (info->fence_map_pa) {
		uint64_t page = info->fence_va & ~(uint64_t)(ADRENOGPU_PAGE_SIZE - 1);
		if ((info->fence_map_pa & (ADRENOGPU_PAGE_SIZE - 1)) || (info->fence_map_pa >> ADRENOGPU_VM_VA_BITS) ||
		    info->fence_map_prot & ~(unsigned)(ADRENOGPU_VM_WRITE | ADRENOGPU_VM_EXEC) ||
		    page >= MAX_VA || (page >= cfg->va_lo && page < cfg->va_hi))
			return ADRENOGPU_DEV_EINVAL;
	}
	dev->mem = *mem;
	dev->hw = *hw;
	dev->info = *info;
	dev->cfg = *cfg;
	if (dev->cfg.max_ctx_per_client > ADRENOGPU_DEV_MAX_CTX) dev->cfg.max_ctx_per_client = ADRENOGPU_DEV_MAX_CTX;
	if (dev->cfg.max_bo_per_client > ADRENOGPU_DEV_MAX_BO) dev->cfg.max_bo_per_client = ADRENOGPU_DEV_MAX_BO;
	dev->vmops.context = dev;
	dev->vmops.alloc_table = vm_alloc_table;
	dev->vmops.free_table = vm_free_table;
	dev->vmops.publish = vm_publish;
	dev->vmops.invalidate = vm_invalidate;
	if (adrenogpu_sched_init(&dev->sched, info->ring, info->ring_dwords, info->wptr, info->fence_va, info->timeout))
		return ADRENOGPU_DEV_EINVAL;
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_CLIENTS; i++) dev->clients[i].in_use = 0;
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_CTX; i++) {
		dev->ctxs[i].in_use = 0;
		dev->ctxs[i].gen = 0;
		dev->ctxs[i].ctx = NULL;
	}
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_BO; i++) {
		dev->bos[i].in_use = 0;
		dev->bos[i].gen = 0;
		dev->bos[i].pages = NULL;
		dev->bos[i].cookie = NULL;
		dev->bos[i].mapcount = 0;
	}
	dev->active = NULL;
	dev->next_client_gen = 0;
	dev->resets = 0;
	dev->wedged = 0;
	return ADRENOGPU_DEV_OK;
}

/* A job that has been written to the ring may still be read by the GPU. */
static int
ctx_busy(const struct adrenogpu_dev *dev, const struct adrenogpu_ctx *ctx)
{
	for (unsigned i = 0; i < dev->sched.count; i++)
		if (dev->sched.jobs[(dev->sched.head + i) % ADRENOGPU_SCHED_MAX_JOBS].ctx == ctx) return 1;
	return 0;
}

static int
client_busy(const struct adrenogpu_dev *dev, uint32_t client)
{
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_CTX; i++)
		if (dev->ctxs[i].in_use && dev->ctxs[i].owner == client && ctx_busy(dev, dev->ctxs[i].ctx)) return 1;
	return 0;
}

/* Reset the GPU and fail what was in flight. If the hardware cannot be reset the jobs stay (the GPU may still read
 * their memory) and the device is marked wedged: nothing that in-flight work can reach is ever released. */
static int
reset_gpu(struct adrenogpu_dev *dev)
{
	uint32_t wptr = dev->sched.rb.wptr;
	if (dev->hw.reset(dev->hw.context, &wptr)) {
		dev->wedged = 1;
		return ADRENOGPU_DEV_EHW;
	}
	(void)adrenogpu_sched_reset(&dev->sched, wptr);
	dev->active = NULL; /* the context bank was reset */
	dev->resets++;
	return ADRENOGPU_DEV_OK;
}

int
adrenogpu_dev_poll(struct adrenogpu_dev *dev, uint64_t now)
{
	if (!dev->sched.count) return 0;
	if (adrenogpu_sched_poll(&dev->sched, now, dev->hw.read_fence(dev->hw.context)) == ADRENOGPU_SCHED_HUNG)
		return reset_gpu(dev) == ADRENOGPU_DEV_OK;
	return 0;
}

static struct adrenogpu_dev_client *
client_of(struct adrenogpu_dev *dev, uint32_t id)
{
	unsigned slot = CLIENT_SLOT(id);
	if (!slot || slot > ADRENOGPU_DEV_MAX_CLIENTS) return NULL;
	struct adrenogpu_dev_client *c = &dev->clients[slot - 1u];
	return c->in_use && ((c->gen << 8) | slot) == id ? c : NULL;
}

/* An open (not closing) client, for every call except close. */
static int
client_open_for_use(struct adrenogpu_dev *dev, uint32_t id, struct adrenogpu_dev_client **out)
{
	struct adrenogpu_dev_client *c = client_of(dev, id);
	if (!c) return ADRENOGPU_DEV_ENOENT;
	if (c->closing) return ADRENOGPU_DEV_ECLOSED;
	*out = c;
	return ADRENOGPU_DEV_OK;
}

static int
lookup_ctx(struct adrenogpu_dev *dev, uint32_t client, uint32_t handle, struct adrenogpu_dev_ctx **out)
{
	unsigned slot = HANDLE_SLOT(handle);
	if (!slot || slot > ADRENOGPU_DEV_MAX_CTX) return ADRENOGPU_DEV_ENOENT;
	struct adrenogpu_dev_ctx *c = &dev->ctxs[slot - 1u];
	if (!c->in_use || c->gen != HANDLE_GEN(handle)) return ADRENOGPU_DEV_ENOENT;
	if (c->owner != client) return ADRENOGPU_DEV_EPERM;
	*out = c;
	return ADRENOGPU_DEV_OK;
}

static int
lookup_bo(struct adrenogpu_dev *dev, uint32_t client, uint32_t handle, struct adrenogpu_dev_bo **out)
{
	unsigned slot = HANDLE_SLOT(handle);
	if (!slot || slot > ADRENOGPU_DEV_MAX_BO) return ADRENOGPU_DEV_ENOENT;
	struct adrenogpu_dev_bo *b = &dev->bos[slot - 1u];
	if (!b->in_use || b->gen != HANDLE_GEN(handle)) return ADRENOGPU_DEV_ENOENT;
	if (b->owner != client) return ADRENOGPU_DEV_EPERM;
	*out = b;
	return ADRENOGPU_DEV_OK;
}

static struct adrenogpu_dev_bo *
bo_of_mapping(const struct adrenogpu_mapping *m)
{
	return (struct adrenogpu_dev_bo *)(uintptr_t)m->bo; /* bo is the first member of adrenogpu_dev_bo */
}

int
adrenogpu_dev_client_open(struct adrenogpu_dev *dev, uint32_t *client)
{
	if (!dev || !client) return ADRENOGPU_DEV_EINVAL;
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_CLIENTS; i++) {
		struct adrenogpu_dev_client *c = &dev->clients[i];
		if (c->in_use) continue;
		dev->next_client_gen = (dev->next_client_gen + 1u) & 0xffffffu;
		if (!dev->next_client_gen) dev->next_client_gen = 1;
		c->in_use = 1;
		c->closing = 0;
		c->gen = dev->next_client_gen;
		c->close_deadline = 0;
		c->nctx = c->nbo = 0;
		c->bytes = 0;
		*client = (c->gen << 8) | (i + 1u);
		return ADRENOGPU_DEV_OK;
	}
	return ADRENOGPU_DEV_ENOSPC;
}

/* Unmap everything, drop the context from the hardware, free its tables. Caller has checked it is idle. */
static void
release_ctx(struct adrenogpu_dev *dev, struct adrenogpu_dev_ctx *dc)
{
	struct adrenogpu_ctx *ctx = dc->ctx;
	while (ctx->nmaps) {
		const struct adrenogpu_mapping *m = &ctx->maps[ctx->nmaps - 1u];
		struct adrenogpu_dev_bo *b = bo_of_mapping(m);
		uint64_t va = m->va;
		if (b->mapcount) b->mapcount--;
		(void)adrenogpu_ctx_unmap(ctx, va);
	}
	if (dev->active == dc) {
		(void)dev->hw.activate(dev->hw.context, 0); /* park the context bank before its tables go away */
		dev->active = NULL;
	}
	adrenogpu_ctx_destroy(ctx);
	dev->hw.tlb_invalidate(dev->hw.context, 0, MAX_VA);
	dev->mem.free(dev->mem.context, ctx, sizeof(*ctx));
	struct adrenogpu_dev_client *c = client_of(dev, dc->owner);
	if (c && c->nctx) c->nctx--;
	dc->ctx = NULL;
	dc->in_use = 0;
	dc->owner = 0;
	dc->gen++;
}

static void
release_bo(struct adrenogpu_dev *dev, struct adrenogpu_dev_bo *b)
{
	uint64_t bytes = (uint64_t)b->bo.npages * ADRENOGPU_PAGE_SIZE;
	dev->mem.bo_free(dev->mem.context, b->cookie);
	dev->mem.free(dev->mem.context, b->pages, (size_t)b->bo.npages * sizeof(uint64_t));
	struct adrenogpu_dev_client *c = client_of(dev, b->owner);
	if (c) {
		if (c->nbo) c->nbo--;
		c->bytes = c->bytes > bytes ? c->bytes - bytes : 0;
	}
	b->pages = NULL;
	b->cookie = NULL;
	b->bo.pages = NULL;
	b->bo.npages = 0;
	b->mapcount = 0;
	b->in_use = 0;
	b->owner = 0;
	b->gen++;
}

int
adrenogpu_dev_client_close(struct adrenogpu_dev *dev, uint32_t client, uint64_t now)
{
	struct adrenogpu_dev_client *c = client_of(dev, client);
	if (!c) return ADRENOGPU_DEV_ENOENT;
	if (!c->closing) {
		c->closing = 1;
		c->close_deadline = sat_add(now, dev->cfg.close_timeout);
	}
	(void)adrenogpu_dev_poll(dev, now);
	if (client_busy(dev, client)) {
		if (now < c->close_deadline) return ADRENOGPU_DEV_EBUSY;
		if (reset_gpu(dev)) return ADRENOGPU_DEV_EHW;
	}
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_CTX; i++)
		if (dev->ctxs[i].in_use && dev->ctxs[i].owner == client) release_ctx(dev, &dev->ctxs[i]);
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_BO; i++)
		if (dev->bos[i].in_use && dev->bos[i].owner == client) release_bo(dev, &dev->bos[i]);
	c->in_use = 0;
	c->closing = 0;
	return ADRENOGPU_DEV_OK;
}

void
adrenogpu_dev_destroy(struct adrenogpu_dev *dev)
{
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_CLIENTS; i++) {
		if (!dev->clients[i].in_use) continue;
		uint32_t id = (dev->clients[i].gen << 8) | (i + 1u);
		(void)adrenogpu_dev_client_close(dev, id, ~0ull);
	}
}

int
adrenogpu_dev_ctx_create(struct adrenogpu_dev *dev, uint32_t client, uint32_t flags, uint32_t *ctx_out,
    uint64_t *va_lo, uint64_t *va_hi)
{
	struct adrenogpu_dev_client *c;
	int rc = client_open_for_use(dev, client, &c);
	if (rc) return rc;
	if (!ctx_out || !va_lo || !va_hi || flags) return ADRENOGPU_DEV_EINVAL;
	if (c->nctx >= dev->cfg.max_ctx_per_client) return ADRENOGPU_DEV_ENOSPC;
	struct adrenogpu_dev_ctx *dc = NULL;
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_CTX && !dc; i++)
		if (!dev->ctxs[i].in_use) dc = &dev->ctxs[i];
	if (!dc) return ADRENOGPU_DEV_ENOSPC;
	struct adrenogpu_ctx *ctx = dev->mem.alloc(dev->mem.context, sizeof(*ctx));
	if (!ctx) return ADRENOGPU_DEV_ENOMEM;
	if (adrenogpu_ctx_init(ctx, &dev->vmops, dev->cfg.va_lo, dev->cfg.va_hi)) {
		dev->mem.free(dev->mem.context, ctx, sizeof(*ctx));
		return ADRENOGPU_DEV_ENOMEM;
	}
	if (dev->info.fence_map_pa &&
	    adrenogpu_vm_map(&ctx->vm, dev->info.fence_va & ~(uint64_t)(ADRENOGPU_PAGE_SIZE - 1), dev->info.fence_map_pa,
	        dev->info.fence_map_prot)) {
		adrenogpu_ctx_destroy(ctx);
		dev->mem.free(dev->mem.context, ctx, sizeof(*ctx));
		return ADRENOGPU_DEV_ENOMEM;
	}
	dc->ctx = ctx;
	dc->owner = client;
	dc->in_use = 1;
	c->nctx++;
	*ctx_out = MAKE_HANDLE(dc->gen, dc - dev->ctxs);
	*va_lo = dev->cfg.va_lo;
	*va_hi = dev->cfg.va_hi;
	return ADRENOGPU_DEV_OK;
}

int
adrenogpu_dev_ctx_destroy(struct adrenogpu_dev *dev, uint32_t client, uint32_t ctx, uint64_t now)
{
	struct adrenogpu_dev_client *c;
	struct adrenogpu_dev_ctx *dc;
	int rc = client_open_for_use(dev, client, &c);
	if (rc) return rc;
	rc = lookup_ctx(dev, client, ctx, &dc);
	if (rc) return rc;
	(void)adrenogpu_dev_poll(dev, now);
	if (ctx_busy(dev, dc->ctx)) return ADRENOGPU_DEV_EBUSY;
	release_ctx(dev, dc);
	return ADRENOGPU_DEV_OK;
}

int
adrenogpu_dev_bo_alloc(struct adrenogpu_dev *dev, uint32_t client, uint64_t size, uint32_t flags, uint32_t *bo,
    uint64_t *actual_size)
{
	struct adrenogpu_dev_client *c;
	int rc = client_open_for_use(dev, client, &c);
	if (rc) return rc;
	if (!bo || !actual_size || flags || !size || size > dev->cfg.max_bo_bytes) return ADRENOGPU_DEV_EINVAL;
	unsigned long npages = (unsigned long)((size + ADRENOGPU_PAGE_SIZE - 1u) / ADRENOGPU_PAGE_SIZE); /* size is bounded */
	uint64_t bytes = (uint64_t)npages * ADRENOGPU_PAGE_SIZE;
	if (c->nbo >= dev->cfg.max_bo_per_client || bytes > dev->cfg.max_client_bytes - c->bytes) return ADRENOGPU_DEV_ENOSPC;
	struct adrenogpu_dev_bo *b = NULL;
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_BO && !b; i++)
		if (!dev->bos[i].in_use) b = &dev->bos[i];
	if (!b) return ADRENOGPU_DEV_ENOSPC;
	uint64_t *pages = dev->mem.alloc(dev->mem.context, npages * sizeof(uint64_t));
	if (!pages) return ADRENOGPU_DEV_ENOMEM;
	void *cookie = NULL;
	if (dev->mem.bo_alloc(dev->mem.context, npages, pages, &cookie)) {
		dev->mem.free(dev->mem.context, pages, npages * sizeof(uint64_t));
		return ADRENOGPU_DEV_ENOMEM;
	}
	for (unsigned long i = 0; i < npages; i++) {
		if ((pages[i] & (ADRENOGPU_PAGE_SIZE - 1)) || (pages[i] >> ADRENOGPU_VM_VA_BITS)) { /* a broken allocator */
			dev->mem.bo_free(dev->mem.context, cookie);
			dev->mem.free(dev->mem.context, pages, npages * sizeof(uint64_t));
			return ADRENOGPU_DEV_ENOMEM;
		}
	}
	b->pages = pages;
	b->cookie = cookie;
	b->owner = client;
	b->mapcount = 0;
	b->in_use = 1;
	b->bo.pages = pages;
	b->bo.npages = npages;
	b->bo.id = MAKE_HANDLE(b->gen, b - dev->bos);
	c->nbo++;
	c->bytes += bytes;
	*bo = b->bo.id;
	*actual_size = bytes;
	return ADRENOGPU_DEV_OK;
}

int
adrenogpu_dev_bo_free(struct adrenogpu_dev *dev, uint32_t client, uint32_t bo)
{
	struct adrenogpu_dev_client *c;
	struct adrenogpu_dev_bo *b;
	int rc = client_open_for_use(dev, client, &c);
	if (rc) return rc;
	rc = lookup_bo(dev, client, bo, &b);
	if (rc) return rc;
	if (b->mapcount) return ADRENOGPU_DEV_EBUSY;
	release_bo(dev, b);
	return ADRENOGPU_DEV_OK;
}

void *
adrenogpu_dev_bo_cookie(struct adrenogpu_dev *dev, uint32_t client, uint32_t bo, uint64_t *bytes)
{
	struct adrenogpu_dev_client *c;
	struct adrenogpu_dev_bo *b;
	if (client_open_for_use(dev, client, &c) || lookup_bo(dev, client, bo, &b)) return NULL;
	if (bytes) *bytes = (uint64_t)b->bo.npages * ADRENOGPU_PAGE_SIZE;
	return b->cookie;
}

int
adrenogpu_dev_bo_map(struct adrenogpu_dev *dev, uint32_t client, uint32_t ctx, uint32_t bo, uint64_t va,
    unsigned prot, uint64_t now)
{
	struct adrenogpu_dev_client *c;
	struct adrenogpu_dev_ctx *dc;
	struct adrenogpu_dev_bo *b;
	int rc = client_open_for_use(dev, client, &c);
	if (rc) return rc;
	rc = lookup_ctx(dev, client, ctx, &dc);
	if (rc) return rc;
	rc = lookup_bo(dev, client, bo, &b);
	if (rc) return rc;
	(void)now;
	if (prot & ~(ADRENOGPU_USER_PROT_WRITE | ADRENOGPU_USER_PROT_EXEC)) return ADRENOGPU_DEV_EINVAL;
	unsigned vmprot = ((prot & ADRENOGPU_USER_PROT_WRITE) ? ADRENOGPU_VM_WRITE : 0) |
	    ((prot & ADRENOGPU_USER_PROT_EXEC) ? ADRENOGPU_VM_EXEC : 0);
	switch (adrenogpu_ctx_map(dc->ctx, &b->bo, va, vmprot)) {
	case ADRENOGPU_CTX_OK: break;
	case ADRENOGPU_CTX_EOVERLAP: return ADRENOGPU_DEV_EEXIST;
	case ADRENOGPU_CTX_EFULL: return ADRENOGPU_DEV_ENOSPC;
	case ADRENOGPU_CTX_EVM: return ADRENOGPU_DEV_ENOMEM;
	default: return ADRENOGPU_DEV_EINVAL;
	}
	b->mapcount++;
	return ADRENOGPU_DEV_OK;
}

int
adrenogpu_dev_bo_unmap(struct adrenogpu_dev *dev, uint32_t client, uint32_t ctx, uint64_t va, uint64_t now)
{
	struct adrenogpu_dev_client *c;
	struct adrenogpu_dev_ctx *dc;
	int rc = client_open_for_use(dev, client, &c);
	if (rc) return rc;
	rc = lookup_ctx(dev, client, ctx, &dc);
	if (rc) return rc;
	const struct adrenogpu_mapping *m = NULL;
	for (unsigned i = 0; i < dc->ctx->nmaps && !m; i++)
		if (dc->ctx->maps[i].va == va) m = &dc->ctx->maps[i];
	if (!m) return ADRENOGPU_DEV_ENOENT;
	(void)adrenogpu_dev_poll(dev, now);
	if (ctx_busy(dev, dc->ctx)) return ADRENOGPU_DEV_EBUSY; /* the GPU may still read what is mapped */
	struct adrenogpu_dev_bo *b = bo_of_mapping(m);
	if (adrenogpu_ctx_unmap(dc->ctx, va)) return ADRENOGPU_DEV_ENOENT;
	if (b->mapcount) b->mapcount--;
	return ADRENOGPU_DEV_OK;
}

int
adrenogpu_dev_submit(struct adrenogpu_dev *dev, uint32_t client, uint32_t ctx, uint64_t ib_va, uint32_t ib_dwords,
    uint32_t flags, uint64_t now, uint32_t *fence)
{
	struct adrenogpu_dev_client *c;
	struct adrenogpu_dev_ctx *dc;
	int rc = client_open_for_use(dev, client, &c);
	if (rc) return rc;
	rc = lookup_ctx(dev, client, ctx, &dc);
	if (rc) return rc;
	/* The A/B-test flags of the framing are not for user space. */
	if (!fence || flags || (ib_va & 3u) || !ib_dwords || ib_dwords > MAX_JOB_DWORDS) return ADRENOGPU_DEV_EINVAL;
	if (dev->wedged) return ADRENOGPU_DEV_EHW;
	(void)adrenogpu_dev_poll(dev, now);
	if (dev->wedged) return ADRENOGPU_DEV_EHW;
	if (!adrenogpu_ctx_find(dc->ctx, ib_va, 4ull * ib_dwords, 0)) return ADRENOGPU_DEV_ERANGE; /* before any hardware change */
	if (dev->active != dc) {
		if (dev->sched.count) return ADRENOGPU_DEV_EBUSY;
		if (dev->hw.activate(dev->hw.context, adrenogpu_vm_root(&dc->ctx->vm))) return ADRENOGPU_DEV_EHW;
		dev->active = dc;
	}
	if (dev->mem.bo_publish)
		for (unsigned i = 0; i < dc->ctx->nmaps; i++)
			dev->mem.bo_publish(dev->mem.context, bo_of_mapping(&dc->ctx->maps[i])->cookie);
	struct adrenogpu_submit job = { 0 };
	job.ib_va = ib_va;
	job.ib_dwords = ib_dwords;
	uint32_t wptr = 0, ctx_fence = 0;
	switch (adrenogpu_sched_submit(&dev->sched, dc->ctx, &job, dev->hw.read_rptr(dev->hw.context), now, &wptr, &ctx_fence)) {
	case ADRENOGPU_SCHED_OK: break;
	case ADRENOGPU_SCHED_EUNMAPPED: return ADRENOGPU_DEV_ERANGE;
	case ADRENOGPU_SCHED_EBUSY: return ADRENOGPU_DEV_EBUSY;
	default: return ADRENOGPU_DEV_EINVAL;
	}
	dev->hw.write_wptr(dev->hw.context, wptr);
	*fence = ctx_fence;
	return ADRENOGPU_DEV_OK;
}

int
adrenogpu_dev_fence_status(struct adrenogpu_dev *dev, uint32_t client, uint32_t ctx, uint32_t fence, uint64_t now,
    enum adrenogpu_fence_status *status)
{
	struct adrenogpu_dev_client *c;
	struct adrenogpu_dev_ctx *dc;
	int rc = client_open_for_use(dev, client, &c);
	if (rc) return rc;
	rc = lookup_ctx(dev, client, ctx, &dc);
	if (rc) return rc;
	if (!status || !fence || (int32_t)(dc->ctx->issued - fence) < 0) return ADRENOGPU_DEV_EINVAL; /* never issued */
	(void)adrenogpu_dev_poll(dev, now);
	if (!adrenogpu_ctx_fence_done(dc->ctx, fence)) *status = ADRENOGPU_FENCE_PENDING;
	else if (adrenogpu_ctx_fence_lost(dc->ctx, fence)) *status = ADRENOGPU_FENCE_LOST;
	else *status = ADRENOGPU_FENCE_SIGNALED;
	return ADRENOGPU_DEV_OK;
}
