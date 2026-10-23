/* SPDX-License-Identifier: MIT */
#include "adrenogpu_vm.h"

#define PTE_VALID_PAGE   3ull          /* bits [1:0]: valid, table/page */
#define PTE_AP_USER      (1ull << 6)   /* AP[1]: accessible without privilege */
#define PTE_AP_RO        (1ull << 7)   /* AP[2]: read-only */
#define PTE_SH_OUTER     (2ull << 8)   /* SH[1:0] = outer shareable */
#define PTE_AF           (1ull << 10)  /* access flag */
#define PTE_NG           (1ull << 11)  /* not global */
#define PTE_PXN          (1ull << 53)
#define PTE_UXN          (1ull << 54)
#define PTE_PA_MASK      0x0000fffffffff000ull

uint64_t
adrenogpu_vm_pte(uint64_t pa, unsigned prot)
{
	uint64_t pte = (pa & PTE_PA_MASK) | PTE_VALID_PAGE | PTE_AF | PTE_SH_OUTER | PTE_NG | PTE_AP_USER;
	if (!(prot & ADRENOGPU_VM_WRITE)) pte |= PTE_AP_RO;
	if (!(prot & ADRENOGPU_VM_EXEC)) pte |= PTE_PXN | PTE_UXN;
	return pte;
}

static volatile uint64_t *
entries(const struct adrenogpu_vm_table *t)
{
	return (volatile uint64_t *)t->cpu;
}

static struct adrenogpu_vm_table *
table_by_pa(const struct adrenogpu_vm *vm, uint64_t pa)
{
	for (unsigned i = 0; i < vm->ntables; i++)
		if (vm->tables[i].pa == pa) return (struct adrenogpu_vm_table *)&vm->tables[i];
	return NULL;
}

int
adrenogpu_vm_init(struct adrenogpu_vm *vm, const struct adrenogpu_vm_ops *ops)
{
	if (!vm || !ops || !ops->alloc_table || !ops->free_table) return ADRENOGPU_VM_EINVAL;
	vm->ops = *ops;
	vm->ntables = 0;
	vm->mapped_pages = 0;
	struct adrenogpu_vm_table root = ops->alloc_table(ops->context);
	if (!root.cpu) return ADRENOGPU_VM_ENOMEM;
	vm->tables[vm->ntables++] = root;
	if (ops->publish) ops->publish(ops->context, root.cpu, ADRENOGPU_PAGE_SIZE);
	return ADRENOGPU_VM_OK;
}

void
adrenogpu_vm_destroy(struct adrenogpu_vm *vm)
{
	if (!vm) return;
	for (unsigned i = 0; i < vm->ntables; i++) vm->ops.free_table(vm->ops.context, vm->tables[i]);
	vm->ntables = 0;
	vm->mapped_pages = 0;
}

uint64_t
adrenogpu_vm_root(const struct adrenogpu_vm *vm)
{
	return vm->ntables ? vm->tables[0].pa : 0;
}

static int
check_va(uint64_t va)
{
	return (va & (ADRENOGPU_PAGE_SIZE - 1)) || (va >> ADRENOGPU_VM_VA_BITS) ? ADRENOGPU_VM_EINVAL : ADRENOGPU_VM_OK;
}

/* Walk to the level-3 table for `va`; create the missing levels when `create`. */
static int
walk(struct adrenogpu_vm *vm, uint64_t va, int create, struct adrenogpu_vm_table **leaf)
{
	struct adrenogpu_vm_table *t = &vm->tables[0];
	for (unsigned level = 0; level < 3u; level++) {
		unsigned idx = (unsigned)((va >> (39u - 9u * level)) & 511u);
		volatile uint64_t *e = entries(t) + idx;
		if (!*e) {
			if (!create) return ADRENOGPU_VM_ENOENT;
			if (vm->ntables == ADRENOGPU_VM_MAX_TABLES) return ADRENOGPU_VM_ENOMEM;
			struct adrenogpu_vm_table n = vm->ops.alloc_table(vm->ops.context);
			if (!n.cpu) return ADRENOGPU_VM_ENOMEM;
			vm->tables[vm->ntables++] = n;
			if (vm->ops.publish) vm->ops.publish(vm->ops.context, n.cpu, ADRENOGPU_PAGE_SIZE);
			*e = n.pa | 3ull;
			if (vm->ops.publish) vm->ops.publish(vm->ops.context, (void *)(uintptr_t)e, sizeof(*e));
		}
		t = table_by_pa(vm, *e & PTE_PA_MASK);
		if (!t) return ADRENOGPU_VM_ECORRUPT;
	}
	*leaf = t;
	return ADRENOGPU_VM_OK;
}

int
adrenogpu_vm_map(struct adrenogpu_vm *vm, uint64_t va, uint64_t pa, unsigned prot)
{
	if (!vm || vm->ntables == 0 || check_va(va) || (pa & (ADRENOGPU_PAGE_SIZE - 1)) || (pa & ~PTE_PA_MASK) ||
	    (prot & ~(unsigned)(ADRENOGPU_VM_WRITE | ADRENOGPU_VM_EXEC)))
		return ADRENOGPU_VM_EINVAL;
	struct adrenogpu_vm_table *leaf;
	int rc = walk(vm, va, 1, &leaf);
	if (rc) return rc;
	volatile uint64_t *e = entries(leaf) + ((va >> 12) & 511u);
	if (*e) return ADRENOGPU_VM_EEXIST;
	*e = adrenogpu_vm_pte(pa, prot);
	if (vm->ops.publish) vm->ops.publish(vm->ops.context, (void *)(uintptr_t)e, sizeof(*e));
	vm->mapped_pages++;
	return ADRENOGPU_VM_OK;
}

int
adrenogpu_vm_unmap(struct adrenogpu_vm *vm, uint64_t va)
{
	if (!vm || vm->ntables == 0 || check_va(va)) return ADRENOGPU_VM_EINVAL;
	struct adrenogpu_vm_table *leaf;
	int rc = walk(vm, va, 0, &leaf);
	if (rc) return rc;
	volatile uint64_t *e = entries(leaf) + ((va >> 12) & 511u);
	if (!*e) return ADRENOGPU_VM_ENOENT;
	*e = 0;
	if (vm->ops.publish) vm->ops.publish(vm->ops.context, (void *)(uintptr_t)e, sizeof(*e));
	if (vm->ops.invalidate) vm->ops.invalidate(vm->ops.context, va, ADRENOGPU_PAGE_SIZE);
	vm->mapped_pages--;
	return ADRENOGPU_VM_OK;
}

int
adrenogpu_vm_map_range(struct adrenogpu_vm *vm, uint64_t va, uint64_t pa, unsigned long pages, unsigned prot)
{
	if (!pages) return ADRENOGPU_VM_EINVAL;
	for (unsigned long i = 0; i < pages; i++) {
		int rc = adrenogpu_vm_map(vm, va + i * ADRENOGPU_PAGE_SIZE, pa + i * ADRENOGPU_PAGE_SIZE, prot);
		if (rc) {
			while (i--) (void)adrenogpu_vm_unmap(vm, va + i * ADRENOGPU_PAGE_SIZE);
			return rc;
		}
	}
	return ADRENOGPU_VM_OK;
}

int
adrenogpu_vm_translate(const struct adrenogpu_vm *vm, uint64_t va, uint64_t *pa, unsigned *prot)
{
	if (!vm || vm->ntables == 0 || (va >> ADRENOGPU_VM_VA_BITS)) return ADRENOGPU_VM_EINVAL;
	const struct adrenogpu_vm_table *t = &vm->tables[0];
	for (unsigned level = 0; level < 3u; level++) {
		uint64_t e = entries(t)[(va >> (39u - 9u * level)) & 511u];
		if (!e) return ADRENOGPU_VM_ENOENT;
		t = table_by_pa(vm, e & PTE_PA_MASK);
		if (!t) return ADRENOGPU_VM_ECORRUPT;
	}
	uint64_t e = entries(t)[(va >> 12) & 511u];
	if (!e) return ADRENOGPU_VM_ENOENT;
	if (pa) *pa = (e & PTE_PA_MASK) | (va & (ADRENOGPU_PAGE_SIZE - 1));
	if (prot) *prot = ((e & PTE_AP_RO) ? 0u : ADRENOGPU_VM_WRITE) | ((e & PTE_UXN) ? 0u : ADRENOGPU_VM_EXEC);
	return ADRENOGPU_VM_OK;
}
