#pragma once
#include <stdint.h>

struct fdt_range { uint64_t base, size; };
struct fdt_fb { uint64_t base, size; uint32_t width, height, stride; };

/* Read a u32/u64 (cell-size agnostic) property of /chosen. Returns 0 if absent. */
int fdt_chosen_u64(uintptr_t fdt, const char *prop, uint64_t *out);
/* Runtime memory map and reserved ranges supplied by the bootloader. */
int fdt_memory_map(uintptr_t fdt, struct fdt_range *memory, uint32_t *nmemory,
		   struct fdt_range *reserved, uint32_t *nreserved, uint64_t *total_size);
/* Simple framebuffer under /chosen, if the bootloader supplied one. */
int fdt_framebuffer(uintptr_t fdt, struct fdt_fb *fb);
/* Match one NUL-separated string in the root compatible property. */
int fdt_root_compatible(uintptr_t fdt, const char *compatible);
