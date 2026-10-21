#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "fp6_gmu_fw.h"
#include "fp6_gmu_loader.h"
static unsigned reserves, copies, words, barriers;
static int fail;
static uint8_t cache[0x15768];
static int reserve(void *c,uint32_t a,uint32_t s,int cached) {(void)c;(void)a;assert(s);assert(cached==0||cached==1);reserves++;return fail == 3;}
static int copy(void *c,uint32_t a,const uint8_t *d,uint32_t s) {(void)c;assert(a==0x4000&&s==sizeof(cache));memcpy(cache,d,s);copies++;return fail == 4;}
static int tcm(void *c,uint32_t r,uint32_t v) {(void)c;(void)v;assert((r>=0x1b400&&r<0x1c400)||(r>=0x1c400&&r<0x1d400));words++;return fail == 5;}
static int ready(void *c) {(void)c;return fail == 1;}
static int publish(void *c) {(void)c;barriers++;return fail == 6;}
int main(void) {struct fp6_gmu_loader_ops ops={reserve,copy,tcm,ready,publish};assert(fp6_gmu_loader_upload(&ops,0)==0);assert(reserves==6&&copies==1&&words==(0x1ec+0x28+0x18)/4&&barriers==1);assert(!memcmp(cache,fp6_gmu_fw_blocks[1].data,sizeof(cache)));
for (fail = 1; fail <= 6; fail++) {
 if (fail == 2) continue;
 reserves = copies = words = barriers = 0;
 assert(fp6_gmu_loader_upload(&ops,0) == -fail);
 if (fail == 1) assert(!reserves && !copies && !words && !barriers);
 if (fail == 3) assert(reserves == 1 && !copies && !words && !barriers);
 if (fail == 4 || fail == 5) assert(!barriers);
 if (fail == 6) assert(barriers == 1);
}
return 0;}
