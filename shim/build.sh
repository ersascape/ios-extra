#!/bin/bash
# Build the shim and wrap it in an Android boot image. Version 2 is the
# historical Sweet path; FP6 uses boot header v4 and receives its DTB from ABL.
set -euo pipefail
cd "$(dirname "$0")"
if command -v aarch64-linux-gnu-gcc >/dev/null 2>&1; then
	CC=${CC:-aarch64-linux-gnu-gcc}
	TARGET_FLAGS=""
else
	CC=${CC:-clang}
	TARGET_FLAGS="--target=aarch64-none-elf"
	LINK_FLAGS="-fuse-ld=lld"
fi
LINK_FLAGS=${LINK_FLAGS:-}
if command -v aarch64-linux-gnu-objcopy >/dev/null 2>&1; then
	OBJCOPY=${OBJCOPY:-aarch64-linux-gnu-objcopy}
elif command -v llvm-objcopy >/dev/null 2>&1; then
	OBJCOPY=${OBJCOPY:-llvm-objcopy}
else
	echo "need aarch64-linux-gnu-objcopy or llvm-objcopy" >&2
	exit 1
fi
READELF=${READELF:-$(command -v llvm-readelf || command -v aarch64-linux-gnu-readelf || true)}
NM=${NM:-$(command -v llvm-nm || command -v aarch64-linux-gnu-nm || true)}
[ -n "$READELF" ] && [ -n "$NM" ] || { echo "need llvm-readelf/llvm-nm or AArch64 binutils" >&2; exit 1; }
CFLAGS="${SHIM_CPPFLAGS:-} -O2 -ffreestanding -nostdlib -fno-pic -fno-jump-tables -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra"
read -r -a TARGET_FLAGS_ARR <<< "$TARGET_FLAGS"
mkdir -p out
for f in start.S shim.c console.c mmu.c fdt.c loader.c ufs.c runtime.c; do
	$CC "${TARGET_FLAGS_ARR[@]}" $CFLAGS -I. -c $f -o out/${f%.*}.o
done
# The image runs wherever ABL puts it with no relocation pass: only the
# header's image_size (start.o, linked at 0) may be an absolute address.
abs=$("$READELF" -r out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o out/runtime.o | grep -c 'R_AARCH64_ABS64 ' || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
$CC "${TARGET_FLAGS_ARR[@]}" $LINK_FLAGS $CFLAGS -static -T shim.ld -Wl,--build-id=none -Wl,-N \
	out/start.o out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o out/ufs.o out/runtime.o -o out/shim.elf
$OBJCOPY -O binary out/shim.elf out/Image
# ABL copies the file; pad to image_size so .bss/stacks exist as zeroed bytes.
size_hex=$("$NM" out/shim.elf | awk '$NF=="_end"{print $1}')
[ -n "$size_hex" ] || { echo "could not find _end in shim ELF" >&2; exit 1; }
size=$((16#$size_hex))
truncate -s "$size" out/Image
# Ramdisk: an XNU payload if given as $1, else an empty newc cpio.
if [ -n "${1:-}" ]; then
	cp "$1" out/ramdisk.bin
else
	(cd out && rm -rf rd && mkdir rd && cd rd && find . | cpio -o -H newc --quiet | gzip -9 > ../ramdisk.bin)
fi
	if [ "${SHIM_BOOT_HEADER_VERSION:-2}" = 4 ]; then
		python3 ../tools/mkbootv4.py --kernel out/Image --ramdisk out/ramdisk.bin \
			--cmdline "${SHIM_BOOT_CMDLINE:-console=null}" --output out/shim-boot.img
	else
		DTB="${SHIM_DTB:-../dtb/boot_unpacked/dtb}"
		mkbootimg --header_version 2 --kernel out/Image --ramdisk out/ramdisk.bin \
			--dtb "$DTB" --base 0 --kernel_offset 0x8000 --ramdisk_offset 0x1000000 \
			--tags_offset 0x100 --dtb_offset 0x1f00000 --pagesize 4096 \
			--os_version 14.0.0 --os_patch_level 2026-07 \
			--cmdline "${SHIM_BOOT_CMDLINE:-console=null}" -o out/shim-boot.img
	fi
ls -l out/Image out/shim-boot.img
