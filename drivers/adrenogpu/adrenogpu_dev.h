/* SPDX-License-Identifier: MIT */
/* AdrenoGPU device core: everything the IOKit shell needs, with no IOKit and no hardware in it.
 *
 * One device owns the scheduler (ring, in-flight jobs, hang detection), the pools of contexts and buffer objects,
 * and a small table of clients (one per open user client). Every object belongs to the client that created it and
 * is named by a 32-bit handle (generation << 16 | slot + 1), so a stale or foreign handle is refused, never
 * resolved. All sizes, addresses and flags coming from user space are validated here; the shell only narrows the
 * 64-bit IOKit scalars with adrenogpu_arg32().
 *
 * Hardware and memory are reached through two small function tables. The memory table is implemented by the shell
 * with kernel allocators; the hardware table is implemented by the GPU bring-up code (bsd/dev/sweet_gpu.c), or by
 * a fake in the host tests.
 *
 * Locking: none inside. The caller serialises every call with one lock. Nothing here blocks; "wait" is the
 * caller polling adrenogpu_dev_fence_status() until the status leaves PENDING or its own deadline passes.
 *
 * Context switching: TTBR0 is written by hw->activate only while the ring is idle (no in-flight job). A submit
 * for another context while jobs are in flight answers EBUSY. Switching between busy contexts needs
 * CP_SMMU_TABLE_UPDATE on the ring and is not implemented (design decision 5). */
#ifndef ADRENOGPU_DEV_H
#define ADRENOGPU_DEV_H
#include "adrenogpu_sched.h"

#define ADRENOGPU_DEV_MAX_CLIENTS 16u
#define ADRENOGPU_DEV_MAX_CTX 32u
#define ADRENOGPU_DEV_MAX_BO 1024u

enum {
	ADRENOGPU_DEV_OK = 0,
	ADRENOGPU_DEV_EINVAL = -1,  /* bad argument: size, alignment, range, flags, overflow, a value wider than 32 bits */
	ADRENOGPU_DEV_ENOENT = -2,  /* no such client, context, buffer object, mapping or fence */
	ADRENOGPU_DEV_EPERM = -3,   /* the handle exists but belongs to another client */
	ADRENOGPU_DEV_ENOSPC = -4,  /* a pool or a per-client quota is exhausted */
	ADRENOGPU_DEV_ENOMEM = -5,  /* an allocator failed */
	ADRENOGPU_DEV_EBUSY = -6,   /* in-flight work forbids this now; try again after it retires */
	ADRENOGPU_DEV_ECLOSED = -7, /* the client is closing */
	ADRENOGPU_DEV_EHW = -8,     /* the hardware table reported a failure */
	ADRENOGPU_DEV_ERANGE = -9,  /* the IB is not inside one mapping of the context */
	ADRENOGPU_DEV_EEXIST = -10, /* the GPU range overlaps an existing mapping */
};

enum adrenogpu_fence_status {
	ADRENOGPU_FENCE_PENDING = 0,
	ADRENOGPU_FENCE_SIGNALED = 1,
	ADRENOGPU_FENCE_LOST = 2, /* abandoned by a GPU reset: the work did not finish */
};

#define ADRENOGPU_USER_PROT_WRITE 1u /* user mapBO protection bits; every mapping is readable */
#define ADRENOGPU_USER_PROT_EXEC 2u

/* Memory the core cannot get from the C library. All sizes are exact; all returned memory is zeroed. */
struct adrenogpu_mem_ops {
	void *context;
	void *(*alloc)(void *context, size_t bytes);               /* zeroed, NULL on failure */
	void (*free)(void *context, void *p, size_t bytes);
	/* Page-table pages, see adrenogpu_vm_ops. */
	struct adrenogpu_vm_table (*alloc_table)(void *context);
	void (*free_table)(void *context, struct adrenogpu_vm_table);
	void (*publish)(void *context, void *cpu, size_t bytes);
	/* Backing for a buffer object: fill pages[0..npages) with the physical address of every 4 KiB page, zeroed
	 * memory. Returns 0 and a cookie, or nonzero (nothing allocated). */
	int (*bo_alloc)(void *context, unsigned long npages, uint64_t *pages, void **cookie);
	void (*bo_free)(void *context, void *cookie);
	/* Optional: make CPU writes to the buffer visible to the GPU. Called for every buffer mapped in the
	 * submitting context at each submit when set; leave NULL when the memory is mapped uncached. */
	void (*bo_publish)(void *context, void *cookie);
};

/* What the hardware bring-up supplies. */
struct adrenogpu_hw_info {
	volatile uint32_t *ring;  /* CPU view of the command ring */
	uint32_t ring_dwords;     /* power of two, at least 64 */
	uint32_t wptr;            /* current write pointer */
	uint64_t fence_va;        /* GPU address of the shared fence word, dword aligned */
	uint64_t fence_map_pa;    /* nonzero: physical page holding the fence word; it is mapped into every context at
	                           * fence_va with fence_map_prot, which must lie outside the context VA range */
	unsigned fence_map_prot;
	uint64_t timeout;         /* a job older than this is hung (same unit as the `now` the caller passes) */
};

struct adrenogpu_hw_ops {
	void *context;
	uint32_t (*read_rptr)(void *context);   /* CP_RB_RPTR */
	uint32_t (*read_fence)(void *context);  /* the fence word the GPU writes (read through the CPU mapping) */
	void (*write_wptr)(void *context, uint32_t wptr); /* order the ring writes first, then CP_RB_WPTR */
	void (*tlb_invalidate)(void *context, uint64_t va, uint64_t bytes);
	int (*activate)(void *context, uint64_t ttbr0); /* only called while idle; 0 parks the context bank */
	int (*reset)(void *context, uint32_t *wptr);    /* reset the GPU and the ring; *wptr = the new write pointer */
};

struct adrenogpu_dev_config {
	uint64_t va_lo, va_hi;         /* the VA range of every context, page aligned, inside 48 bits */
	unsigned max_ctx_per_client;   /* each capped by the pool size */
	unsigned max_bo_per_client;
	uint64_t max_bo_bytes;         /* one buffer object */
	uint64_t max_client_bytes;     /* all buffer objects of one client */
	uint64_t close_timeout;        /* how long a closing client may keep jobs in flight before a GPU reset */
};

struct adrenogpu_dev_client {
	int in_use;
	int closing;
	uint32_t gen;
	uint64_t close_deadline;
	unsigned nctx, nbo;
	uint64_t bytes;
};

struct adrenogpu_dev_ctx {
	int in_use;
	uint16_t gen;
	uint32_t owner; /* client id */
	struct adrenogpu_ctx *ctx;
};

struct adrenogpu_dev_bo {
	struct adrenogpu_bo bo; /* first member: a mapping's bo pointer converts back to this */
	int in_use;
	uint16_t gen;
	uint32_t owner;
	uint64_t *pages;
	void *cookie;
	unsigned mapcount;
};

struct adrenogpu_dev {
	struct adrenogpu_mem_ops mem;
	struct adrenogpu_hw_ops hw;
	struct adrenogpu_hw_info info;
	struct adrenogpu_dev_config cfg;
	struct adrenogpu_vm_ops vmops;
	struct adrenogpu_sched sched;
	struct adrenogpu_dev_client clients[ADRENOGPU_DEV_MAX_CLIENTS];
	struct adrenogpu_dev_ctx ctxs[ADRENOGPU_DEV_MAX_CTX];
	struct adrenogpu_dev_bo bos[ADRENOGPU_DEV_MAX_BO];
	struct adrenogpu_dev_ctx *active; /* the context whose TTBR0 is programmed, NULL if none */
	uint32_t next_client_gen;
	unsigned long resets;
	int wedged; /* a GPU reset failed: in-flight work may still touch memory, so no new work and no releases */
};

/* Narrow a 64-bit IOKit scalar to 32 bits; EINVAL when it does not fit (no silent truncation). */
int adrenogpu_arg32(uint64_t v, uint32_t *out);

/* The default limits: contexts in [1 MiB, 128 TiB), 8 contexts and 256 buffers per client, 256 MiB per buffer,
 * 1 GiB per client, close timeout = `timeout`. */
void adrenogpu_dev_default_config(struct adrenogpu_dev_config *, uint64_t timeout);

int adrenogpu_dev_init(struct adrenogpu_dev *, const struct adrenogpu_mem_ops *, const struct adrenogpu_hw_ops *,
    const struct adrenogpu_hw_info *, const struct adrenogpu_dev_config *);
/* Close every client without waiting (the GPU is reset first if jobs are in flight) and release the device. */
void adrenogpu_dev_destroy(struct adrenogpu_dev *);

/* Retire finished jobs from the fence word; on a hang reset the GPU and fail the in-flight jobs. Returns 1 if a
 * reset happened. Every other call below polls first, so a waiting caller only needs fence_status. */
int adrenogpu_dev_poll(struct adrenogpu_dev *, uint64_t now);

int adrenogpu_dev_client_open(struct adrenogpu_dev *, uint32_t *client);
/* Tear a client down: no new work is accepted, in-flight work is waited out until `close_timeout` and then failed
 * by a GPU reset, then its contexts and buffer objects are released. Returns EBUSY while work is still in flight
 * (call again later with a later `now`), OK when the client is gone. */
int adrenogpu_dev_client_close(struct adrenogpu_dev *, uint32_t client, uint64_t now);

int adrenogpu_dev_ctx_create(struct adrenogpu_dev *, uint32_t client, uint32_t flags, uint32_t *ctx,
    uint64_t *va_lo, uint64_t *va_hi);
int adrenogpu_dev_ctx_destroy(struct adrenogpu_dev *, uint32_t client, uint32_t ctx, uint64_t now);

int adrenogpu_dev_bo_alloc(struct adrenogpu_dev *, uint32_t client, uint64_t size, uint32_t flags, uint32_t *bo,
    uint64_t *actual_size);
/* EBUSY while the buffer is still mapped in a context. */
int adrenogpu_dev_bo_free(struct adrenogpu_dev *, uint32_t client, uint32_t bo);
/* The cookie of a buffer the client owns (for the shell to map it into the client's task), or NULL. */
void *adrenogpu_dev_bo_cookie(struct adrenogpu_dev *, uint32_t client, uint32_t bo, uint64_t *bytes);

int adrenogpu_dev_bo_map(struct adrenogpu_dev *, uint32_t client, uint32_t ctx, uint32_t bo, uint64_t va,
    unsigned prot, uint64_t now);
/* EBUSY while the context has jobs in flight. */
int adrenogpu_dev_bo_unmap(struct adrenogpu_dev *, uint32_t client, uint32_t ctx, uint64_t va, uint64_t now);

int adrenogpu_dev_submit(struct adrenogpu_dev *, uint32_t client, uint32_t ctx, uint64_t ib_va, uint32_t ib_dwords,
    uint32_t flags, uint64_t now, uint32_t *fence);
/* Status of a fence of this context. The fence must have been issued to it. */
int adrenogpu_dev_fence_status(struct adrenogpu_dev *, uint32_t client, uint32_t ctx, uint32_t fence, uint64_t now,
    enum adrenogpu_fence_status *status);
#endif
