#!/usr/bin/env python3
"""Execute the patched bounded GMU probe with firmware/reset fault injection."""
from pathlib import Path
import os
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
typedef size_t vm_size_t;
typedef uintptr_t addr64_t;
typedef int boolean_t;
typedef uint64_t ppnum_t;
#define FALSE 0
#define PAGE_SIZE 0x4000u
#define PAGE_MASK (PAGE_SIZE-1u)
#define VM_WIMG_MASK 0xffu
#define VM_WIMG_DEFAULT 0x2u
#define VM_WIMG_WCOMB 0x6u
#define kernel_pmap ((void *)1)
#define ptoa_64(pn) ((uint64_t)(pn) << 14)
#include "domain.h"
static struct fp6_gmu_domain fp6_gmu_domain;
static vm_offset_t fp6_gmu_window = 1;
#define FP6_SMMU_GMU_SID 5u
#define FP6_SMMU_CB_FSR 0x58u
#define FP6_GMU_TEST 1
static uint32_t reset_value=1, fw_result=0x100, hfi_result=1, smr;
static unsigned release_count, reset_count, route_writes, hfi_starts;
static int refuse_reset;
static int PE_parse_boot_argn(const char *s, void *v, int n) {(void)s;(void)v;(void)n;return 0;}
static uint64_t fake_ticks=1000000, fake_frequency=19200000, cx_seed, cx_seed_tick;
static uint32_t cx_pending_lo;
static int cx_map_fail, irq_enabled=1, scm_available=1, scm_status;
static unsigned cx_rate_num=1, cx_rate_den=1, cx_writes, cx_reads, cx_write_ticks=5;
static unsigned scm_calls;
static uint64_t scm_fid[2], scm_arginfo[2], scm_arg0[2];
static uint64_t fp6_gmu_test_counter(void) { return fake_ticks += 20; }
static uint64_t fp6_gmu_test_frequency(void) { return fake_frequency; }
static boolean_t ml_set_interrupts_enabled(boolean_t enable) { int old=irq_enabled;irq_enabled=enable;return old; }
static vm_offset_t ml_io_map(uint64_t a, uint32_t n) {
 (void)n;if(a==0x03d9e000u)return cx_map_fail?0:3;if(a==0x03d0f000u)return 4;return 3;
}
static void delay(int n) { if(n>0)fake_ticks+=(uint64_t)n*19200u/1000u; }
static void fp6_scm_invoke(uint64_t fid,uint64_t arginfo,uint64_t arg0,uint64_t *status,uint64_t *value) {
 assert(scm_calls<2);scm_fid[scm_calls]=fid;scm_arginfo[scm_calls]=arginfo;scm_arg0[scm_calls]=arg0;scm_calls++;
 *status=0;*value=0;if(fid==0x42000101u)*value=scm_available;else *status=scm_status;
}
static uint32_t fp6_smmu_read32(vm_offset_t b, uint32_t o) {
 if (b==2) return o==0x800 ? smr : 0;
 if (b==3) {
  cx_reads++;
  uint64_t value=cx_seed+(fake_ticks-cx_seed_tick)*cx_rate_num/cx_rate_den;
  if(o==0x200) return (uint32_t)value;
  if(o==0x204) return (uint32_t)(value>>32);
  return 0;
 }
 if (b!=1) return 0;
 if (o==0x47000) return reset_value;
 if (o==0x47070) return fw_result;
 if (o==0x47600) return hfi_result;
 return 0;
}
static void fp6_smmu_write32(vm_offset_t b,uint32_t o,uint32_t v) {
 if (b==2) { assert(o==0x800); smr=v;route_writes++;return; }
 if (b==3) {
  cx_writes++;
  fake_ticks+=cx_write_ticks;if(o==0x200)cx_pending_lo=v;
  if(o==0x204){cx_seed=((uint64_t)v<<32)|cx_pending_lo;cx_seed_tick=fake_ticks;}return;
 }
 if (b==4) return;
 if (b!=1) return;
 if (o==0x47000) {
  if (!v) {release_count++;reset_value=0;}
  else {reset_count++;if(!refuse_reset)reset_value=v;}
 }
 if(o==0x47618) hfi_starts++;
}
static unsigned allocs;
static unsigned cache_set_count;
static struct { ppnum_t pn; unsigned attr; } cache_attrs[16];
static ppnum_t pmap_find_phys(void *map, addr64_t va) {
 (void)map;return (ppnum_t)(va >> 14);
}
static unsigned pmap_cache_attributes(ppnum_t pn) {
 for(unsigned i=0;i<16;i++)if(cache_attrs[i].pn==pn)return cache_attrs[i].attr;
 return VM_WIMG_DEFAULT;
}
static void pmap_set_cache_attributes(ppnum_t pn,unsigned attr) {
 for(unsigned i=0;i<16;i++)if(cache_attrs[i].pn==pn){cache_attrs[i].attr=attr;cache_set_count++;return;}
 for(unsigned i=0;i<16;i++)if(!cache_attrs[i].pn){cache_attrs[i].pn=pn;cache_attrs[i].attr=attr;cache_set_count++;return;}
 assert(0);
}
static int alloc_page(void *c,uint32_t n,struct fp6_gmu_domain_page *p) {
 (void)c;size_t bytes=(n+PAGE_MASK)&~(size_t)PAGE_MASK;p->va=aligned_alloc(PAGE_SIZE,bytes);if(p->va)memset(p->va,0,bytes);p->pa=0x900000000ULL+(++allocs)*0x100000ULL;return !p->va;
}
static int publish(void *c,const void *p,uint32_t n) {(void)c;(void)p;(void)n;return 0;}
'''
MAIN = r'''
static void run_probe(uint32_t fw, uint32_t hfi, int fail_reset) {
 fw_result=fw;hfi_result=hfi;refuse_reset=fail_reset;reset_value=1;
 release_count=reset_count=route_writes=hfi_starts=0;
 scm_calls=0;scm_available=1;scm_status=0;
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
 assert(cache_set_count==5);
 for(unsigned i=0;i<5;i++)assert(cache_attrs[i].attr==VM_WIMG_WCOMB);
 uint32_t *vrb=(uint32_t *)(void *)fp6_gmu_range_va(fp6_gmu_vrb_va);
 uint32_t *trace=(uint32_t *)(void *)fp6_gmu_range_va(vrb[2]);
 assert(trace && vrb[2]==fp6_gmu_trace_va);
 assert(trace[1]==0x40000001 && trace[2]==80 && trace[3]==16384);
 assert(trace[8]==fp6_gmu_trace_va && trace[9]==0 && trace[10]==5 && trace[11]==1);
 assert(fp6_gmu_cx_timer_sync());
 assert(fp6_gmu_cx_timer_ready && irq_enabled && cx_seed != 0);
 fp6_gmu_cx_timer_ready=0;cx_write_ticks=0;
 assert(fp6_gmu_cx_timer_sync()); /* timer-tick quantization can make measured skew exactly zero */
 assert(fp6_gmu_cx_timer_ready && irq_enabled);
 cx_write_ticks=5;
 unsigned timer_writes=cx_writes;
 fp6_gmu_cx_timer_ready=0;fake_frequency=0;
 assert(!fp6_gmu_cx_timer_sync() && cx_writes==timer_writes && irq_enabled);
 fake_frequency=19200000;
 fp6_gmu_cx_timer_ready=0;cx_map_fail=1;
 assert(!fp6_gmu_cx_timer_sync() && !fp6_gmu_cx_timer_ready && irq_enabled);
 cx_rate_num=0;cx_rate_den=1; /* phone-measured CX counter remains static after seed */
 cx_map_fail=1;
 reset_value=1;release_count=reset_count=route_writes=hfi_starts=0;scm_calls=0;
 fp6_gmu_first_boot(2,0x1000,0x800);
 assert(route_writes==0 && release_count==0 && scm_calls==0);
 cx_map_fail=0;cx_reads=0;fp6_gmu_cx_timer_ready=0;
 int timer_ok=fp6_gmu_cx_timer_sync();
 assert(timer_ok && fp6_gmu_cx_timer_ready && cx_reads==0 && cx_seed!=0);
 reset_value=1;release_count=reset_count=route_writes=hfi_starts=0;scm_calls=0;
 fp6_gmu_first_boot(2,0x1000,0x800);
 assert(route_writes==1 && release_count==1 && hfi_starts==1);
 unsigned cache_sets_before_publish=cache_set_count;
 assert(!fp6_gmu_domain_publish(&fp6_gmu_domain));
 assert(cache_set_count==cache_sets_before_publish);
 assert(fp6_gmu_hfi_set_wcomb(&fp6_gmu_domain,fp6_gmu_hfi_va));
 assert(cache_set_count==cache_sets_before_publish); /* frozen domain: no cache mutation */
 run_probe(0x100,1,0); /* successful HFI still stops */
 run_probe(0x100,1,1); /* reset write rejected */
 run_probe(0x300,1,0); /* success bits plus firmware assert must fail */
 run_probe(0x100,0,0); /* HFI timeout */
 run_probe(0,0,0);     /* firmware timeout */
 reset_value=1;release_count=reset_count=route_writes=hfi_starts=0;
 scm_calls=0;scm_available=1;scm_status=1;
 fp6_gmu_first_boot(2,0x1000,0x800);
 assert(scm_calls==2 && route_writes==0 && release_count==0 && reset_count==0);
 assert(scm_fid[0]==0x42000101u && scm_arginfo[0]==1 && scm_arg0[0]==0x02002801u);
 assert(scm_fid[1]==0x42002801u && scm_arginfo[1]==1 && scm_arg0[1]==9);
 reset_value=1;release_count=reset_count=route_writes=hfi_starts=0;
 scm_calls=0;scm_available=0;scm_status=0;
 fp6_gmu_first_boot(2,0x1000,0x800);
 assert(scm_calls==1 && route_writes==1 && release_count==1);
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
    flags=os.environ.get('IOS_EXTRA_CFLAGS','').split()
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',*flags,str(work/'test.c'),'-o',str(work/'test')],check=True)
    subprocess.run([str(work/'test')],check=True)
print('PASS: GMU trace header, firmware fault priority, bounded success and failed-reset DMA lifetime')
