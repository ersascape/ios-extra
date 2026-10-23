/* SPDX-License-Identifier: MIT */
/* AdrenoGPU per-context GPU address space: a 4-level, 4 KiB-granule, 48-bit page table for the
 * Adreno 810's TTBR0 context bank.
 *
 * The format is the one replayed on the phone since patch 0198: T0SZ=16, 4 KiB granule, stage-1 AArch64
 * descriptors, access flag set, outer shareable, memory attribute index 0. Pure C with no hardware access:
 * the kernel supplies table pages and a TLB-invalidate hook, host tests supply malloc'd pages.
 *
 * Isolation model: a context's IBs run unprivileged against this table, so the GPU can reach exactly the
 * pages mapped here; there is no relocation list. Nothing here validates what the IBs contain. */
#ifndef ADRENOGPU_VM_H
#define ADRENOGPU_VM_H
#include <stddef.h>
#include <stdint.h>

#define ADRENOGPU_PAGE_SIZE 4096u
#define ADRENOGPU_VM_VA_BITS 48u
#define ADRENOGPU_VM_TCR_TTBR0 0xa0102010u /* the value the phone runs with: T0SZ=16, SH0=outer, TG0=4K */

enum adrenogpu_vm_prot {
	ADRENOGPU_VM_READ = 0,      /* every mapping is readable */
	ADRENOGPU_VM_WRITE = 1u,    /* without this the descriptor is read-only (AP[2]) */
	ADRENOGPU_VM_EXEC = 2u,     /* without this the descriptor is execute-never (UXN and PXN) */
};

enum adrenogpu_vm_status {
	ADRENOGPU_VM_OK = 0,
	ADRENOGPU_VM_EINVAL = -1,   /* unaligned, outside the 48-bit space, or bad protection bits */
	ADRENOGPU_VM_ENOMEM = -2,   /* the table allocator failed */
	ADRENOGPU_VM_EEXIST = -3,   /* the page is already mapped */
	ADRENOGPU_VM_ENOENT = -4,   /* the page is not mapped */
	ADRENOGPU_VM_ECORRUPT = -5, /* a table entry points at memory this VM does not own */
};

/* One 4 KiB table page: CPU address, GPU-visible (physical) address. */
struct adrenogpu_vm_table {
	void *cpu;
	uint64_t pa;
};

struct adrenogpu_vm_ops {
	void *context;
	/* A zeroed 4 KiB table page, or a table with cpu == NULL on failure. */
	struct adrenogpu_vm_table (*alloc_table)(void *context);
	void (*free_table)(void *context, struct adrenogpu_vm_table);
	/* Make table writes visible to the GPU (CPU cache clean). Called after every change. */
	void (*publish)(void *context, void *cpu, size_t bytes);
	/* Invalidate the GPU TLB for [va, va + bytes) after an unmap; may invalidate everything. */
	void (*invalidate)(void *context, uint64_t va, uint64_t bytes);
};

#define ADRENOGPU_VM_MAX_TABLES 256u

struct adrenogpu_vm {
	struct adrenogpu_vm_ops ops;
	struct adrenogpu_vm_table tables[ADRENOGPU_VM_MAX_TABLES]; /* tables[0] is the root */
	unsigned ntables;
	unsigned long mapped_pages;
};

/* The 64-bit stage-1 page descriptor for physical page `pa` with `prot`. */
uint64_t adrenogpu_vm_pte(uint64_t pa, unsigned prot);

/* Allocate the root table. */
int adrenogpu_vm_init(struct adrenogpu_vm *, const struct adrenogpu_vm_ops *);
/* Free every table. The caller has already made sure the GPU no longer uses this space. */
void adrenogpu_vm_destroy(struct adrenogpu_vm *);

/* Physical address of the root, for TTBR0. */
uint64_t adrenogpu_vm_root(const struct adrenogpu_vm *);

int adrenogpu_vm_map(struct adrenogpu_vm *, uint64_t va, uint64_t pa, unsigned prot);
/* Map `pages` physically contiguous pages. On failure nothing from this call stays mapped. */
int adrenogpu_vm_map_range(struct adrenogpu_vm *, uint64_t va, uint64_t pa, unsigned long pages, unsigned prot);
int adrenogpu_vm_unmap(struct adrenogpu_vm *, uint64_t va);
/* Physical address backing `va` (page offset kept), or ADRENOGPU_VM_ENOENT. */
int adrenogpu_vm_translate(const struct adrenogpu_vm *, uint64_t va, uint64_t *pa, unsigned *prot);
#endif
