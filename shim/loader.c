/*
 * Milestone 4: act as iBoot for xnu.
 *
 * mkpayload.py already resolved the kernel's chained fixups and built the
 * ADT, so this only has to: find the payload in the ABL ramdisk, copy the
 * segments to phys_base + (vmaddr - virt_base), place the ADT and
 * boot_args behind the kernel, and jump to the entry point with the MMU
 * and caches off, x0 = boot_args (physical).
 */
#include <stdint.h>
#include "console.h"
#include "fdt.h"
#include "loader.h"

#define BOOT_LINE_LENGTH	608
#define PAGE_16K		0x4000UL
#define ALIGN_32M		0x2000000UL
#define MAX_MEMORY_RANGES	32
#define MAX_RESERVED_RANGES	96

struct payload_seg {
	uint64_t vmaddr, vmsize, file_off, file_size;
};

struct payload {
	char magic[8];
	uint32_t version, nsegs;
	uint64_t virt_base, entry_va, adt_off, adt_size, kernel_end;
	uint64_t phys_base, mem_size;
	char cmdline[BOOT_LINE_LENGTH];
	struct payload_seg segs[];
};

/* pexpert/pexpert/arm64/boot.h, Revision/Version 2 */
struct boot_video {
	uint64_t v_baseAddr, v_display, v_rowBytes, v_width, v_height, v_depth;
};

struct boot_args {
	uint16_t Revision, Version;
	uint64_t virtBase, physBase, memSize, topOfKernelData;
	struct boot_video Video;
	uint32_t machineType;
	uint64_t deviceTreeP;
	uint32_t deviceTreeLength;
	char CommandLine[BOOT_LINE_LENGTH];
	uint64_t bootFlags, memSizeActual;
};

_Static_assert(__builtin_offsetof(struct payload, segs) == 0x2a8, "payload header layout");
_Static_assert(__builtin_offsetof(struct boot_args, Video) == 40, "boot_args layout");
_Static_assert(__builtin_offsetof(struct boot_args, CommandLine) == 108, "boot_args layout");
_Static_assert(sizeof(struct boot_args) == 736, "boot_args layout");

/* MMU off: everything is Device memory, so copy in aligned 8-byte words. */
static void copy64(uintptr_t dst, uintptr_t src, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	volatile const uint64_t *s = (volatile const uint64_t *)src;
	for (uint64_t i = 0; i < (n + 7) / 8; i++)
		d[i] = s[i];
}

static void zero64(uintptr_t dst, uint64_t n)
{
	volatile uint64_t *d = (volatile uint64_t *)dst;
	for (uint64_t i = 0; i < n / 8; i++)
		d[i] = 0;
}

static int magic_ok(const char *m)
{
	static const char want[] = "SWEETXNU";
	for (int i = 0; i < 8; i++)
		if (m[i] != want[i])
			return 0;
	return 1;
}

typedef void (*xnu_entry_t)(uint64_t boot_args_pa);

extern char _head[], _end[];

static int streq(const char *a, const char *b)
{
	while (*a && *a == *b) a++, b++;
	return *a == *b;
}

static uint64_t align_up(uint64_t v, uint64_t a) { return (v + a - 1) & ~(a - 1); }

static void sort_ranges(struct fdt_range *r, uint32_t n)
{
	for (uint32_t i = 1; i < n; i++) {
		struct fdt_range v = r[i]; uint32_t j = i;
		while (j && r[j - 1].base > v.base) { r[j] = r[j - 1]; j--; }
		r[j] = v;
	}
}

static int consider_gap(uint64_t start, uint64_t end, uint64_t need,
			uint64_t *best_base, uint64_t *best_size)
{
	if (end <= start) return 1;
	start = align_up(start, ALIGN_32M);
	end &= ~(PAGE_16K - 1);
	if (end <= start || end - start < need) return 1;
	if (end - start > *best_size) { *best_base = start; *best_size = end - start; }
	return 1;
}

static int choose_runtime_ram(uintptr_t dtb, uint64_t initrd_start, uint64_t initrd_end,
			      uint64_t need, uint64_t *base, uint64_t *size,
			      struct fdt_fb *fb)
{
	struct fdt_range memory[MAX_MEMORY_RANGES], reserved[MAX_RESERVED_RANGES];
	uint32_t nm = MAX_MEMORY_RANGES, nr = MAX_RESERVED_RANGES - 4;
	uint64_t dtb_size;
	if (!fdt_memory_map(dtb, memory, &nm, reserved, &nr, &dtb_size)) return 0;
	sort_ranges(reserved, nr);
	if (fdt_framebuffer(dtb, fb)) {
		uint64_t fb_reserve = fb->size;
		if (fb->base == 0xe3940000UL && fb_reserve < 0x2b00000UL) fb_reserve = 0x2b00000UL;
		reserved[nr++] = (struct fdt_range){fb->base, fb_reserve};
	}
	reserved[nr++] = (struct fdt_range){initrd_start, initrd_end - initrd_start};
	reserved[nr++] = (struct fdt_range){dtb, dtb_size};
	reserved[nr++] = (struct fdt_range){(uintptr_t)_head, (uintptr_t)(_end - _head)};
	sort_ranges(reserved, nr);

	uint64_t best_base = 0, best_size = 0;
	for (uint32_t i = 0; i < nm; i++) {
		uint64_t bank = memory[i].base, bank_end = bank + memory[i].size;
		if (bank_end < bank) continue;
		uint64_t cursor = bank;
		for (uint32_t j = 0; j < nr && cursor < bank_end; j++) {
			uint64_t r0 = reserved[j].base, r1 = r0 + reserved[j].size;
			if (r1 < r0 || r1 <= cursor || r0 >= bank_end) continue;
			if (r0 > cursor) consider_gap(cursor, r0 < bank_end ? r0 : bank_end,
						      need, &best_base, &best_size);
			if (r1 > cursor) cursor = r1;
		}
		consider_gap(cursor, bank_end, need, &best_base, &best_size);
	}
	if (!best_base || !best_size) return 0;
	*base = best_base; *size = best_size;
	return 1;
}

static uint32_t le32(const volatile uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static void put_le64(volatile uint8_t *p, uint64_t v)
{
	for (uint32_t i = 0; i < 8; i++) p[i] = (uint8_t)(v >> (i * 8));
}

static int adt_patch_node(volatile uint8_t *blob, uint32_t len, uint32_t *off,
			  uint64_t base, uint64_t size, uint64_t ramdisk_base,
			  uint64_t ramdisk_size, int *have_base, int *have_size)
{
	if (*off > len || len - *off < 8) return 0;
	uint32_t nprops = le32(blob + *off), nchildren = le32(blob + *off + 4);
	*off += 8;
	uint32_t props = *off; int chosen = 0;
	for (uint32_t i = 0; i < nprops; i++) {
		if (*off > len || len - *off < 36) return 0;
		const volatile char *name = (const volatile char *)(blob + *off);
		uint32_t sz = le32(blob + *off + 32), n = sz & 0x7fffffff;
		uint32_t value = *off + 36;
		if (n > len - value) return 0;
		if (streq((const char *)name, "name") && n >= 6 && streq((const char *)(blob + value), "chosen")) chosen = 1;
		*off = value + ((n + 3) & ~3U);
		if (*off > len) return 0;
	}
	uint32_t pos = props;
	for (uint32_t i = 0; i < nprops; i++) {
		const volatile char *name = (const volatile char *)(blob + pos);
		uint32_t n = le32(blob + pos + 32) & 0x7fffffff;
		uint32_t value = pos + 36;
		if (chosen && n == 8 && streq((const char *)name, "dram-base")) {
			put_le64(blob + value, base); *have_base = 1;
		} else if (chosen && n == 8 && streq((const char *)name, "dram-size")) {
			put_le64(blob + value, size); *have_size = 1;
		} else if (n == 16 && streq((const char *)name, "RAMDisk")) {
			put_le64(blob + value, ramdisk_base);
			put_le64(blob + value + 8, ramdisk_size);
		}
		pos = value + ((n + 3) & ~3U);
	}
	for (uint32_t i = 0; i < nchildren; i++)
		if (!adt_patch_node(blob, len, off, base, size, ramdisk_base, ramdisk_size,
				    have_base, have_size)) return 0;
	return 1;
}

static int adt_patch_ram(volatile uint8_t *blob, uint32_t len, uint64_t base, uint64_t size,
			 uint64_t ramdisk_base, uint64_t ramdisk_size)
{
	uint32_t off = 0; int have_base = 0, have_size = 0;
	return adt_patch_node(blob, len, &off, base, size, ramdisk_base, ramdisk_size,
			       &have_base, &have_size) &&
	       have_base && have_size;
}

const char *loader_boot(uintptr_t dtb)
{
	uint64_t rd_start, rd_end;

	if (!fdt_chosen_u64(dtb, "linux,initrd-start", &rd_start) ||
	    !fdt_chosen_u64(dtb, "linux,initrd-end", &rd_end))
		return "no initrd in /chosen";
	con_hex2("INITRD", "lo=", rd_start, "hi=", rd_end);

	if (rd_end <= rd_start || rd_end - rd_start < sizeof(struct payload))
		return "bad initrd range";
	/* v4 ABL may prepend vendor ramdisks to the generic payload. */
	uint64_t payload_start = (rd_start + 7) & ~7UL;
	while (payload_start <= rd_end - sizeof(struct payload) &&
	       !magic_ok((const char *)payload_start)) payload_start += 8;
	if (payload_start > rd_end - sizeof(struct payload))
		return "no aligned SWEETXNU payload";
	uint64_t payload_size = rd_end - payload_start;
	const struct payload *p = (const struct payload *)payload_start;
	if (!magic_ok(p->magic))
		return "no SWEETXNU payload";
	if (p->version != 1 || (p->adt_off & 7) || (rd_start & 7))
		return "bad payload header";
	if (p->adt_size > 0xffffffffUL || p->adt_off > payload_size || p->adt_size > payload_size - p->adt_off)
		return "bad payload ADT range";

	if (p->nsegs > (payload_size - sizeof(*p)) / sizeof(struct payload_seg))
		return "bad segment table";
	for (uint32_t i = 0; i < p->nsegs; i++) {
		const struct payload_seg *s = &p->segs[i];
		if (s->file_off > payload_size || s->file_size > payload_size - s->file_off ||
		    s->file_size > s->vmsize || s->vmaddr < p->virt_base ||
		    s->vmaddr > p->kernel_end || s->vmsize > p->kernel_end - s->vmaddr ||
		    (s->file_off & 7) || (s->vmaddr & 7) || (s->vmsize & 7))
			return "bad payload segment";
	}
	if (p->kernel_end < p->virt_base ||
	    p->kernel_end - p->virt_base > UINT64_MAX - p->adt_size - PAGE_16K * 2 ||
	    p->entry_va < p->virt_base || p->entry_va >= p->kernel_end)
		return "bad kernel extent";
	uint64_t need = p->kernel_end - p->virt_base + p->adt_size + PAGE_16K * 2;
	uint64_t phys_base = p->phys_base, mem_size = p->mem_size;
	struct fdt_fb fb = {0};
	if (!phys_base && !mem_size) {
		if (p->kernel_end < p->virt_base)
			return "bad kernel range";
		if (!choose_runtime_ram(dtb, rd_start, rd_end, need,
					&phys_base, &mem_size, &fb))
			return "no free RAM range in bootloader FDT";
		if (!fb.base)
			return "no framebuffer in bootloader FDT";
		con_set_framebuffer(fb.base, fb.width, fb.height, fb.stride);
	} else if (!phys_base || !mem_size) {
		return "incomplete payload RAM range";
	}
	if (mem_size < need || phys_base > UINT64_MAX - mem_size)
		return "kernel exceeds RAM range";
	uint64_t pa_of_va_base = phys_base - p->virt_base;	/* pa = va + this */
	con_hex2("PHYS", "base=", phys_base, "size=", mem_size);
	con_hex("VIRT", p->virt_base);
	con_hex("ENTRY", p->entry_va);

	/* The payload must not overlap where the kernel goes. */
	if (rd_end > phys_base && rd_start < phys_base + mem_size)
		return "ramdisk overlaps kernel memory";

	for (uint32_t i = 0; i < p->nsegs; i++) {
		const struct payload_seg *s = &p->segs[i];
		uintptr_t dst = s->vmaddr + pa_of_va_base;
		copy64(dst, payload_start + s->file_off, s->file_size);
		if (s->vmsize > s->file_size)
			zero64(dst + ((s->file_size + 7) & ~7UL), s->vmsize - ((s->file_size + 7) & ~7UL));
	}
	con_hex2("SEGS", "n=", p->nsegs, "end=", p->kernel_end + pa_of_va_base);

	/* ADT, then boot_args, behind the kernel; everything below topOfKernelData is ours. */
	uintptr_t adt_pa = p->kernel_end + pa_of_va_base;
	copy64(adt_pa, payload_start + p->adt_off, p->adt_size);
	if (!p->phys_base) {
		uint64_t rd_pa = 0, rd_size = 0;
		if (p->nsegs) {
			const struct payload_seg *last = &p->segs[p->nsegs - 1];
			rd_pa = last->vmaddr + pa_of_va_base;
			rd_size = last->vmsize;
		}
		if (!adt_patch_ram((volatile uint8_t *)adt_pa, (uint32_t)p->adt_size,
				   phys_base, mem_size, rd_pa, rd_size))
			return "FP6 ADT RAM properties missing";
	}
	uintptr_t ba_pa = (adt_pa + p->adt_size + PAGE_16K - 1) & ~(PAGE_16K - 1);
	uintptr_t top = ba_pa + PAGE_16K;

	zero64(ba_pa, PAGE_16K);
	volatile struct boot_args *ba = (volatile struct boot_args *)ba_pa;
	ba->Revision = 2;
	ba->Version = 2;
	ba->virtBase = p->virt_base;
	ba->physBase = phys_base;
	ba->memSize = mem_size;
	ba->topOfKernelData = top;
	uint64_t fb_base;
	uint32_t fb_width, fb_height, fb_stride;
	con_get_framebuffer(&fb_base, &fb_width, &fb_height, &fb_stride);
	ba->Video.v_baseAddr = fb_base;
	ba->Video.v_display = 1;
	ba->Video.v_rowBytes = fb_stride;
	ba->Video.v_width = fb_width;
	ba->Video.v_height = fb_height;
	ba->Video.v_depth = 32;
	ba->deviceTreeP = adt_pa - pa_of_va_base;	/* xnu reads it with the MMU on: a VA */
	ba->deviceTreeLength = (uint32_t)p->adt_size;
	for (int i = 0; i < BOOT_LINE_LENGTH; i++)
		ba->CommandLine[i] = p->cmdline[i];
	ba->memSizeActual = mem_size;
	con_hex2("BOOTARG", "pa=", ba_pa, "top=", top);

	uintptr_t entry_pa = p->entry_va + pa_of_va_base;
	con_hex("JUMP", entry_pa);
	con_str("XNU", "jumping (fbcon clears screen)");

	/* Everything was written with the MMU and caches off; drop any stale I-cache lines too. */
	__asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");
	((xnu_entry_t)entry_pa)(ba_pa);
	return "xnu returned";
}
