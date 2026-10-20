/* Small freestanding libc symbols emitted by clang for the shim. */
#include <stddef.h>

void *memset(void *dst, int value, size_t n)
{
	unsigned char *p = dst;
	for (size_t i = 0; i < n; i++) p[i] = (unsigned char)value;
	return dst;
}

int strcmp(const char *a, const char *b)
{
	while (*a && *a == *b) a++, b++;
	return (unsigned char)*a - (unsigned char)*b;
}
