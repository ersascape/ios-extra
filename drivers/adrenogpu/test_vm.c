/* SPDX-License-Identifier: MIT */
/* Host test for adrenogpu_vm. Table pages are malloc'd; their "physical" address is the host pointer. */
#include "adrenogpu_vm.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned live_tables, alloc_calls, publish_calls, invalidate_calls, fail_after;

static struct adrenogpu_vm_table
alloc_table(void *context)
{
	(void)context;
	struct adrenogpu_vm_table t = { 0, 0 };
	if (fail_after && alloc_calls >= fail_after) return t;
	alloc_calls++;
	void *p = aligned_alloc(4096, 4096);
	if (!p) return t;
	memset(p, 0, 4096);
	live_tables++;
	t.cpu = p;
	t.pa = (uint64_t)(uintptr_t)p;
	return t;
}

static void
free_table(void *context, struct adrenogpu_vm_table t)
{
	(void)context;
	free(t.cpu);
	live_tables--;
}

static void publish(void *context, void *cpu, size_t bytes) { (void)context; (void)cpu; (void)bytes; publish_calls++; }
static void invalidate(void *context, uint64_t va, uint64_t bytes) { (void)context; (void)va; (void)bytes; invalidate_calls++; }

static const struct adrenogpu_vm_ops ops = { 0, alloc_table, free_table, publish, invalidate };

static void
reset(void)
{
	assert(live_tables == 0);
	alloc_calls = publish_calls = invalidate_calls = fail_after = 0;
}

int
main(void)
{
	/* 1. The descriptor equals the one the phone runs (patch 0198: FP6_AS_PTE_PAGE). */
	const uint64_t proven = 3ull | (1ull << 10) | (2ull << 8) | (1ull << 11) | (1ull << 6) | (3ull << 53);
	assert(adrenogpu_vm_pte(0x12345000ull, ADRENOGPU_VM_WRITE) == (0x12345000ull | proven));
	assert(adrenogpu_vm_pte(0x1000, ADRENOGPU_VM_READ) & (1ull << 7));                /* read-only */
	assert(!(adrenogpu_vm_pte(0x1000, ADRENOGPU_VM_WRITE | ADRENOGPU_VM_EXEC) & (3ull << 53))); /* executable */
	assert(ADRENOGPU_VM_TCR_TTBR0 == 0xa0102010u);
	printf("PASS: descriptor matches the proven FP6_AS_PTE_PAGE\n");

	/* 2. Map, translate and unmap round trip, including the capture window and the top of the space. */
	reset();
	struct adrenogpu_vm vm;
	assert(adrenogpu_vm_init(&vm, &ops) == 0);
	assert(adrenogpu_vm_root(&vm) == vm.tables[0].pa && vm.ntables == 1);
	const uint64_t vas[] = { 0x1000, 0x100000000ull, 0x10002e000ull, 0xffffffff000ull, (1ull << 48) - 4096 };
	for (unsigned i = 0; i < sizeof vas / sizeof *vas; i++) {
		uint64_t pa = 0x80000000ull + 0x1000ull * i;
		assert(adrenogpu_vm_map(&vm, vas[i], pa, ADRENOGPU_VM_WRITE) == 0);
	}
	for (unsigned i = 0; i < sizeof vas / sizeof *vas; i++) {
		uint64_t pa = 0;
		unsigned prot = 99;
		assert(adrenogpu_vm_translate(&vm, vas[i] + 0x234, &pa, &prot) == 0);
		assert(pa == 0x80000000ull + 0x1000ull * i + 0x234);
		assert(prot == ADRENOGPU_VM_WRITE);
	}
	assert(vm.mapped_pages == 5);
	printf("PASS: map and translate round trip\n");

	/* 3. Argument checks and double mapping. */
	assert(adrenogpu_vm_map(&vm, 0x1004, 0x1000, 0) == ADRENOGPU_VM_EINVAL);            /* unaligned va */
	assert(adrenogpu_vm_map(&vm, 0x5000, 0x1004, 0) == ADRENOGPU_VM_EINVAL);            /* unaligned pa */
	assert(adrenogpu_vm_map(&vm, 1ull << 48, 0x1000, 0) == ADRENOGPU_VM_EINVAL);        /* outside 48 bits */
	assert(adrenogpu_vm_map(&vm, 0x5000, 1ull << 48, 0) == ADRENOGPU_VM_EINVAL);        /* pa outside the mask */
	assert(adrenogpu_vm_map(&vm, 0x5000, 0x1000, 4) == ADRENOGPU_VM_EINVAL);            /* unknown prot bit */
	assert(adrenogpu_vm_map(&vm, 0x1000, 0x9000, 0) == ADRENOGPU_VM_EEXIST);
	assert(adrenogpu_vm_translate(&vm, 0x7000, NULL, NULL) == ADRENOGPU_VM_ENOENT);
	printf("PASS: invalid and duplicate mappings are refused\n");

	/* 4. Unmap invalidates and frees the slot. */
	unsigned inv = invalidate_calls;
	assert(adrenogpu_vm_unmap(&vm, 0x1000) == 0 && invalidate_calls == inv + 1);
	assert(adrenogpu_vm_translate(&vm, 0x1000, NULL, NULL) == ADRENOGPU_VM_ENOENT);
	assert(adrenogpu_vm_unmap(&vm, 0x1000) == ADRENOGPU_VM_ENOENT);
	assert(adrenogpu_vm_map(&vm, 0x1000, 0x9000, ADRENOGPU_VM_READ) == 0);
	printf("PASS: unmap invalidates the TLB hook and allows remapping\n");
	adrenogpu_vm_destroy(&vm);
	assert(live_tables == 0);

	/* 5. A contiguous 2 MiB shares one leaf table: root + three levels. */
	reset();
	assert(adrenogpu_vm_init(&vm, &ops) == 0);
	assert(adrenogpu_vm_map_range(&vm, 0x100000000ull, 0x40000000ull, 512, ADRENOGPU_VM_WRITE) == 0);
	assert(vm.ntables == 4 && vm.mapped_pages == 512);
	adrenogpu_vm_destroy(&vm);
	printf("PASS: 512 contiguous pages share one leaf table\n");

	/* 6. map_range rolls back when a table allocation fails halfway. */
	reset();
	assert(adrenogpu_vm_init(&vm, &ops) == 0);
	fail_after = alloc_calls + 3;                       /* three levels for the first page, then the next leaf fails */
	assert(adrenogpu_vm_map_range(&vm, 0x1ff000, 0x40000000ull, 4, ADRENOGPU_VM_WRITE) == ADRENOGPU_VM_ENOMEM);
	assert(vm.mapped_pages == 0);
	assert(adrenogpu_vm_translate(&vm, 0x1ff000, NULL, NULL) == ADRENOGPU_VM_ENOENT);
	adrenogpu_vm_destroy(&vm);
	printf("PASS: a failed map_range leaves nothing mapped\n");

	/* 7. Allocation failure at init, and no leak. */
	reset();
	fail_after = 1;
	alloc_calls = 1;
	assert(adrenogpu_vm_init(&vm, &ops) == ADRENOGPU_VM_ENOMEM && live_tables == 0);
	printf("PASS: init failure leaks no table\n");

	/* 8. A table entry pointing at memory the VM does not own is reported, never followed. */
	reset();
	assert(adrenogpu_vm_init(&vm, &ops) == 0);
	assert(adrenogpu_vm_map(&vm, 0x4000, 0x1000, 0) == 0);
	((uint64_t *)vm.tables[0].cpu)[0] = 0xdead000ull | 3ull;
	assert(adrenogpu_vm_translate(&vm, 0x4000, NULL, NULL) == ADRENOGPU_VM_ECORRUPT);
	assert(adrenogpu_vm_map(&vm, 0x5000, 0x2000, 0) == ADRENOGPU_VM_ECORRUPT);
	adrenogpu_vm_destroy(&vm);
	printf("PASS: a foreign table pointer is reported as corruption\n");

	/* 9. Every descriptor and table change is published to the GPU. */
	reset();
	assert(adrenogpu_vm_init(&vm, &ops) == 0);
	unsigned before = publish_calls;
	assert(adrenogpu_vm_map(&vm, 0x4000, 0x1000, 0) == 0);
	assert(publish_calls >= before + 4);                 /* three new tables, their links, and the leaf entry */
	adrenogpu_vm_destroy(&vm);
	printf("PASS: table writes are published\n");
	assert(live_tables == 0);
	return 0;
}
