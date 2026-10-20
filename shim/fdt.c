/* Minimal bounded FDT reader for ABL's /chosen and runtime memory map. */
#include "fdt.h"

#define FDT_MAGIC 0xd00dfeed
#define FDT_BEGIN_NODE 1
#define FDT_END_NODE 2
#define FDT_PROP 3
#define FDT_NOP 4
#define FDT_END 9
#define MAX_DEPTH 64

static uint32_t be32(uintptr_t a) { return __builtin_bswap32(*(volatile uint32_t *)a); }
static uint64_t be64(uintptr_t a) { return (uint64_t)be32(a) << 32 | be32(a + 4); }
static uintptr_t align4(uintptr_t a) { return (a + 3) & ~3UL; }
static uintptr_t skip_str(uintptr_t p) { while (*(volatile char *)p) p++; return p + 1; }

static int streq(const char *a, const char *b)
{
	while (*a && *a == *b) a++, b++;
	return *a == *b;
}

static int starts(const char *a, const char *b)
{
	while (*b && *a == *b) a++, b++;
	return !*b;
}

static uint64_t cells(uintptr_t p, uint32_t n)
{
	uint64_t v = 0;
	for (uint32_t i = 0; i < n; i++) v = (v << 32) | be32(p + i * 4);
	return v;
}

int fdt_chosen_u64(uintptr_t fdt, const char *prop, uint64_t *out)
{
	if (!fdt || be32(fdt) != FDT_MAGIC) return 0;
	uintptr_t p = fdt + be32(fdt + 8), end = p + be32(fdt + 36);
	uintptr_t strings = fdt + be32(fdt + 12);
	int depth = 0, chosen = 0;
	while (p + 4 <= end) {
		uint32_t tok = be32(p); p += 4;
		if (tok == FDT_BEGIN_NODE) {
			const char *name = (const char *)p;
			depth++;
			chosen = depth == 2 && streq(name, "chosen");
			p = align4(skip_str(p));
		} else if (tok == FDT_END_NODE) {
			if (chosen) return 0;
			depth--;
		} else if (tok == FDT_PROP) {
			uint32_t len = be32(p), nameoff = be32(p + 4);
			uintptr_t val = p + 8;
			if (chosen && streq((const char *)(strings + nameoff), prop)) {
				if (len == 4) *out = be32(val);
				else if (len == 8) *out = be64(val);
				else return 0;
				return 1;
			}
			p = align4(val + len);
		} else if (tok == FDT_NOP) continue;
		else return 0;
	}
	return 0;
}

static int add_range(struct fdt_range *out, uint32_t *n, uint32_t cap,
		     uint64_t base, uint64_t size)
{
	if (!size) return 1;
	if (*n >= cap) return 0;
	out[(*n)++] = (struct fdt_range){base, size};
	return 1;
}

int fdt_memory_map(uintptr_t fdt, struct fdt_range *memory, uint32_t *nmemory,
		   struct fdt_range *reserved, uint32_t *nreserved, uint64_t *total_size)
{
	if (!fdt || be32(fdt) != FDT_MAGIC) return 0;
	const uint32_t memory_cap = *nmemory, reserved_cap = *nreserved;
	*nmemory = *nreserved = 0;
	*total_size = be32(fdt + 4);
	uint32_t ac[MAX_DEPTH] = {2}, sc[MAX_DEPTH] = {2};
	uint8_t kind[MAX_DEPTH] = {0}; /* 1=memory, 2=reserved-memory child */
	int depth = -1;
	uintptr_t p = fdt + be32(fdt + 8), end = p + be32(fdt + 36);
	uintptr_t strings = fdt + be32(fdt + 12);

	/* FDT memreserve map entries. */
	uintptr_t r = fdt + be32(fdt + 16);
	for (uint32_t i = 0; i < 64 && r + 16 <= fdt + *total_size; i++, r += 16) {
		uint64_t base = be64(r), size = be64(r + 8);
		if (!base && !size) break;
		if (!add_range(reserved, nreserved, reserved_cap, base, size)) return 0;
	}

	while (p + 4 <= end) {
		uint32_t tok = be32(p); p += 4;
		if (tok == FDT_BEGIN_NODE) {
			const char *name = (const char *)p;
			depth++;
			if (depth >= MAX_DEPTH) return 0;
			if (depth > 0) { ac[depth] = ac[depth - 1]; sc[depth] = sc[depth - 1]; }
			kind[depth] = 0;
			if (depth == 1 && (streq(name, "memory") || starts(name, "memory@"))) kind[depth] = 1;
			if (depth == 2 && kind[1] == 3) kind[depth] = 2;
			if (depth == 1 && streq(name, "reserved-memory")) kind[depth] = 3;
			p = align4(skip_str(p));
		} else if (tok == FDT_END_NODE) {
			if (depth < 0) return 0;
			depth--;
		} else if (tok == FDT_PROP) {
			uint32_t len = be32(p), nameoff = be32(p + 4);
			const char *name = (const char *)(strings + nameoff);
			uintptr_t val = p + 8;
			if (depth == 0 && streq(name, "#address-cells") && len == 4) ac[0] = be32(val);
			else if (depth == 0 && streq(name, "#size-cells") && len == 4) sc[0] = be32(val);
			else if (depth == 1 && kind[depth] == 3 && streq(name, "#address-cells") && len == 4) ac[depth] = be32(val);
			else if (depth == 1 && kind[depth] == 3 && streq(name, "#size-cells") && len == 4) sc[depth] = be32(val);
			else if (depth > 0 && (kind[depth] == 1 || kind[depth] == 2) && streq(name, "reg")) {
				uint32_t na = ac[depth - 1], ns = sc[depth - 1], tuple = (na + ns) * 4;
				if (!na || na > 2 || !ns || ns > 2 || !tuple || len % tuple) return 0;
				for (uint32_t off = 0; off < len; off += tuple) {
					uint64_t base = cells(val + off, na);
					uint64_t size = cells(val + off + na * 4, ns);
					if (kind[depth] == 1) {
						if (!add_range(memory, nmemory, memory_cap, base, size)) return 0;
					} else if (!add_range(reserved, nreserved, reserved_cap, base, size)) return 0;
				}
			}
			p = align4(val + len);
		} else if (tok == FDT_NOP) continue;
		else if (tok == FDT_END) break;
		else return 0;
	}
	return *nmemory != 0;
}

int fdt_framebuffer(uintptr_t fdt, struct fdt_fb *fb)
{
	if (!fdt || be32(fdt) != FDT_MAGIC) return 0;
	uint32_t ac[MAX_DEPTH] = {2}, sc[MAX_DEPTH] = {2};
	int depth = -1, in_chosen = 0, in_fb = 0, have_reg = 0;
	uintptr_t p = fdt + be32(fdt + 8), end = p + be32(fdt + 36);
	uintptr_t strings = fdt + be32(fdt + 12);
	while (p + 4 <= end) {
		uint32_t tok = be32(p); p += 4;
		if (tok == FDT_BEGIN_NODE) {
			const char *node_name = (const char *)p;
			depth++;
			if (depth >= MAX_DEPTH) return 0;
			if (depth > 0) { ac[depth] = ac[depth - 1]; sc[depth] = sc[depth - 1]; }
			if (depth == 1) in_chosen = streq(node_name, "chosen");
			if (depth == 2 && in_chosen && starts(node_name, "framebuffer@")) { in_fb = 1; have_reg = 0; }
			p = align4(skip_str(p));
		} else if (tok == FDT_END_NODE) {
			if (in_fb && depth == 2) {
				return have_reg && fb->base && fb->size && fb->width && fb->height &&
				       fb->stride >= fb->width * 4 &&
				       (uint64_t)fb->stride * fb->height <= fb->size;
			}
			if (depth == 2) in_fb = 0;
			if (depth == 1) in_chosen = 0;
			depth--;
		} else if (tok == FDT_PROP) {
			uint32_t len = be32(p), nameoff = be32(p + 4);
			const char *name = (const char *)(strings + nameoff);
			uintptr_t val = p + 8;
			if (in_chosen && depth == 1 && streq(name, "#address-cells") && len == 4) ac[depth] = be32(val);
			else if (in_chosen && depth == 1 && streq(name, "#size-cells") && len == 4) sc[depth] = be32(val);
			else if (in_fb && streq(name, "reg")) {
				uint32_t na = ac[depth - 1], ns = sc[depth - 1];
				if (na > 2 || ns > 2 || len < (na + ns) * 4) return 0;
				fb->base = cells(val, na); fb->size = cells(val + na * 4, ns); have_reg = 1;
			} else if (in_fb && len == 4 && streq(name, "width")) fb->width = be32(val);
			else if (in_fb && len == 4 && streq(name, "height")) fb->height = be32(val);
			else if (in_fb && len == 4 && streq(name, "stride")) fb->stride = be32(val);
			p = align4(val + len);
		} else if (tok == FDT_NOP) continue;
		else if (tok == FDT_END) break;
		else return 0;
	}
	return 0;
}

int fdt_root_compatible(uintptr_t fdt, const char *compatible)
{
	if (!fdt || be32(fdt) != FDT_MAGIC) return 0;
	uintptr_t p = fdt + be32(fdt + 8), end = p + be32(fdt + 36);
	uintptr_t strings = fdt + be32(fdt + 12);
	int depth = -1;
	while (p + 4 <= end) {
		uint32_t tok = be32(p); p += 4;
		if (tok == FDT_BEGIN_NODE) {
			depth++;
			p = align4(skip_str(p));
		} else if (tok == FDT_END_NODE) {
			if (depth == 0) return 0;
			depth--;
		} else if (tok == FDT_PROP) {
			uint32_t len = be32(p), nameoff = be32(p + 4);
			uintptr_t val = p + 8;
			if (depth == 0 && streq((const char *)(strings + nameoff), "compatible")) {
				uint32_t off = 0;
				while (off < len) {
					const char *s = (const char *)(val + off);
					uint32_t n = 0;
					while (off + n < len && s[n]) n++;
					if (n == 0 || off + n >= len) return 0;
					uint32_t i = 0;
					while (i < n && compatible[i] && s[i] == compatible[i]) i++;
					if (i == n && !compatible[i]) return 1;
					off += n + 1;
				}
				return 0;
			}
			p = align4(val + len);
		} else if (tok == FDT_NOP) continue;
		else if (tok == FDT_END) break;
		else return 0;
	}
	return 0;
}
