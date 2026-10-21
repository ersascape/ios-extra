"""Run actual runtime patch callbacks against pinned firmware and MMIO model."""
import pathlib, tempfile, subprocess, importlib.util, sys
r=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fp6_runtime_fw',r/'tools/fp6-gmu-fw.py')
fw=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fw;spec.loader.exec_module(fw)
p=r/'xnu/patches/0135-fp6-gmu-runtime-upload.patch'
s='\n'.join(x[1:] for x in p.read_text().splitlines() if x.startswith('+') and not x.startswith('+++'))
s=s[:s.index('\n\tif (passed &&')].rstrip()
s=s[:s.rfind('\n\t}')]
s=s.replace('__asm__ volatile("dsb sy" ::: "memory");','')
header='\n'.join(x[1:] for x in (r/'xnu/patches/0133-fp6-gmu-persistent-domain.patch').read_text().splitlines() if x.startswith('+') and not x.startswith('+++'))
preamble=r'''
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
typedef uintptr_t vm_offset_t,vm_size_t,addr64_t;
typedef uint64_t ppnum_t;
#define PAGE_MASK 0x3fffULL
#define KMA_DATA 1
#define KMA_ZERO 2
#define KMA_PERMANENT 4
#define VM_KERN_MEMORY_IOKIT 0
#define KERN_SUCCESS 0
#define FALSE 0
#define FP6_SMMU_CB_SCTLR 0
#define FP6_SMMU_CB_TTBR0 0x20
#define FP6_SMMU_CB_TLBIALL 0x618
#define FP6_SMMU_CB_TLBSYNC 0x7f0
#define FP6_SMMU_CB_TLBSTATUS 0x7f4
#define FP6_SMMU_CB_ATS1PR 0x800
#define FP6_SMMU_CB_ATSR 0x8f0
#define FP6_SMMU_CB_PAR 0x50
static int kernel_map,kernel_pmap,mode=1,bad_clock,bad_reset,bad_ats,bad_ttbr;
static unsigned tcmwrites,cleans;
static uint8_t gpucc[0x10000],gmu[0x68000],smmu[0x40000];
struct fp6_smmu_clocks {vm_offset_t gpucc;};
static uint64_t nextpa=0x900000000ULL;
struct allocation { uintptr_t va; uint64_t pa,size; };
static struct allocation allocations[128];static unsigned count;
static int kmem_alloc_contig(int m,vm_offset_t *va,vm_size_t size,unsigned mask,int a,int b,int c,int d) {
 (void)m;(void)mask;(void)a;(void)b;(void)c;(void)d;
 *va=(uintptr_t)aligned_alloc(16384,size);assert(*va && count<128);
 allocations[count++]=(struct allocation){*va,nextpa,size};nextpa+=size;return 0;
}
static ppnum_t pmap_find_phys(int p,addr64_t va) {
 (void)p;for(unsigned i=0;i<count;i++)if(va>=allocations[i].va && va<allocations[i].va+allocations[i].size)
 return (allocations[i].pa+va-allocations[i].va)>>14;return 0;
}
#define ptoa_64(n) ((n)<<14)
static void clean_dcache64(addr64_t a,uint32_t n,int physical){assert(a&&n&&!physical);cleans++;}
static int PE_parse_boot_argn(const char *n,void *v,int size){(void)n;(void)size;*(int*)v=mode;return 1;}
static vm_offset_t ml_io_map(vm_offset_t pa,vm_size_t size){assert(pa==0x3d37000&&size==0x68000);return (uintptr_t)gmu;}
static void delay(unsigned d){(void)d;}
static uint32_t fp6_smmu_read32(vm_offset_t,uint32_t);
static uint64_t fp6_smmu_read64(vm_offset_t,uint32_t);
static void fp6_smmu_write32(vm_offset_t,uint32_t,uint32_t);
static void fp6_smmu_write64(vm_offset_t,uint32_t,uint64_t);
'''
model=r'''
static int fp6_gmu_clocks_prepare(struct fp6_smmu_clocks *c){(void)c;return !bad_clock;}
static uint32_t fp6_smmu_read32(vm_offset_t b,uint32_t o){
 if(b==(uintptr_t)gpucc && (o==0x90d4||o==0x90e4))return bad_clock?0x80000000:1;
 if(b==(uintptr_t)gmu&&o==0x47000)return bad_reset?0:1;
 return *(uint32_t*)(b+o);
}
static uint64_t fp6_smmu_read64(vm_offset_t b,uint32_t o){return *(uint64_t*)(b+o);}
static void fp6_smmu_write32(vm_offset_t b,uint32_t o,uint32_t v){
 *(uint32_t*)(b+o)=v;if(b==(uintptr_t)gmu)tcmwrites++;
}
static void fp6_smmu_write64(vm_offset_t b,uint32_t o,uint64_t v){
 *(uint64_t*)(b+o)=bad_ttbr && o==0x20020 ? 0 : v;
 if(o==0x20800){
  uint64_t par=1;
  for(unsigned i=0;i<fp6_gmu_domain.count;i++){
   struct fp6_gmu_domain_range *r=&fp6_gmu_domain.ranges[i];
   if(v>=r->address&&v<(uint64_t)r->address+r->mapped_size)par=r->backing.pa+v-r->address;
  }
  *(uint64_t*)(b+0x20050)=bad_ats?1:par;
 }
}
int main(int argc,char **argv){
 (void)argv;
 struct fp6_smmu_clocks c={(uintptr_t)gpucc};
 mode=0;assert(!fp6_gmu_persistent_upload((uintptr_t)smmu,0x20000,0x800,0,&c));assert(!count&&!tcmwrites);
 mode=1;bad_clock=1;assert(!fp6_gmu_persistent_upload((uintptr_t)smmu,0x20000,0x800,0,&c));assert(!count&&!tcmwrites);
 bad_clock=0;bad_reset=1;assert(!fp6_gmu_persistent_upload((uintptr_t)smmu,0x20000,0x800,0,&c));assert(!count&&!tcmwrites);
 bad_reset=0;
 if(argc>1){bad_ats=!strcmp(argv[1],"bad-ats");bad_ttbr=!strcmp(argv[1],"bad-ttbr");assert(!fp6_gmu_persistent_upload((uintptr_t)smmu,0x20000,0x800,0,&c));assert(!tcmwrites);puts("PASS: failed persistent translation prevents TCM writes");return 0;}
 assert(fp6_gmu_persistent_upload((uintptr_t)smmu,0x20000,0x800,0,&c));
 assert(count&&cleans&&tcmwrites==139&&fp6_gmu_domain.frozen);
 assert(!*(uint32_t*)(smmu+0x800));
 assert(*(uint64_t*)(smmu+0x20020)==fp6_gmu_domain.root.pa);
 puts("PASS: active runtime pinned firmware allocation, publication, every-page ATS and TCM readback");return 0;
}
'''
with tempfile.TemporaryDirectory() as td:
 d=pathlib.Path(td);(d/'fp6_gmu_domain.h').write_text(header)
 fw.emit_header(fw.verify_pinned_blob(pathlib.Path('/tmp/fp6-firmware/gen80300_gmu.bin').read_bytes()),d/'fp6_gmu_fw.h')
 (d/'test.c').write_text(preamble+s+model)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I',str(d),'-I',str(r/'xnu/helpers'),str(d/'test.c'),'-o',str(d/'test')],check=True)
 subprocess.run([str(d/'test')],check=True)
 subprocess.run([str(d/'test'),'bad-ats'],check=True)
 subprocess.run([str(d/'test'),'bad-ttbr'],check=True)
