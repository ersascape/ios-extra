/* SPDX-License-Identifier: MIT */
#include "adrenogpu_dev.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- fake memory ---- */
static long live_tables, live_bos, live_meta;
static unsigned long bo_calls, fail_bo_after, fail_meta_after, meta_calls, tables_failing;
static uint64_t fake_pa = 0x80000000ull;

static void *
m_alloc(void *c, size_t bytes)
{
	(void)c;
	if (fail_meta_after && meta_calls++ >= fail_meta_after) return NULL;
	live_meta++;
	return calloc(1, bytes);
}
static void m_free(void *c, void *p, size_t bytes) { (void)c; (void)bytes; assert(p); live_meta--; free(p); }

static struct adrenogpu_vm_table
m_alloc_table(void *c)
{
	(void)c;
	struct adrenogpu_vm_table t = { 0, 0 };
	if (tables_failing) return t;
	t.cpu = aligned_alloc(4096, 4096);
	memset(t.cpu, 0, 4096);
	t.pa = (uint64_t)(uintptr_t)t.cpu;
	live_tables++;
	return t;
}
static void m_free_table(void *c, struct adrenogpu_vm_table t) { (void)c; free(t.cpu); live_tables--; }

static int
m_bo_alloc(void *c, unsigned long npages, uint64_t *pages, void **cookie)
{
	(void)c;
	if (fail_bo_after && bo_calls++ >= fail_bo_after) return -1;
	for (unsigned long i = 0; i < npages; i++) {
		pages[i] = fake_pa; /* scattered: every page is its own run */
		fake_pa += 0x3000;
	}
	*cookie = malloc(1);
	live_bos++;
	return 0;
}
static void m_bo_free(void *c, void *cookie) { (void)c; free(cookie); live_bos--; }
static const struct adrenogpu_mem_ops mem_ops = { 0, m_alloc, m_free, m_alloc_table, m_free_table, 0, m_bo_alloc, m_bo_free, 0 };

/* ---- fake hardware ---- */
static uint32_t ring[256];
static uint32_t rptr, fence_word, wptr_written;
static unsigned activations, resets, invalidates;
static uint64_t last_ttbr;
static int reset_fails, activate_fails, cp_stalled;

static uint32_t h_rptr(void *c) { (void)c; return rptr; }
static uint32_t h_fence(void *c) { (void)c; return fence_word; }
static void h_wptr(void *c, uint32_t w) { (void)c; wptr_written = w; if (!cp_stalled) rptr = w; /* the CP consumes at once unless stalled */ }
static void h_inval(void *c, uint64_t va, uint64_t n) { (void)c; (void)va; (void)n; invalidates++; }
static int h_activate(void *c, uint64_t ttbr) { (void)c; if (activate_fails) return -1; last_ttbr = ttbr; activations++; return 0; }
static int
h_reset(void *c, uint32_t *w)
{
	(void)c;
	if (reset_fails) return -1;
	resets++;
	*w = 0;
	rptr = 0;
	return 0;
}
static const struct adrenogpu_hw_ops hw_ops = { 0, h_rptr, h_fence, h_wptr, h_inval, h_activate, h_reset };

#define FENCE_VA 0xffffff0000001000ull
#define TIMEOUT 1000u
#define CLOSE_TIMEOUT 5000u
#define VA_LO 0x100000ull
#define VA_HI 0x100000000ull

static struct adrenogpu_dev dev;

static void
setup(void)
{
	assert(live_tables == 0 && live_bos == 0 && live_meta == 0);
	memset(ring, 0, sizeof(ring));
	rptr = fence_word = wptr_written = 0;
	activations = resets = invalidates = 0;
	last_ttbr = 0;
	reset_fails = activate_fails = cp_stalled = 0;
	fail_bo_after = fail_meta_after = meta_calls = bo_calls = tables_failing = 0;
	struct adrenogpu_hw_info info = { ring, 256, 0, FENCE_VA, 0, 0, TIMEOUT };
	struct adrenogpu_dev_config cfg;
	adrenogpu_dev_default_config(&cfg, CLOSE_TIMEOUT);
	cfg.va_lo = VA_LO;
	cfg.va_hi = VA_HI;
	memset(&dev, 0, sizeof(dev));
	assert(adrenogpu_dev_init(&dev, &mem_ops, &hw_ops, &info, &cfg) == 0);
}

static void
teardown(void)
{
	adrenogpu_dev_destroy(&dev);
	assert(live_tables == 0 && live_bos == 0 && live_meta == 0);
}

/* a client with one context and one mapped 16 KiB buffer at 0x10000000 */
struct env { uint32_t client, ctx, bo; };

static struct env
make_env(void)
{
	struct env e;
	uint64_t lo, hi, size;
	assert(adrenogpu_dev_client_open(&dev, &e.client) == 0);
	assert(adrenogpu_dev_ctx_create(&dev, e.client, 0, &e.ctx, &lo, &hi) == 0 && lo == VA_LO && hi == VA_HI);
	assert(adrenogpu_dev_bo_alloc(&dev, e.client, 16384, 0, &e.bo, &size) == 0 && size == 16384);
	assert(adrenogpu_dev_bo_map(&dev, e.client, e.ctx, e.bo, 0x10000000ull, ADRENOGPU_USER_PROT_WRITE, 0) == 0);
	return e;
}

static void
test_validation(void)
{
	setup();
	uint32_t v32;
	assert(adrenogpu_arg32(0xffffffffull, &v32) == 0 && v32 == 0xffffffffu);
	assert(adrenogpu_arg32(0x100000000ull, &v32) == ADRENOGPU_DEV_EINVAL); /* would alias handle 0 if truncated */
	assert(adrenogpu_arg32(~0ull, &v32) == ADRENOGPU_DEV_EINVAL);

	struct env e = make_env();
	uint64_t lo, hi, size;
	uint32_t h, fence;
	assert(adrenogpu_dev_ctx_create(&dev, e.client, 1, &h, &lo, &hi) == ADRENOGPU_DEV_EINVAL);   /* flags are reserved */
	assert(adrenogpu_dev_ctx_create(&dev, 0xdeadbeef, 0, &h, &lo, &hi) == ADRENOGPU_DEV_ENOENT); /* no such client */
	assert(adrenogpu_dev_ctx_create(&dev, 0, 0, &h, &lo, &hi) == ADRENOGPU_DEV_ENOENT);

	assert(adrenogpu_dev_bo_alloc(&dev, e.client, 0, 0, &h, &size) == ADRENOGPU_DEV_EINVAL);
	assert(adrenogpu_dev_bo_alloc(&dev, e.client, 1, 1, &h, &size) == ADRENOGPU_DEV_EINVAL);        /* flags */
	assert(adrenogpu_dev_bo_alloc(&dev, e.client, (256ull << 20) + 1, 0, &h, &size) == ADRENOGPU_DEV_EINVAL);
	assert(adrenogpu_dev_bo_alloc(&dev, e.client, ~0ull, 0, &h, &size) == ADRENOGPU_DEV_EINVAL);    /* round-up overflow */
	assert(adrenogpu_dev_bo_alloc(&dev, e.client, ~0ull - 4095, 0, &h, &size) == ADRENOGPU_DEV_EINVAL);
	assert(adrenogpu_dev_bo_alloc(&dev, e.client, 1, 0, &h, &size) == 0 && size == 4096);           /* rounded up */
	uint32_t small = h;
	assert(adrenogpu_dev_bo_alloc(&dev, e.client, 256ull << 20, 0, &h, &size) == 0 && size == 256ull << 20);
	assert(adrenogpu_dev_bo_free(&dev, e.client, h) == 0);

	uint64_t va = 0x20000000ull;
	assert(adrenogpu_dev_bo_map(&dev, e.client, e.ctx, small, va + 1, 0, 0) == ADRENOGPU_DEV_EINVAL);          /* unaligned */
	assert(adrenogpu_dev_bo_map(&dev, e.client, e.ctx, small, VA_LO - 4096, 0, 0) == ADRENOGPU_DEV_EINVAL);   /* below range */
	assert(adrenogpu_dev_bo_map(&dev, e.client, e.ctx, small, VA_HI, 0, 0) == ADRENOGPU_DEV_EINVAL);          /* at the end */
	assert(adrenogpu_dev_bo_map(&dev, e.client, e.ctx, small, VA_HI - 4096, 0, 0) == 0);                       /* last page fits */
	assert(adrenogpu_dev_bo_map(&dev, e.client, e.ctx, small, ~0ull & ~4095ull, 0, 0) == ADRENOGPU_DEV_EINVAL);
	assert(adrenogpu_dev_bo_map(&dev, e.client, e.ctx, small, va, 4, 0) == ADRENOGPU_DEV_EINVAL);              /* unknown prot bit */
	assert(adrenogpu_dev_bo_map(&dev, e.client, e.ctx, small, va, ~0u, 0) == ADRENOGPU_DEV_EINVAL);
	assert(adrenogpu_dev_bo_map(&dev, e.client, e.ctx, small, 0x10001000ull, 0, 0) == ADRENOGPU_DEV_EEXIST);  /* overlaps e.bo */
	assert(adrenogpu_dev_bo_map(&dev, e.client, e.ctx, small, va, 0, 0) == 0);
	assert(adrenogpu_dev_bo_free(&dev, e.client, small) == ADRENOGPU_DEV_EBUSY);                               /* still mapped */
	assert(adrenogpu_dev_bo_unmap(&dev, e.client, e.ctx, va + 4096, 0) == ADRENOGPU_DEV_ENOENT);             /* not a mapping start */
	assert(adrenogpu_dev_bo_unmap(&dev, e.client, e.ctx, va, 0) == 0);
	assert(adrenogpu_dev_bo_unmap(&dev, e.client, e.ctx, va, 0) == ADRENOGPU_DEV_ENOENT);

	uint64_t ib = 0x10000000ull;
	assert(adrenogpu_dev_submit(&dev, e.client, e.ctx, ib + 2, 4, 0, 0, &fence) == ADRENOGPU_DEV_EINVAL);   /* unaligned IB */
	assert(adrenogpu_dev_submit(&dev, e.client, e.ctx, ib, 0, 0, 0, &fence) == ADRENOGPU_DEV_EINVAL);       /* empty */
	assert(adrenogpu_dev_submit(&dev, e.client, e.ctx, ib, 0x100000, 0, 0, &fence) == ADRENOGPU_DEV_EINVAL); /* over the PM4 limit */
	assert(adrenogpu_dev_submit(&dev, e.client, e.ctx, ib, 4, 1, 0, &fence) == ADRENOGPU_DEV_EINVAL);        /* A/B flags */
	assert(adrenogpu_dev_submit(&dev, e.client, e.ctx, ib, 4097, 0, 0, &fence) == ADRENOGPU_DEV_ERANGE);     /* runs past the BO */
	assert(adrenogpu_dev_submit(&dev, e.client, e.ctx, 0x30000000ull, 4, 0, 0, &fence) == ADRENOGPU_DEV_ERANGE); /* unmapped */
	assert(adrenogpu_dev_submit(&dev, e.client, e.ctx, ~0ull - 3, 4, 0, 0, &fence) == ADRENOGPU_DEV_ERANGE);   /* wraps */
	assert(adrenogpu_dev_submit(&dev, e.client, e.ctx, ib, 4, 0, 0, NULL) == ADRENOGPU_DEV_EINVAL);
	assert(dev.sched.count == 0 && wptr_written == 0 && activations == 0); /* refused submits touched nothing */
	assert(adrenogpu_dev_submit(&dev, e.client, e.ctx, ib, 4096, 0, 0, &fence) == 0 && fence == 1);

	enum adrenogpu_fence_status st;
	assert(adrenogpu_dev_fence_status(&dev, e.client, e.ctx, 0, 0, &st) == ADRENOGPU_DEV_EINVAL);
	assert(adrenogpu_dev_fence_status(&dev, e.client, e.ctx, 2, 0, &st) == ADRENOGPU_DEV_EINVAL);   /* never issued */
	assert(adrenogpu_dev_fence_status(&dev, e.client, e.ctx, 0x80000001u, 0, &st) == ADRENOGPU_DEV_EINVAL);
	assert(adrenogpu_dev_fence_status(&dev, e.client, e.ctx, 1, 0, &st) == 0 && st == ADRENOGPU_FENCE_PENDING);
	fence_word = dev.sched.next_seq;
	assert(adrenogpu_dev_fence_status(&dev, e.client, e.ctx, 1, 1, &st) == 0 && st == ADRENOGPU_FENCE_SIGNALED);
	printf("PASS: every user value is validated and refused submits leave the ring and hardware untouched\n");
	teardown();
}

static void
test_ownership(void)
{
	setup();
	struct env a = make_env(), b;
	uint32_t bctx, bbo, fence, tmp;
	uint64_t lo, hi, size;
	assert(adrenogpu_dev_client_open(&dev, &b.client) == 0);
	assert(adrenogpu_dev_ctx_create(&dev, b.client, 0, &bctx, &lo, &hi) == 0);
	assert(adrenogpu_dev_bo_alloc(&dev, b.client, 4096, 0, &bbo, &size) == 0);
	assert(a.client != b.client && a.ctx != bctx && a.bo != bbo);

	/* B names A's objects: refused with EPERM, and A's state is unchanged. */
	assert(adrenogpu_dev_submit(&dev, b.client, a.ctx, 0x10000000ull, 4, 0, 0, &fence) == ADRENOGPU_DEV_EPERM);
	assert(adrenogpu_dev_ctx_destroy(&dev, b.client, a.ctx, 0) == ADRENOGPU_DEV_EPERM);
	assert(adrenogpu_dev_bo_free(&dev, b.client, a.bo) == ADRENOGPU_DEV_EPERM);
	assert(adrenogpu_dev_bo_map(&dev, b.client, a.ctx, bbo, 0x40000000ull, 0, 0) == ADRENOGPU_DEV_EPERM);  /* A's context */
	assert(adrenogpu_dev_bo_map(&dev, b.client, bctx, a.bo, 0x40000000ull, 0, 0) == ADRENOGPU_DEV_EPERM);  /* A's buffer */
	assert(adrenogpu_dev_bo_unmap(&dev, b.client, a.ctx, 0x10000000ull, 0) == ADRENOGPU_DEV_EPERM);
	enum adrenogpu_fence_status st;
	assert(adrenogpu_dev_fence_status(&dev, b.client, a.ctx, 1, 0, &st) == ADRENOGPU_DEV_EPERM);
	assert(adrenogpu_dev_bo_cookie(&dev, b.client, a.bo, NULL) == NULL);
	assert(adrenogpu_dev_bo_cookie(&dev, a.client, a.bo, &size) != NULL && size == 16384);
	assert(dev.sched.count == 0 && dev.bos[0].mapcount == 1 && dev.ctxs[0].ctx->nmaps == 1);

	/* Handles that never existed or are malformed. */
	assert(adrenogpu_dev_ctx_destroy(&dev, a.client, 0, 0) == ADRENOGPU_DEV_ENOENT);
	assert(adrenogpu_dev_ctx_destroy(&dev, a.client, 0xffffffffu, 0) == ADRENOGPU_DEV_ENOENT);
	assert(adrenogpu_dev_ctx_destroy(&dev, a.client, 0x10000u | 99u, 0) == ADRENOGPU_DEV_ENOENT);
	assert(adrenogpu_dev_bo_free(&dev, a.client, 0xffff) == ADRENOGPU_DEV_ENOENT);
	assert(adrenogpu_dev_bo_free(&dev, a.client, a.bo ^ 0x10000u) == ADRENOGPU_DEV_ENOENT); /* wrong generation */

	/* A freed handle is stale even after its slot is reused, for the old and the new owner. */
	uint32_t old_bo = bbo;
	assert(adrenogpu_dev_bo_free(&dev, b.client, bbo) == 0);
	assert(adrenogpu_dev_bo_free(&dev, b.client, old_bo) == ADRENOGPU_DEV_ENOENT);
	assert(adrenogpu_dev_bo_alloc(&dev, a.client, 4096, 0, &tmp, &size) == 0); /* may reuse the slot */
	assert(tmp != old_bo);
	assert(adrenogpu_dev_bo_free(&dev, b.client, old_bo) == ADRENOGPU_DEV_ENOENT);
	assert(adrenogpu_dev_bo_free(&dev, b.client, tmp) == ADRENOGPU_DEV_EPERM);

	/* A client id is stale too once the client is gone: a new client in the same slot is a different client. */
	uint32_t old_client = b.client;
	assert(adrenogpu_dev_client_close(&dev, b.client, 0) == 0);
	assert(adrenogpu_dev_ctx_create(&dev, old_client, 0, &tmp, &lo, &hi) == ADRENOGPU_DEV_ENOENT);
	uint32_t c2;
	assert(adrenogpu_dev_client_open(&dev, &c2) == 0 && c2 != old_client);
	assert(adrenogpu_dev_ctx_destroy(&dev, c2, bctx, 0) == ADRENOGPU_DEV_ENOENT);
	assert(adrenogpu_dev_ctx_destroy(&dev, c2, a.ctx, 0) == ADRENOGPU_DEV_EPERM);
	printf("PASS: a client cannot use, free, map, unmap, submit to or wait on another client's handles\n");
	teardown();
}

static void
test_teardown(void)
{
	setup();
	struct env a = make_env();
	uint32_t f1, f2;
	assert(adrenogpu_dev_submit(&dev, a.client, a.ctx, 0x10000000ull, 8, 0, 100, &f1) == 0);
	assert(adrenogpu_dev_submit(&dev, a.client, a.ctx, 0x10000000ull, 8, 0, 110, &f2) == 0 && f2 == f1 + 1);
	assert(activations == 1 && last_ttbr == adrenogpu_vm_root(&dev.ctxs[0].ctx->vm));
	assert(wptr_written == dev.sched.rb.wptr && dev.sched.count == 2);

	/* Work in flight: unmap, destroy and close wait. */
	assert(adrenogpu_dev_bo_unmap(&dev, a.client, a.ctx, 0x10000000ull, 120) == ADRENOGPU_DEV_EBUSY);
	assert(adrenogpu_dev_ctx_destroy(&dev, a.client, a.ctx, 120) == ADRENOGPU_DEV_EBUSY);
	assert(adrenogpu_dev_client_close(&dev, a.client, 200) == ADRENOGPU_DEV_EBUSY);
	uint32_t tmp, x;
	uint64_t lo, hi;
	assert(adrenogpu_dev_ctx_create(&dev, a.client, 0, &tmp, &lo, &hi) == ADRENOGPU_DEV_ECLOSED); /* closing refuses new work */
	assert(adrenogpu_dev_submit(&dev, a.client, a.ctx, 0x10000000ull, 8, 0, 210, &x) == ADRENOGPU_DEV_ECLOSED);
	assert(adrenogpu_dev_client_close(&dev, a.client, 300) == ADRENOGPU_DEV_EBUSY); /* inside the close timeout */
	assert(resets == 0 && live_bos == 1);

	/* The GPU finishes before the timeout: torn down without a reset. */
	fence_word = dev.sched.next_seq;
	assert(adrenogpu_dev_client_close(&dev, a.client, 400) == 0);
	assert(resets == 0 && live_tables == 0 && live_bos == 0 && dev.active == NULL);
	assert(last_ttbr == 0 && "the context bank is parked before its tables are freed");
	assert(adrenogpu_dev_client_close(&dev, a.client, 500) == ADRENOGPU_DEV_ENOENT);
	printf("PASS: a closing client waits for its in-flight jobs and is then torn down without a reset\n");

	/* The GPU never finishes and the close timeout (300) is shorter than the hang timeout: the close itself
	 * resets the GPU, which fails the job, and then everything is released. */
	dev.cfg.close_timeout = 300;
	struct env c = make_env(), other;
	assert(adrenogpu_dev_submit(&dev, c.client, c.ctx, 0x10000000ull, 8, 0, 1000, &f1) == 0);
	assert(adrenogpu_dev_client_close(&dev, c.client, 1100) == ADRENOGPU_DEV_EBUSY); /* deadline 1400 */
	assert(adrenogpu_dev_client_close(&dev, c.client, 1399) == ADRENOGPU_DEV_EBUSY && resets == 0);
	assert(adrenogpu_dev_client_close(&dev, c.client, 1400) == 0);
	assert(resets == 1 && live_tables == 0 && live_bos == 0 && dev.sched.count == 0 && dev.sched.failed == 1);
	dev.cfg.close_timeout = CLOSE_TIMEOUT;
	printf("PASS: a client whose job never retires is torn down after a reset fails the job\n");

	/* A reset caused by one client's close fails the other client's job too and the survivor sees LOST. */
	other = make_env();
	uint32_t g;
	assert(adrenogpu_dev_submit(&dev, other.client, other.ctx, 0x10000000ull, 8, 0, 2000, &g) == 0);
	struct env victim = make_env();
	enum adrenogpu_fence_status st;
	assert(adrenogpu_dev_client_close(&dev, victim.client, 2000) == 0); /* idle client: nothing to wait for */
	assert(adrenogpu_dev_poll(&dev, 2000 + TIMEOUT) == 1 && resets == 2); /* the hung job is reset */
	assert(adrenogpu_dev_fence_status(&dev, other.client, other.ctx, g, 4000, &st) == 0 && st == ADRENOGPU_FENCE_LOST);
	assert(dev.active == NULL);
	printf("PASS: a hang resets the GPU, fails the in-flight job and its fence reports LOST\n");

	/* A client that dies with several contexts and buffers frees them all. */
	uint32_t cl, ctxs[3], bos[5];
	assert(adrenogpu_dev_client_open(&dev, &cl) == 0);
	uint64_t size;
	for (int i = 0; i < 3; i++) assert(adrenogpu_dev_ctx_create(&dev, cl, 0, &ctxs[i], &lo, &hi) == 0);
	for (int i = 0; i < 5; i++) assert(adrenogpu_dev_bo_alloc(&dev, cl, 8192, 0, &bos[i], &size) == 0);
	assert(adrenogpu_dev_bo_map(&dev, cl, ctxs[0], bos[0], 0x1000000ull, 0, 0) == 0);
	assert(adrenogpu_dev_bo_map(&dev, cl, ctxs[1], bos[0], 0x1000000ull, 0, 0) == 0);
	assert(adrenogpu_dev_client_close(&dev, cl, 9000) == 0);
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_BO; i++) assert(!dev.bos[i].in_use || dev.bos[i].owner != cl);
	printf("PASS: closing releases every context, mapping and buffer of the client\n");

	/* If the hardware cannot be reset, nothing the GPU might still read is freed. */
	uint32_t cw = other.client;
	assert(adrenogpu_dev_submit(&dev, cw, other.ctx, 0x10000000ull, 8, 0, 20000, &g) == 0);
	reset_fails = 1;
	long tables_before = live_tables, bos_before = live_bos;
	assert(adrenogpu_dev_client_close(&dev, cw, 22000) == ADRENOGPU_DEV_EBUSY); /* the hang poll tries a reset: fails */
	assert(dev.wedged);
	assert(adrenogpu_dev_client_close(&dev, cw, 22000 + CLOSE_TIMEOUT) == ADRENOGPU_DEV_EHW);
	assert(dev.wedged && live_tables == tables_before && live_bos == bos_before);
	assert(adrenogpu_dev_submit(&dev, cw, other.ctx, 0x10000000ull, 8, 0, 30000, &g) == ADRENOGPU_DEV_ECLOSED);
	reset_fails = 0;
	teardown();
	printf("PASS: a failed GPU reset leaves in-flight memory allocated\n");
}

static void
test_exhaustion(void)
{
	setup();
	uint32_t cl, h, ctxs[ADRENOGPU_DEV_MAX_CTX + 1];
	uint64_t lo, hi, size;
	assert(adrenogpu_dev_client_open(&dev, &cl) == 0);

	/* Per-client context quota, then the device pool across clients. */
	for (unsigned i = 0; i < 8; i++) assert(adrenogpu_dev_ctx_create(&dev, cl, 0, &ctxs[i], &lo, &hi) == 0);
	assert(adrenogpu_dev_ctx_create(&dev, cl, 0, &h, &lo, &hi) == ADRENOGPU_DEV_ENOSPC);
	uint32_t others[4];
	unsigned total = 8;
	for (unsigned k = 0; k < 4; k++) {
		assert(adrenogpu_dev_client_open(&dev, &others[k]) == 0);
		for (unsigned i = 0; i < 8; i++) {
			int rc = adrenogpu_dev_ctx_create(&dev, others[k], 0, &h, &lo, &hi);
			if (total < ADRENOGPU_DEV_MAX_CTX) { assert(rc == 0); total++; }
			else assert(rc == ADRENOGPU_DEV_ENOSPC);
		}
	}
	assert(total == ADRENOGPU_DEV_MAX_CTX);
	/* A destroyed handle goes stale, its slot is reusable with a new generation. */
	assert(adrenogpu_dev_ctx_destroy(&dev, cl, ctxs[3], 0) == 0);
	assert(adrenogpu_dev_ctx_destroy(&dev, cl, ctxs[3], 0) == ADRENOGPU_DEV_ENOENT);
	assert(adrenogpu_dev_ctx_create(&dev, cl, 0, &h, &lo, &hi) == 0 && h != ctxs[3] && (h & 0xffff) == (ctxs[3] & 0xffff));
	for (unsigned k = 0; k < 4; k++) assert(adrenogpu_dev_client_close(&dev, others[k], 0) == 0);

	/* Per-client buffer count and byte quotas. */
	uint32_t bos[ADRENOGPU_DEV_MAX_BO];
	unsigned n = 0;
	while (adrenogpu_dev_bo_alloc(&dev, cl, 4096, 0, &bos[n], &size) == 0) n++;
	assert(n == 256 && adrenogpu_dev_bo_alloc(&dev, cl, 4096, 0, &h, &size) == ADRENOGPU_DEV_ENOSPC);
	for (unsigned i = 0; i < n; i++) assert(adrenogpu_dev_bo_free(&dev, cl, bos[i]) == 0);
	assert(adrenogpu_dev_bo_alloc(&dev, cl, 256ull << 20, 0, &bos[0], &size) == 0);
	assert(adrenogpu_dev_bo_alloc(&dev, cl, 256ull << 20, 0, &bos[1], &size) == 0);
	assert(adrenogpu_dev_bo_alloc(&dev, cl, 256ull << 20, 0, &bos[2], &size) == 0);
	assert(adrenogpu_dev_bo_alloc(&dev, cl, 256ull << 20, 0, &bos[3], &size) == 0);
	assert(adrenogpu_dev_bo_alloc(&dev, cl, 4096, 0, &h, &size) == ADRENOGPU_DEV_ENOSPC); /* 1 GiB used */
	assert(adrenogpu_dev_bo_free(&dev, cl, bos[0]) == 0);
	assert(adrenogpu_dev_bo_alloc(&dev, cl, 4096, 0, &h, &size) == 0);                      /* quota is released on free */
	assert(adrenogpu_dev_bo_free(&dev, cl, h) == 0);
	for (unsigned i = 1; i < 4; i++) assert(adrenogpu_dev_bo_free(&dev, cl, bos[i]) == 0);

	/* The device's buffer pool, with quotas lifted far enough to reach it. */
	assert(adrenogpu_dev_client_close(&dev, cl, 0) == 0);
	teardown();
	setup();
	dev.cfg.max_bo_per_client = ADRENOGPU_DEV_MAX_BO;
	assert(adrenogpu_dev_client_open(&dev, &cl) == 0);
	uint32_t cl2;
	assert(adrenogpu_dev_client_open(&dev, &cl2) == 0);
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_BO; i++) assert(adrenogpu_dev_bo_alloc(&dev, cl, 4096, 0, &bos[i], &size) == 0);
	assert(adrenogpu_dev_bo_alloc(&dev, cl2, 4096, 0, &h, &size) == ADRENOGPU_DEV_ENOSPC);
	assert(adrenogpu_dev_bo_free(&dev, cl, bos[500]) == 0);
	assert(adrenogpu_dev_bo_alloc(&dev, cl2, 4096, 0, &h, &size) == 0 && h != bos[500]);
	assert(adrenogpu_dev_bo_free(&dev, cl, bos[500]) == ADRENOGPU_DEV_ENOENT); /* the old handle does not reach cl2's buffer */
	assert(adrenogpu_dev_bo_free(&dev, cl, h) == ADRENOGPU_DEV_EPERM);
	teardown();

	/* The client table, and an id stays unique after reuse. */
	setup();
	uint32_t ids[ADRENOGPU_DEV_MAX_CLIENTS + 1];
	for (unsigned i = 0; i < ADRENOGPU_DEV_MAX_CLIENTS; i++) assert(adrenogpu_dev_client_open(&dev, &ids[i]) == 0);
	assert(adrenogpu_dev_client_open(&dev, &ids[ADRENOGPU_DEV_MAX_CLIENTS]) == ADRENOGPU_DEV_ENOSPC);
	assert(adrenogpu_dev_client_close(&dev, ids[5], 0) == 0);
	uint32_t again;
	assert(adrenogpu_dev_client_open(&dev, &again) == 0 && again != ids[5]);
	teardown();

	/* Allocator failures unwind completely. */
	setup();
	assert(adrenogpu_dev_client_open(&dev, &cl) == 0);
	fail_meta_after = 1;                                         /* the first allocation (the context) succeeds ... */
	meta_calls = 0;
	assert(adrenogpu_dev_ctx_create(&dev, cl, 0, &h, &lo, &hi) == 0);
	assert(adrenogpu_dev_bo_alloc(&dev, cl, 4096, 0, &bos[0], &size) == ADRENOGPU_DEV_ENOMEM); /* ... the pages array fails */
	fail_meta_after = 0;
	fail_bo_after = 1;
	bo_calls = 1;
	assert(adrenogpu_dev_bo_alloc(&dev, cl, 4096, 0, &bos[0], &size) == ADRENOGPU_DEV_ENOMEM);
	assert(live_bos == 0 && live_meta == 1 && dev.clients[0].nbo == 0 && dev.clients[0].bytes == 0);
	fail_bo_after = 0;
	tables_failing = 1;
	assert(adrenogpu_dev_ctx_create(&dev, cl, 0, &ctxs[0], &lo, &hi) == ADRENOGPU_DEV_ENOMEM);
	assert(live_meta == 1 && dev.clients[0].nctx == 1);
	tables_failing = 0;
	assert(adrenogpu_dev_bo_alloc(&dev, cl, 4096, 0, &bos[0], &size) == 0);
	assert(adrenogpu_dev_bo_map(&dev, cl, h, bos[0], 0x1000000ull, 0, 0) == 0);
	tables_failing = 1;
	assert(adrenogpu_dev_bo_map(&dev, cl, h, bos[0], 0x80000000ull, 0, 0) == ADRENOGPU_DEV_ENOMEM); /* needs new tables */
	assert(dev.bos[0].mapcount == 1);
	tables_failing = 0;
	teardown();
	printf("PASS: pools, quotas, client slots and allocator failures are handled and handles do not alias\n");
}

static void
test_scheduling(void)
{
	setup();
	struct env a = make_env(), b = make_env();
	uint32_t f, g;
	enum adrenogpu_fence_status st;
	assert(adrenogpu_dev_submit(&dev, a.client, a.ctx, 0x10000000ull, 8, 0, 10, &f) == 0);
	/* Another context cannot take over TTBR0 while the ring is busy. */
	assert(adrenogpu_dev_submit(&dev, b.client, b.ctx, 0x10000000ull, 8, 0, 20, &g) == ADRENOGPU_DEV_EBUSY);
	assert(activations == 1);
	/* The same context may queue more. */
	assert(adrenogpu_dev_submit(&dev, a.client, a.ctx, 0x10000000ull, 8, 0, 30, &g) == 0 && g == f + 1);
	fence_word = dev.sched.next_seq - 1;
	assert(adrenogpu_dev_fence_status(&dev, a.client, a.ctx, f, 40, &st) == 0 && st == ADRENOGPU_FENCE_SIGNALED);
	assert(adrenogpu_dev_fence_status(&dev, a.client, a.ctx, g, 40, &st) == 0 && st == ADRENOGPU_FENCE_PENDING);
	fence_word = dev.sched.next_seq;
	uint32_t h;
	assert(adrenogpu_dev_submit(&dev, b.client, b.ctx, 0x10000000ull, 8, 0, 50, &h) == 0 && h == 1);
	assert(activations == 2 && last_ttbr == adrenogpu_vm_root(&dev.ctxs[1].ctx->vm));
	/* Destroying the active context after it went idle parks the bank. */
	fence_word = dev.sched.next_seq;
	assert(adrenogpu_dev_ctx_destroy(&dev, b.client, b.ctx, 60) == 0 && last_ttbr == 0 && dev.active == NULL);
	/* A full queue is EBUSY, not corruption, and recovers once the GPU catches up. */
	cp_stalled = 1;
	unsigned queued = 0;
	int rc;
	while ((rc = adrenogpu_dev_submit(&dev, a.client, a.ctx, 0x10000000ull, 8, 0, 70, &g)) == 0) queued++;
	assert(rc == ADRENOGPU_DEV_EBUSY && queued >= 2 && queued <= ADRENOGPU_SCHED_MAX_JOBS);
	cp_stalled = 0;
	fence_word = dev.sched.next_seq;
	rptr = wptr_written;
	assert(adrenogpu_dev_submit(&dev, a.client, a.ctx, 0x10000000ull, 8, 0, 80, &g) == 0);
	fence_word = dev.sched.next_seq;
	assert(adrenogpu_dev_fence_status(&dev, a.client, a.ctx, g, 90, &st) == 0 && st == ADRENOGPU_FENCE_SIGNALED);
	/* Activation failure is reported and leaves nothing queued. */
	assert(adrenogpu_dev_ctx_create(&dev, a.client, 0, &h, &(uint64_t){0}, &(uint64_t){0}) == 0);
	activate_fails = 1;
	{
		uint32_t before = dev.sched.count;
		assert(adrenogpu_dev_bo_map(&dev, a.client, h, a.bo, 0x10000000ull, 0, 0) == 0);
		assert(adrenogpu_dev_submit(&dev, a.client, h, 0x10000000ull, 8, 0, 95, &g) == ADRENOGPU_DEV_EHW && dev.sched.count == before);
	}
	activate_fails = 0;
	printf("PASS: contexts only switch while idle, fences retire in order, a full queue answers EBUSY\n");
	teardown();
}

int
main(void)
{
	test_validation();
	test_ownership();
	test_scheduling();
	test_teardown();
	test_exhaustion();
	return 0;
}
