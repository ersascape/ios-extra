#!/usr/bin/env python3
"""Check persistent multi-level GMU mappings, lifetime and publication failures."""
import pathlib, subprocess, tempfile
root = pathlib.Path(__file__).resolve().parents[1]
patch = (root/'xnu/patches/0133-fp6-gmu-persistent-domain.patch').read_text()
header = '\n'.join(x[1:] for x in patch.splitlines() if x.startswith('+') and not x.startswith('+++'))+'\n'
source = r'''
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "domain.h"
static unsigned allocations, publishes, fail_alloc, fail_publish;
static int alloc(void *c, uint32_t size, struct fp6_gmu_domain_page *p) {
 (void)c; if (++allocations == fail_alloc) return -1;
 p->va=aligned_alloc(4096,size); p->pa=0x900000000ULL+(uint64_t)allocations*0x1000000;
 return p->va ? 0 : -1;
}
static int publish(void *c,const void *p,uint32_t size) {
 (void)c; assert(p && size); return ++publishes==fail_publish ? -1:0;
}
static const struct fp6_gmu_domain_ops ops={alloc,publish};
static uint64_t walk(struct fp6_gmu_domain *d,uint32_t a) {
 unsigned i=a>>30,j=(a>>21)&511,k=(a>>12)&511;
 assert((((uint64_t*)d->root.va)[i]&~4095ULL)==d->l2[i].pa);
 assert((((uint64_t*)d->l2[i].va)[j]&~4095ULL)==d->l3[i][j].pa);
 return ((uint64_t*)d->l3[i][j].va)[k];
}
int main(void) {
 struct fp6_gmu_domain *d=calloc(1,sizeof(*d)); assert(!fp6_gmu_domain_init(d,&ops,0));
 /* Exercise an L2 boundary and a separate top-level branch. */
 assert(!fp6_gmu_domain_reserve_access(d,0x1ff000,0x3000,1,0,1));
 assert(!fp6_gmu_domain_reserve_access(d,0xc0000000,0x1000,0,1,0));
 uint64_t pa=d->ranges[0].backing.pa;
 assert((walk(d,0x1ff000)&~4095ULL)==pa);
 assert((walk(d,0x201000)&~4095ULL)==pa+8192);
 assert((walk(d,0x1ff000)&0xfff)==0xe83); /* nG, read-only, privileged */
 assert((walk(d,0xc0000000)&0xfff)==0xe43); /* nG, read/write, unprivileged */
 unsigned n=allocations; assert(!fp6_gmu_domain_reserve_access(d,0x1ff000,0x3000,1,0,1));assert(n==allocations);
 assert(fp6_gmu_domain_reserve_access(d,0x1ff000,0x3000,1,1,1));
 assert(fp6_gmu_domain_reserve(d,0x200000,4096,1));
 uint8_t payload[]={1,2,3,4};
 assert(!fp6_gmu_domain_copy(d,0x1ffffe,payload,4));
 assert(d->ranges[0].backing.va[4094]==1 && d->ranges[0].backing.va[4097]==4);
 assert(fp6_gmu_domain_copy(d,0x201ffe,payload,4));
 assert(!fp6_gmu_domain_publish(d)); assert(d->frozen && publishes==8);
 assert(fp6_gmu_domain_copy(d,0x1ff000,payload,4));
 assert(fp6_gmu_domain_reserve(d,0x800000,4096,0));
 assert(fp6_gmu_domain_init(d,&ops,0));
 d=calloc(1,sizeof(*d));assert(!fp6_gmu_domain_init(d,&ops,0));fail_alloc=allocations+2;
 assert(fp6_gmu_domain_reserve(d,0x60000000,4096,0));assert(d->failed && d->count==1);
 assert(fp6_gmu_domain_publish(d));
 fail_alloc=0;d=calloc(1,sizeof(*d));assert(!fp6_gmu_domain_init(d,&ops,0));
 assert(!fp6_gmu_domain_reserve(d,0x60000000,4096,0));fail_publish=publishes+2;
 assert(fp6_gmu_domain_publish(d));assert(d->failed && !d->frozen);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 p=pathlib.Path(td);(p/'domain.h').write_text(header);(p/'test.c').write_text(source)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('PASS: persistent GMU domain mapping, overlap, publication and failure lifetime')
# Exercise the same loader callbacks against verified pinned firmware rather
# than merely supplying page-aligned synthetic descriptors.
firmware=pathlib.Path('/tmp/fp6-firmware/gen80300_gmu.bin')
if firmware.exists():
 import importlib.util, sys
 spec=importlib.util.spec_from_file_location('fp6_domain_fw',root/'tools/fp6-gmu-fw.py')
 fw=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fw;spec.loader.exec_module(fw)
 integration=source[:source.index('int main(void)')]+r'''
#include "fp6_gmu_fw.h"
#include "fp6_gmu_loader.h"
static unsigned tcm;
static int ready(void *c) { (void)c;return 0; }
static int write_tcm(void *c,uint32_t reg,uint32_t value) {
 (void)c;(void)value;assert(reg>=0x1b400 && reg<0x1d400);tcm++;return 0;
}
int main(void) {
 struct fp6_gmu_domain *d=calloc(1,sizeof(*d));assert(!fp6_gmu_domain_init(d,&ops,0));
 struct fp6_gmu_loader_ops loader={fp6_gmu_domain_reserve,fp6_gmu_domain_copy,write_tcm,ready,fp6_gmu_domain_publish};
 assert(!fp6_gmu_loader_upload(&loader,d));assert(d->frozen && !d->failed && tcm);
 for(unsigned i=0;i<FP6_GMU_FW_BLOCK_COUNT;i++) {
  const struct fp6_gmu_fw_block *b=&fp6_gmu_fw_blocks[i];
  int kind=fp6_gmu_loader_vma(b->address,b->size);
  if(kind!=2 && kind!=4)continue;
  unsigned j;
  for(j=0;j<d->count;j++) {
   struct fp6_gmu_domain_range *r=&d->ranges[j];
   if(b->address>=r->address && (uint64_t)b->address+b->size<=(uint64_t)r->address+r->size) {
    assert(!memcmp(r->backing.va+b->address-r->address,b->data,b->size));
    assert((walk(d,b->address)&~4095ULL)==r->backing.pa+((b->address-r->address)&~4095u));
    break;
   }
  }
  assert(j<d->count);
 }
 return 0;
}
'''
 with tempfile.TemporaryDirectory() as td:
  p=pathlib.Path(td);(p/'domain.h').write_text(header)
  fw.emit_header(fw.verify_pinned_blob(firmware.read_bytes()),p/'fp6_gmu_fw.h')
  (p/'test.c').write_text(integration)
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(root/'xnu/helpers'),str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
 print('PASS: pinned Gen8.3 firmware loader to persistent domain, payload/PTE verification')
else:
 print('SKIP: pinned local firmware unavailable; integration not established')
