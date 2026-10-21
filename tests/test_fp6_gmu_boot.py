#!/usr/bin/env python3
"""Execute the patched bounded GMU probe with firmware/reset fault injection."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef uintptr_t vm_offset_t;
#include "domain.h"
static struct fp6_gmu_domain fp6_gmu_domain;
static vm_offset_t fp6_gmu_window = 1;
#define FP6_SMMU_GMU_SID 5u
#define FP6_SMMU_CB_FSR 0x58u
static uint32_t reset_value=1, fw_result=0x100, hfi_result=1, smr;
static unsigned release_count, reset_count, route_writes, hfi_starts;
static int refuse_reset;
static int PE_parse_boot_argn(const char *s, void *v, int n) {(void)s;(void)v;(void)n;return 0;}
static vm_offset_t ml_io_map(uint64_t a, uint32_t n) {(void)a;(void)n;return 3;}
static void delay(int n) {(void)n;}
static uint32_t fp6_smmu_read32(vm_offset_t b, uint32_t o) {
 if (b==2) return o==0x800 ? smr : 0;
 if (b!=1) return 0;
 if (o==0x47000) return reset_value;
 if (o==0x47070) return fw_result;
 if (o==0x47600) return hfi_result;
 return 0;
}
static void fp6_smmu_write32(vm_offset_t b,uint32_t o,uint32_t v) {
 if (b==2) { assert(o==0x800); smr=v;route_writes++;return; }
 if (b!=1) return;
 if (o==0x47000) {
  if (!v) {release_count++;reset_value=0;}
  else {reset_count++;if(!refuse_reset)reset_value=v;}
 }
 if(o==0x47618) hfi_starts++;
}
static unsigned allocs;
static int alloc_page(void *c,uint32_t n,struct fp6_gmu_domain_page *p) {
 (void)c;p->va=aligned_alloc(4096,n);if(p->va)memset(p->va,0,n);p->pa=0x900000000ULL+(++allocs)*0x100000ULL;return !p->va;
}
static int publish(void *c,const void *p,uint32_t n) {(void)c;(void)p;(void)n;return 0;}
'''
MAIN = r'''
static void run_probe(uint32_t fw, uint32_t hfi, int fail_reset) {
 fw_result=fw;hfi_result=hfi;refuse_reset=fail_reset;reset_value=1;
 release_count=reset_count=route_writes=hfi_starts=0;
 fp6_gmu_first_boot(2,0x1000,0x800);
 assert(release_count==1 && reset_count==1);
 assert(reset_value==(fail_reset ? 0u : 1u));
 /* Even an unverified reset must never unroute or disable the DMA context. */
 assert(route_writes==1 && smr==0x80000005u);
 assert(hfi_starts==((fw==0x100)?1u:0u));
}
int main(void) {
 static const struct fp6_gmu_domain_ops ops={alloc_page,publish};
 assert(!fp6_gmu_domain_init(&fp6_gmu_domain,&ops,0));
 assert(!fp6_gmu_boot_reserve());
 uint32_t *vrb=(uint32_t *)(void *)fp6_gmu_range_va(fp6_gmu_vrb_va);
 uint32_t *trace=(uint32_t *)(void *)fp6_gmu_range_va(vrb[2]);
 assert(trace && vrb[2]==fp6_gmu_trace_va);
 assert(trace[1]==0x40000001 && trace[2]==80 && trace[3]==16384);
 assert(trace[8]==fp6_gmu_trace_va && trace[9]==0 && trace[10]==5 && trace[11]==1);
 assert(!fp6_gmu_domain_publish(&fp6_gmu_domain));
 run_probe(0x100,1,0); /* successful HFI still stops */
 run_probe(0x100,1,1); /* reset write rejected */
 run_probe(0x300,1,0); /* success bits plus firmware assert must fail */
 run_probe(0x100,0,0); /* HFI timeout */
 run_probe(0,0,0);     /* firmware timeout */
 (void)fp6_gmu_boot_wanted;
 (void)fp6_gmu_domain_copy;
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='fp6-gmu-boot-') as td:
    work=Path(td)
    for patch in sorted((ROOT/'xnu/patches').glob('*.patch')):
        if b'+++ b/bsd/dev/sweet_gpu.c\n' in patch.read_bytes():
            subprocess.run(['git','apply','--include=bsd/dev/sweet_gpu.c',str(patch)],cwd=work,check=True)
    source=(work/'bsd/dev/sweet_gpu.c').read_text()
    region=source[source.index('#define FP6_GMU_HFI_SIZE'):source.index('/* Called only after temporary ATS passes.')]
    region=region.replace('__asm__ volatile("dsb sy" ::: "memory");','')
    patch=(ROOT/'xnu/patches/0133-fp6-gmu-persistent-domain.patch').read_text()
    (work/'domain.h').write_text('\n'.join(x[1:] for x in patch.splitlines() if x.startswith('+') and not x.startswith('+++'))+'\n')
    (work/'test.c').write_text(HARNESS+region+MAIN)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(work/'test.c'),'-o',str(work/'test')],check=True)
    subprocess.run([str(work/'test')],check=True)
print('PASS: GMU trace header, firmware fault priority, bounded success and failed-reset DMA lifetime')
