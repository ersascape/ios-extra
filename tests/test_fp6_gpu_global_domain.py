#!/usr/bin/env python3
"""Exercise the FP6 GPU 48-bit TTBR1 global-memory page tables."""
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
patch = (ROOT / "xnu/patches/0163-fp6-gpu-global-domain.patch").read_text()
gpu_patch = patch.split("\ndiff --git ", 1)[0]
header = "\n".join(
    line[1:] for line in gpu_patch.splitlines()
    if line.startswith("+") and not line.startswith("+++")
) + "\n"

source = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "gpu_domain.h"
static unsigned nalloc, npublish;
static int alloc_table(void *ctx, uint32_t size, struct fp6_gpu_global_page *p) {
 (void)ctx;
 assert(size == 4096);
 p->va=aligned_alloc(4096,4096);
 p->pa=0x900000000ULL+(uint64_t)nalloc++*0x1000;
 return p->va ? 0 : -1;
}
static int publish(void *ctx,const void *va,uint32_t size) {
 (void)ctx; assert(va && size==4096); npublish++; return 0;
}
static const struct fp6_gpu_global_ops ops={alloc_table,publish};
int main(void) {
 struct fp6_gpu_global_domain *d=calloc(1,sizeof(*d));
 assert(d && !fp6_gpu_global_init(d,&ops,0));
 assert(nalloc==13);
 uint64_t va0,va1; uint32_t rounded;
 assert(!fp6_gpu_global_va(d,0x3000,12,&va0,&rounded));
 assert(va0==FP6_GPU_GLOBAL_BASE && rounded==0x3000);
 assert(!fp6_gpu_global_va(d,0x3000,16,&va1,&rounded));
 assert(va1==FP6_GPU_GLOBAL_BASE+0x10000 && rounded==0x3000);
 /* Cross an L3 boundary and verify both ends through the TTBR1 walk. */
 uint64_t edge=FP6_GPU_GLOBAL_BASE+0x1ff000;
 assert(!fp6_gpu_global_map(d,edge,0x3000,0x903000000ULL,
     FP6_GPU_GLOBAL_GFX_WRITE));
 assert(fp6_gpu_global_walk(d,edge)==0x903000000ULL);
 assert(fp6_gpu_global_walk(d,edge+0x1000)==0x903001000ULL);
 assert(fp6_gpu_global_walk(d,edge+0x2fff)==0x903002fffULL);
 uint64_t *pte=(uint64_t *)(void *)d->l3[0].va;
 assert((pte[511]&0xfff)==0xe43); /* writable, unprivileged, OSH, AF, nG */
 assert((fp6_gpu_global_walk(d,edge+0x2000)&~0xfffULL)==0x903002000ULL);
 assert(fp6_gpu_global_map(d,edge,0x3000,0x903000000ULL,
     FP6_GPU_GLOBAL_GFX_WRITE)==0); /* idempotent descriptor replay */
 assert(fp6_gpu_global_map(d,edge+0x1000,0x1000,0x904000000ULL,0));
 assert(fp6_gpu_global_walk(d,edge+0x1000)==0x903001000ULL);
 assert((pte[511] & (3ULL << 53)) == (3ULL << 53)); /* data remains XN */
 uint64_t exec_va;
 assert(!fp6_gpu_global_va(d,0x1000,12,&exec_va,&rounded));
 assert(!fp6_gpu_global_map(d,exec_va,0x1000,0x906000000ULL,
     FP6_GPU_GLOBAL_GFX_PRIV | FP6_GPU_GLOBAL_GFX_EXEC));
 uint64_t exec_canonical=fp6_gpu_global_canonical(exec_va);
 unsigned exec_l3=(unsigned)((exec_canonical >> 21) & 511u);
 unsigned exec_page=(unsigned)((exec_canonical >> 12) & 511u);
 uint64_t *exec_ptes=(uint64_t *)(void *)d->l3[exec_l3].va;
 assert((exec_ptes[exec_page] & (3ULL << 53)) == 0);
 assert(fp6_gpu_global_walk(d,exec_va)==0x906000000ULL);
 assert(fp6_gpu_global_walk(d,FP6_GPU_GLOBAL_BASE+FP6_GPU_GLOBAL_SIZE)==~0ULL);
 assert(!fp6_gpu_global_publish(d) && d->frozen && npublish==13);
 /* HFI MEM_ALLOC is serviced after initial publication while firmware waits.
  * Appending a new mapping must preserve existing PTEs and permit republish. */
 assert(!fp6_gpu_global_va(d,0x1000,12,&va0,&rounded));
 assert(va0==FP6_GPU_GLOBAL_BASE+0x14000 && rounded==0x1000);
 assert(!fp6_gpu_global_map(d,va0,0x1000,0x905000000ULL,0));
 assert(fp6_gpu_global_walk(d,va0)==0x905000000ULL);
 assert(!fp6_gpu_global_publish(d) && d->frozen && npublish==26);
 return 0;
}
'''

with tempfile.TemporaryDirectory() as td:
    work = pathlib.Path(td)
    (work / "gpu_domain.h").write_text(header)
    (work / "bsd/dev").mkdir(parents=True)
    (work / "bsd/dev/fp6_gpu_global_domain.h").write_text(header)
    subprocess.run([
        "git", "apply", "--include=bsd/dev/fp6_gpu_global_domain.h",
        str(ROOT / "xnu/patches/0185-fp6-sqe-executable-mapping.patch"),
    ], cwd=work, check=True)
    header = (work / "bsd/dev/fp6_gpu_global_domain.h").read_text()
    (work / "gpu_domain.h").write_text(header)
    (work / "test.c").write_text(source)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        str(work / "test.c"), "-o", str(work / "test"),
    ], check=True)
    subprocess.run([str(work / "test")], check=True)
print("PASS: GPU global VA allocation, TTBR1 walk, data XN and SQE executable PTEs")
