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
#define kernel_pmap ((void *)1)
#define ptoa_64(pn) ((uint64_t)(pn) << 14)
#include "domain.h"
static struct fp6_gmu_domain fp6_gmu_domain;
static vm_offset_t fp6_gmu_window = 1;
#define FP6_SMMU_GMU_SID 5u
#define FP6_SMMU_CB_SCTLR 0x0000u
#define FP6_SMMU_CB_FSR 0x58u
#define FP6_SMMU_CB_TLBIALL 0x0618u
#define FP6_SMMU_CB_TLBSYNC 0x07f0u
#define FP6_SMMU_CB_TLBSTATUS 0x07f4u
#define FP6_SMMU_DUMMY_VAL 0xffffffffu
#define FP6_GMU_TEST 1
static uint32_t reset_value=1, fw_result=0x100, hfi_result=1, smr, fake_cb_sctlr=0x27;
static unsigned release_count, reset_count, route_writes, hfi_starts;
static unsigned fake_tlbi_count, fake_tlbsync_count;
static int refuse_reset;
static int PE_parse_boot_argn(const char *s, void *v, int n) {(void)s;(void)v;(void)n;return 0;}
static uint64_t fake_ticks=1000000, fake_frequency=19200000, cx_seed, cx_seed_tick;
static uint32_t cx_pending_lo;
static int cx_map_fail, irq_enabled=1, scm_available=1, scm_status;
static uint32_t fp6_cmd_db[0x20000/4], fp6_rsc[0x10000/4];
static unsigned rsc_command_count;
static int hide_acv;
static uint32_t fp6_gmu_hfi_irq;
static unsigned fp6_hfi_doorbells, fp6_hfi_cache_flushes;
static int fake_bad_hfi_ack;
static int fake_cntr_event, fake_mem_alloc_event;
static uint32_t fake_start_header;
static uint32_t fake_counter_header;
static uint32_t fake_mem_alloc_header, fake_mem_alloc_va;
static uint32_t fake_mem_alloc_flags;
static uint32_t fake_mem_alloc_handle=0xabcdu;
static uint32_t fp6_gmu_hfi_va;
static uint8_t *fp6_gmu_range_va(uint32_t);
static uint64_t fake_gmu_walk(uint32_t a) {
 unsigned i=a>>30,j=(a>>21)&511,k=(a>>12)&511;
 assert(fp6_gmu_domain.l2[i].va && fp6_gmu_domain.l3[i][j].va);
 return ((uint64_t *)fp6_gmu_domain.l3[i][j].va)[k];
}
static void flush_dcache64(uintptr_t address, unsigned count, int physical) {
 assert(address && count && !physical); fp6_hfi_cache_flushes++;
}
static void fake_hfi_reply(uint32_t *msgq, uint32_t *msg_hdr, uint32_t req, unsigned seq) {
 uint32_t ri=msg_hdr[11];
 msgq[ri]=((seq&0xfffu)<<20)|0x0001047eu;
 msgq[(ri+1u)%1024u]=req^(fake_bad_hfi_ack?(1u<<20):0u);
 msgq[(ri+2u)%1024u]=0;
 msgq[(ri+3u)%1024u]=0;
 msg_hdr[11]=(ri+4u)%1024u;
}
static unsigned cx_rate_num=1, cx_rate_den=1, cx_writes, cx_reads, cx_write_ticks=5;
static unsigned scm_calls;
static uint64_t scm_fid[2], scm_arginfo[2], scm_arg0[2];
static uint64_t fp6_gmu_test_counter(void) { return fake_ticks += 20; }
static uint64_t fp6_gmu_test_frequency(void) { return fake_frequency; }
static boolean_t ml_set_interrupts_enabled(boolean_t enable) { int old=irq_enabled;irq_enabled=enable;return old; }
static vm_offset_t ml_io_map(uint64_t a, uint32_t n) {
 (void)n;
 if(a==0x03d9e000u)return cx_map_fail?0:3;
 if(a==0x03d0f000u)return 4;
 if(a==0x81c60000u)return a;
 if(a==0x17a20000u)return a;
 return 3;
}
static void delay(int n) { if(n>0)fake_ticks+=(uint64_t)n*19200u/1000u; }
static void fp6_scm_invoke(uint64_t fid,uint64_t arginfo,uint64_t arg0,uint64_t *status,uint64_t *value) {
 assert(scm_calls<2);scm_fid[scm_calls]=fid;scm_arginfo[scm_calls]=arginfo;scm_arg0[scm_calls]=arg0;scm_calls++;
 *status=0;*value=0;if(fid==0x42000101u)*value=scm_available;else *status=scm_status;
}
static uint32_t fp6_smmu_read32(vm_offset_t b, uint32_t o) {
 if (b>=0x81c60000u && b<0x81c80000u) {
  unsigned off=(unsigned)(b-0x81c60000u)+o;
  if(hide_acv && off==328u)return 0;
  return fp6_cmd_db[off/4];
 }
 if (b>=0x17a20000u && b<0x17a30000u) return fp6_rsc[((b-0x17a20000u)+o)/4];
 if (b==2) {
  if(o==0x800)return smr;
  if(o==0x1000+FP6_SMMU_CB_SCTLR)return fake_cb_sctlr;
  return 0;
 }
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
 if (o==0x47648) return fp6_gmu_hfi_irq;
 return 0;
}
static void fp6_smmu_write32(vm_offset_t b,uint32_t o,uint32_t v) {
 if (b==2) {
  if(o==0x800){smr=v;route_writes++;return;}
  if(o==0x1000+FP6_SMMU_CB_TLBIALL){assert(v==FP6_SMMU_DUMMY_VAL);fake_tlbi_count++;return;}
  if(o==0x1000+FP6_SMMU_CB_TLBSYNC){assert(v==FP6_SMMU_DUMMY_VAL);fake_tlbsync_count++;return;}
  assert(0);
 }
 if (b==3) {
  cx_writes++;
  fake_ticks+=cx_write_ticks;if(o==0x200)cx_pending_lo=v;
  if(o==0x204){cx_seed=((uint64_t)v<<32)|cx_pending_lo;cx_seed_tick=fake_ticks;}return;
 }
 if (b==4) return;
 if (b>=0x17a20000u && b<0x17a30000u) {
  uint32_t off=(b-0x17a20000u)+o;
  fp6_rsc[off/4]=v;
  if(off>=0xd00u && (off-0xd00u)%672u==0x24u && (v&(1u<<24))) {
   uint32_t base=off-0x24u;
   for(unsigned i=0;i<3;i++) fp6_rsc[(base+0x40u+24u*i)/4]=0x10100u;
   fp6_rsc[(base+0x28u)/4]=1;
   rsc_command_count++;
  }
  return;
 }
 if (b!=1) return;
 if (o==0x47000) {
  if (!v) {release_count++;reset_value=0;}
  else {reset_count++;if(!refuse_reset)reset_value=v;}
 }
 if(o==0x47618) hfi_starts++;
 if(o==0x47644) fp6_gmu_hfi_irq=0;
 if(o==0x47650 && (v&1u)) {
  uint8_t *mem=fp6_gmu_range_va(fp6_gmu_hfi_va);
  assert(mem);
  uint32_t *table=(uint32_t *)(void *)mem;
  uint32_t *cmd_hdr=table+6, *msg_hdr=table+18;
  uint32_t *cmdq=(uint32_t *)(void *)(mem+0x350u);
  uint32_t *msgq=(uint32_t *)(void *)(mem+0x1350u);
  uint32_t wi=cmd_hdr[10]; /* prior GMU read index is the next request start */
  unsigned dwords=(cmdq[wi]>>8)&0xffu;
  unsigned rounded=(dwords+3u)&~3u;
  uint32_t req_hdr=cmdq[wi];
  unsigned id=req_hdr&0xffu, seq=(req_hdr>>20)&0xfffu;
  assert(id!=126 && dwords>=2 && rounded<1024);
  assert(seq==fp6_hfi_doorbells+1);
  assert(((req_hdr>>16)&0xfu)==((id==110u || id==20u)?1u:0u));
  if(fp6_hfi_doorbells==0) {
   assert(id==15 && dwords==19 && cmdq[(wi+1u)%1024u]==0);
   assert(cmdq[(wi+2u)%1024u]==1 && cmdq[(wi+3u)%1024u]==2 && cmdq[(wi+4u)%1024u]==3);
   assert(cmdq[(wi+5u)%1024u]==0 && cmdq[(wi+6u)%1024u]==0xffffffffu);
   assert(cmdq[(wi+8u)%1024u]==0x00400101u && cmdq[(wi+9u)%1024u]==0xffffffffu);
   assert(cmdq[(wi+10u)%1024u]==362000u);
   assert(cmdq[(wi+11u)%1024u]==3 && cmdq[(wi+12u)%1024u]==2);
   assert(cmdq[(wi+16u)%1024u]==350000u && cmdq[(wi+18u)%1024u]==650000u);
  } else if(fp6_hfi_doorbells==1) {
   assert(id==3 && dwords==160);
   assert(cmdq[(wi+1u)%1024u]==3 && cmdq[(wi+2u)%1024u]==1 && cmdq[(wi+3u)%1024u]==3);
   uint32_t ddr=(wi+32u)%1024u;
   assert(cmdq[(ddr+8u)%1024u]==0x20c3430du); /* AB=IB, SH0 width 16 */
   assert(cmdq[(ddr+9u)%1024u]==0x60c3430du); /* AB=IB, MC0 width 4 */
   assert(cmdq[(ddr+10u)%1024u]==0x60000000u); /* ACV, no premature perfmode */
  } else if(fp6_hfi_doorbells<4) {
   assert(id==11 && dwords==4);
   assert(cmdq[(wi+1u)%1024u]==(fp6_hfi_doorbells==2?1u:16u));
   assert(cmdq[(wi+2u)%1024u]==1 && cmdq[(wi+3u)%1024u]==0);
  } else if((req_hdr>>16&0xfu)==1u && id==110u) {
   assert(dwords==6u && ((req_hdr>>20)&0xfffu)==6u);
  } else if((req_hdr>>16&0xfu)==1u && id==20u) {
   assert(dwords==11u && ((req_hdr>>20)&0xfffu)==6u);
   assert(cmdq[(wi+1u)%1024u]==fake_mem_alloc_header);
   assert(cmdq[(wi+2u)%1024u]==0u && cmdq[(wi+3u)%1024u]==0u);
   assert(cmdq[(wi+4u)%1024u]==fake_mem_alloc_flags && cmdq[(wi+5u)%1024u]==2u);
   assert(cmdq[(wi+6u)%1024u]==fake_mem_alloc_handle && cmdq[(wi+7u)%1024u]==fake_mem_alloc_handle);
   fake_mem_alloc_va=cmdq[(wi+8u)%1024u];
   assert(fake_mem_alloc_va && cmdq[(wi+9u)%1024u]==4096u && cmdq[(wi+10u)%1024u]==12u);
   assert(fp6_gmu_domain.frozen && (fake_gmu_walk(fake_mem_alloc_va)&~4095ULL)==
       fp6_gmu_domain.ranges[fp6_gmu_domain.count-1].backing.pa);
   assert((fake_gmu_walk(fake_mem_alloc_va)&0xc0u)==
       ((fake_mem_alloc_flags&(1u<<4)?0u:0x40u)|(fake_mem_alloc_flags&(1u<<5)?0u:0x80u)));
  } else {
   assert(id==14 && dwords==2 && cmdq[(wi+1u)%1024u]==0);
  }
  uint32_t ri=msg_hdr[11];
  if(id==14 && fake_mem_alloc_event) {
   fake_start_header=cmdq[wi];
   msgq[ri]=(11u<<8)|20u; fake_mem_alloc_header=msgq[ri]; msgq[(ri+1u)%1024u]=1u;
   msgq[(ri+2u)%1024u]=0u; msgq[(ri+3u)%1024u]=0u;
   msgq[(ri+4u)%1024u]=fake_mem_alloc_flags; msgq[(ri+5u)%1024u]=2u;
   msgq[(ri+6u)%1024u]=0u; msgq[(ri+7u)%1024u]=fake_mem_alloc_handle;
   msgq[(ri+8u)%1024u]=0u; msgq[(ri+9u)%1024u]=4096u;
   msgq[(ri+10u)%1024u]=12u; msg_hdr[11]=(ri+12u)%1024u;
  } else if(id==14 && fake_cntr_event) {
   fake_start_header=cmdq[wi];
   msgq[ri]=(3u<<8)|110u; fake_counter_header=msgq[ri]; msgq[(ri+1u)%1024u]=7u;
   msgq[(ri+2u)%1024u]=9u; msg_hdr[11]=(ri+4u)%1024u;
  } else if((cmdq[wi]>>16&0xfu)==1u && id==20u) {
   assert(fake_mem_alloc_event && fake_start_header);
   fake_hfi_reply(msgq,msg_hdr,fake_start_header,5u);
  } else if((cmdq[wi]>>16&0xfu)==1u && id==110u) {
   assert(dwords==6u && cmdq[(wi+1u)%1024u]==fake_counter_header);
   assert(cmdq[(wi+2u)%1024u]==7u && cmdq[(wi+3u)%1024u]==9u);
   assert(cmdq[(wi+4u)%1024u]==0u && cmdq[(wi+5u)%1024u]==0u);
   fake_hfi_reply(msgq,msg_hdr,fake_start_header,5u);
  } else {
   fake_hfi_reply(msgq,msg_hdr,cmdq[wi],seq);
  }
  cmd_hdr[10]=cmd_hdr[11]; /* GMU consumed the host-to-firmware packet */
  fp6_gmu_hfi_irq=1; fp6_hfi_doorbells++;
 }
}
static int fp6_power_write(vm_offset_t b,uint32_t o,uint32_t v) {
 fp6_smmu_write32(b,o,v);return fp6_smmu_read32(b,o)==v;
}
static int fp6_power_poll(vm_offset_t b,uint32_t o,uint32_t mask,uint32_t want,unsigned count) {
 for(unsigned i=0;i<count;i++) if((fp6_smmu_read32(b,o)&mask)==want)return 1;
 return 0;
}
static void make_cmd_db(void) {
 fp6_cmd_db[1]=0x0c0330dbu;
 /* Linux cmd_db_get_header() scans all populated slave headers in order. */
 fp6_cmd_db[2]=(400u<<16)|3u; /* unrelated ARC entry precedes BCM */
 fp6_cmd_db[3]=(3u<<16)|960u;
 fp6_cmd_db[6]=(136u<<16)|5u; /* SH0/MC0/ACV/CN0 in BCM slave header */
 fp6_cmd_db[7]=(4u<<16)|880u;
 const uint32_t arc_names[3][2]={{0x2e786667u,0x006c766cu},{0x6c2e7863u,0x00006c76u},{0x6c2e786du,0x00006c76u}};
 const uint16_t arc_values[4]={0,0x40,0x80,0x100};
 for(unsigned i=0;i<3;i++) {
  unsigned e=(544u+24u*i)/4u;
  fp6_cmd_db[e]=arc_names[i][0];fp6_cmd_db[e+1]=arc_names[i][1];
  fp6_cmd_db[e+5]=(8u*i<<16)|8u;
  unsigned aux=(144u+960u+8u*i)/4u;
  fp6_cmd_db[aux]=arc_values[0]|((uint32_t)arc_values[1]<<16);
  fp6_cmd_db[aux+1]=arc_values[2]|((uint32_t)arc_values[3]<<16);
 }
 const uint32_t names[4]={0x00304853u,0x0030434du,0x00564341u,0x304e43u};
 const uint32_t addrs[4]={0x50020u,0x50030u,0x50068u,0x50078u};
 const uint32_t widths[4]={16u,4u,0u,4u}; /* fixed ACV has width zero */
 const uint32_t units[4]={1000000u,1000000u,1u,1000000u};
 const uint32_t vcds[4]={0u,0u,1u,2u};
 for(unsigned i=0;i<4;i++) {
  unsigned e=(280u+24u*i)/4u;
  fp6_cmd_db[e]=names[i];fp6_cmd_db[e+1]=0;fp6_cmd_db[e+4]=addrs[i];
  fp6_cmd_db[e+5]=(8u*i<<16)|8u;
  unsigned aux=(144u+880u+8u*i)/4u;
  fp6_cmd_db[aux]=units[i];fp6_cmd_db[aux+1]=widths[i]|(vcds[i]<<16);
 }
 fp6_rsc[0]=3u<<16;
 fp6_rsc[3]=(3u<<12)|(4u<<27); /* three ACTIVE TCSes, four commands per TCS */
 fp6_rsc[(0xd00u+0x28u)/4]=1;
}
static unsigned allocs;
static unsigned publish_count;
static int alloc_page(void *c,uint32_t n,struct fp6_gmu_domain_page *p) {
 (void)c;size_t bytes=(n+PAGE_MASK)&~(size_t)PAGE_MASK;p->va=aligned_alloc(PAGE_SIZE,bytes);if(p->va)memset(p->va,0,bytes);p->pa=0x900000000ULL+(++allocs)*0x100000ULL;return !p->va;
}
static int publish(void *c,const void *p,uint32_t n) {(void)c;(void)p;(void)n;publish_count++;return 0;}
'''
MAIN = r'''
static void run_probe(uint32_t fw, uint32_t hfi, int fail_reset) {
 fw_result=fw;hfi_result=hfi;refuse_reset=fail_reset;reset_value=1;
 fp6_gmu_hfi_irq=0;fp6_hfi_doorbells=fp6_hfi_cache_flushes=0;
 fake_tlbi_count=fake_tlbsync_count=0;fake_mem_alloc_va=0;
 fake_start_header=fake_counter_header=0;
 release_count=reset_count=route_writes=hfi_starts=0;
 scm_calls=0;scm_available=1;scm_status=0;
 fp6_gmu_first_boot(2,0x1000,0x800);
 assert(release_count==1 && reset_count==1);
 assert(reset_value==(fail_reset ? 0u : 1u));
 /* Even an unverified reset must never unroute or disable the DMA context. */
 assert(route_writes==1 && smr==0x80000005u);
 assert(hfi_starts==((fw==0x100)?1u:0u));
 unsigned expected=(fake_bad_hfi_ack?1u:5u)+(fake_cntr_event?1u:0u);
 if(fake_mem_alloc_event)expected=6u;
 if(fake_mem_alloc_event && (fake_mem_alloc_flags&1u))expected=5u;
 assert(fp6_hfi_doorbells==((fw==0x100 && hfi==1)?expected:0u));
 unsigned flushes=(fake_bad_hfi_ack?2u:10u)+(fake_cntr_event?2u:0u);
 if(fake_mem_alloc_event)flushes+=2u;
 if(fake_mem_alloc_event && (fake_mem_alloc_flags&1u))flushes=10u;
 assert(fp6_hfi_cache_flushes==((fw==0x100 && hfi==1)?flushes:0u));
}
int main(void) {
 setbuf(stdout,NULL);
 make_cmd_db();
 static const struct fp6_gmu_domain_ops ops={alloc_page,publish};
 assert(!fp6_gmu_domain_init(&fp6_gmu_domain,&ops,0));
 assert(!fp6_gmu_boot_reserve());
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
 hide_acv=1;reset_value=1;release_count=reset_count=route_writes=hfi_starts=0;scm_calls=0;
 unsigned commands_before_missing_acv=rsc_command_count;
 fp6_gmu_first_boot(2,0x1000,0x800);
 assert(release_count==0 && rsc_command_count==commands_before_missing_acv);
 hide_acv=0;
 fp6_cmd_db[(144u+880u+4u)/4u]=0; /* variable SH0 must have a nonzero width */
 reset_value=1;release_count=reset_count=route_writes=hfi_starts=0;scm_calls=0;
 fp6_gmu_first_boot(2,0x1000,0x800);
 assert(release_count==0 && rsc_command_count==commands_before_missing_acv);
 fp6_cmd_db[(144u+880u+4u)/4u]=16u;
 reset_value=1;release_count=reset_count=route_writes=hfi_starts=0;scm_calls=0;
 fp6_gmu_first_boot(2,0x1000,0x800);
 assert(route_writes==1 && release_count==1 && hfi_starts==1);
 assert(rsc_command_count==1);
 assert(fp6_rsc[(0xd00u+0x38u)/4]==0x50020u);
 assert(fp6_rsc[(0xd00u+0x3cu)/4]==0x20000858u); /* 2,136,718 kB/s -> 2,136 votes */
 assert(fp6_rsc[(0xd00u+0x38u+24u)/4]==0x50030u);
 assert(fp6_rsc[(0xd00u+0x3cu+24u)/4]==0x60000858u);
 assert(fp6_rsc[(0xd00u+0x38u+48u)/4]==0x50068u);
 assert(fp6_rsc[(0xd00u+0x3cu+48u)/4]==0x60000000u);
 unsigned published_before=publish_count;
 assert(!fp6_gmu_domain_publish(&fp6_gmu_domain));
 assert(publish_count>published_before); /* CPU-initialized HFI buffers are cleaned before GMU access */
 run_probe(0x100,1,0); /* successful HFI still stops */
 fake_cntr_event=1;
 run_probe(0x100,1,0); /* GMU counter event gets a zero-offset service ACK; START completes */
 fake_cntr_event=0;
 fake_bad_hfi_ack=1;
 run_probe(0x100,1,0); /* mismatched HFI ACK sequence fails closed */
 fake_bad_hfi_ack=0;
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
 fake_mem_alloc_event=1;
 run_probe(0x100,1,0); /* GMU-only request is backed, mapped, flushed, ACKed, then START completes */
 assert(fake_mem_alloc_va && fake_tlbi_count==1 && fake_tlbsync_count==1);
 assert((fake_gmu_walk(fake_mem_alloc_va)&0xc0u)==0xc0u); /* Linux default: read-only, unprivileged */
 fake_mem_alloc_flags=(1u<<4)|(1u<<5); /* GMU privileged read/write permissions */
 fake_mem_alloc_handle=0xabceu;
 run_probe(0x100,1,0);
 assert(fake_mem_alloc_va && (fake_gmu_walk(fake_mem_alloc_va)&0xc0u)==0);
 fake_mem_alloc_flags=1u; /* GPU-accessible request must not receive a fabricated GPU address */
 fake_mem_alloc_handle=0xabcfu;
 run_probe(0x100,1,0);
 assert(!fake_mem_alloc_va && fake_tlbi_count==0 && fake_tlbsync_count==0);
 fake_mem_alloc_flags=0;
 fake_mem_alloc_event=0;
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
    assert 'pmap_set_cache_attributes(' not in source
    region=source[source.index('#define FP6_GMU_HFI_SIZE'):source.index('/* Called only after temporary ATS passes.')]
    region=region.replace('__asm__ volatile("dsb sy" ::: "memory");','')
    patch=(ROOT/'xnu/patches/0133-fp6-gmu-persistent-domain.patch').read_text()
    (work/'domain.h').write_text('\n'.join(x[1:] for x in patch.splitlines() if x.startswith('+') and not x.startswith('+++'))+'\n')
    (work/'test.c').write_text(HARNESS+region+MAIN)
    flags=os.environ.get('IOS_EXTRA_CFLAGS','').split()
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',*flags,str(work/'test.c'),'-o',str(work/'test')],check=True)
    subprocess.run([str(work/'test')],check=True)
print('PASS: GMU trace header, firmware fault priority, bounded success and failed-reset DMA lifetime')
