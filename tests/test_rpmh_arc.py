"""Run the real sweet_rpmh.c against a simulated RSC, TCS bank and command DB.

Only the ARM barriers are removed and the MMIO store is routed through a test
hook that models trigger completion and write-one-to-clear. The same source is
cross-compiled separately against XNU headers. Covers the display LDO vote
(must be unchanged by the ARC work) and the ARC level-index votes.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RpmhArcTests(unittest.TestCase):
    def test_votes(self):
        with tempfile.TemporaryDirectory(prefix='ios-extra-rpmh-test-') as directory:
            work = Path(directory)
            for patch in sorted((ROOT / 'xnu/patches').glob('*.patch')):
                if b'+++ b/bsd/dev/sweet_rpmh.c\n' in patch.read_bytes():
                    subprocess.run(['git', 'apply', '--include=bsd/dev/sweet_rpmh.c',
                                    str(patch)], cwd=work, check=True)
            source = (work / 'bsd/dev/sweet_rpmh.c').read_text()
            for text in ('__asm__ volatile("dmb oshld" ::: "memory");',
                         '__asm__ volatile("dmb oshst" ::: "memory");',
                         '__asm__ volatile("dsb osh" ::: "memory");'):
                self.assertEqual(source.count(text), 1)
                source = source.replace(text, '')
            store = '*(volatile uint32_t *)(base + off) = value;'
            self.assertEqual(source.count(store), 1)
            source = source.replace(store, 'test_store(base, off, value);')
            (work / 'sweet_rpmh.c').write_text(source)
            headers = {
                'sys/param.h': '#include <stdint.h>\n#include <stdbool.h>\n#include <string.h>\n'
                               'typedef uintptr_t vm_offset_t;\ntypedef uintptr_t vm_size_t;\n',
                'sys/systm.h': '',
                'sys/errno.h': '#include <errno.h>\n',
                'kern/clock.h': 'void delay(int);\n',
                'machine/machine_routines.h': '',
            }
            for name, text in headers.items():
                path = work / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            (work / 'test.c').write_text(HARNESS)
            build = subprocess.run([shutil.which('cc') or 'cc', '-std=c11', '-Wall',
                                    '-Wextra', '-Werror', *os.environ.get('IOS_EXTRA_CFLAGS', '').split(), '-I', str(work),
                                    str(work / 'test.c'), '-o', str(work / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([str(work / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('PASS: rpmh LDO + ARC cases', result.stdout)


HARNESS = r'''
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>

#include <sys/param.h>
static void test_store(vm_offset_t base, uint32_t off, uint32_t value);
static int rpmh_printf(const char *, ...);
#define printf rpmh_printf
#define ARM64_BOARD_CONFIG_SWEET 1
#include "sweet_rpmh.c"
#undef printf

static uint32_t rsc[0x100 / 4], tcs[RH_TCS_SIZE / 4], dict[2], db[256];
static unsigned map_calls;
static struct { uint32_t addr, data; } sent[8];
static unsigned nsent, triggers;
static char output[65536];

static int rpmh_printf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    size_t used = strlen(output);
    int count = vsnprintf(output + used, sizeof(output) - used, fmt, ap);
    va_end(ap);
    assert(count >= 0 && (size_t)count < sizeof(output) - used);
    return count;
}

void delay(int us) { (void)us; }

vm_offset_t ml_io_map(vm_offset_t pa, vm_size_t size)
{
    map_calls++;
    if (pa == RH_RSC_PA && size == 0x100) return (vm_offset_t)rsc;
    if (pa == RH_TCS_PA && size == RH_TCS_SIZE) return (vm_offset_t)tcs;
    if (pa == RH_DICT_PA && size == 8) return (vm_offset_t)dict;
    if (pa == 0x85fe0000u && size == sizeof(db)) return (vm_offset_t)db;
    assert(!"unexpected mapping");
    return 0;
}

static void test_store(vm_offset_t base, uint32_t off, uint32_t value)
{
    uint32_t *words = (uint32_t *)base;
    words[off / 4] = value;
    if (base != (vm_offset_t)tcs) return;
    if (off == RH_IRQ_CLEAR) {
        tcs[RH_IRQ_STATUS / 4] &= ~value;
        return;
    }
    for (unsigned t = 0; t < RH_ACTIVE_N; t++) {
        uint32_t b = t * RH_TCS_STRIDE;
        if (off == b + RH_CONTROL && (value & RH_TRIGGER)) {
            uint32_t enable = tcs[(b + RH_ENABLE) / 4];
            triggers++;
            for (unsigned c = 0; c < 3; c++) {
                if (!(enable & (1u << c))) continue;
                assert(nsent < 8);
                sent[nsent].addr = tcs[(b + RH_ADDR + c * RH_CMD_STRIDE) / 4];
                sent[nsent++].data = tcs[(b + RH_DATA + c * RH_CMD_STRIDE) / 4];
                tcs[(b + RH_CMD_STATUS + c * RH_CMD_STRIDE) / 4] = RH_ISSUED | RH_COMPLETE;
            }
            tcs[RH_IRQ_STATUS / 4] |= 1u << t;
        }
    }
}

static void db16(unsigned off, uint16_t v)
{
    unsigned char *b = (unsigned char *)db;
    assert(off + 2 <= sizeof(db));
    b[off] = v & 255; b[off + 1] = v >> 8;
}

static void db32(unsigned off, uint32_t v) { assert(!(off & 3)); db[off / 4] = v; }

static void entry(unsigned off, const char *name, uint32_t addr, unsigned len, unsigned aux)
{
    unsigned char *b = (unsigned char *)db;
    memset(b + off, 0, 24);
    memcpy(b + off, name, strlen(name));
    db32(off + 16, addr); db16(off + 20, len); db16(off + 22, aux);
}

static void table(unsigned off, const uint16_t *v, unsigned count)
{
    for (unsigned i = 0; i < count; i++) db16(off + 2 * i, v[i]);
}

#define AUX 272u /* absolute: 144 + 128 */
static const uint16_t cx_levels[16] = {0, 16, 64, 128, 192, 256};
static const uint16_t mx_levels[16] = {0, 16, 192, 320, 384};

static void reset(void)
{
    memset(rsc, 0, sizeof(rsc)); memset(tcs, 0, sizeof(tcs)); memset(db, 0, sizeof(db));
    rsc[0] = 0x00020000u; rsc[1] = 1; rsc[3] = (8u << (6 * RH_DRV)) | (3u << 27);
    for (unsigned t = 0; t < 18; t++) tcs[(t * RH_TCS_STRIDE + RH_STATUS) / 4] = 1;
    dict[0] = 0x85fe0000u; dict[1] = sizeof(db);
    db32(0, 1); db32(4, RH_DB_MAGIC);
    /* slave 3 (ARC): 2 entries at data+0; slave 4 (VRM): 1 entry at data+48 */
    db16(8, 3); db16(10, 0); db16(12, 128); db16(14, 2); db16(16, 0x1000);
    db16(24, 4); db16(26, 48); db16(28, 128); db16(30, 1); db16(32, 0x100);
    entry(144, "cx.lvl", 0x30000, 32, 0);
    entry(168, "mx.lvl", 0x30010, 32, 32);
    entry(192, "ldoc11", 0x40000, 0, 64);
    table(AUX, cx_levels, 16); table(AUX + 32, mx_levels, 16);
    memset(sent, 0, sizeof(sent)); nsent = triggers = 0; map_calls = 0;
    rh_rsc = rh_tcs = rh_dict = rh_db = 0; rh_db_size = 0; rh_poisoned = false; rh_lock = 0;
    output[0] = 0;
}

static void assert_idle(void)
{
    assert(rh_lock == 0 && !rh_poisoned);
    for (unsigned t = 0; t < RH_ACTIVE_N; t++) {
        uint32_t b = t * RH_TCS_STRIDE;
        assert(tcs[(b + RH_CONTROL) / 4] == 0 && tcs[(b + RH_ENABLE) / 4] == 0 &&
               tcs[(b + RH_WAIT) / 4] == 0);
    }
    assert(!tcs[RH_IRQ_STATUS / 4]);
}

int main(void)
{
    unsigned level = 99;
    /* Display LDO vote: three commands, same addresses/data as before ARC. */
    reset();
    assert(sweet_rpmh_vreg_enable("ldoc11", 3200) == 0);
    assert(nsent == 3 && triggers == 1);
    assert(sent[0].addr == 0x40000 && sent[0].data == 3200);
    assert(sent[1].addr == 0x40008 && sent[1].data == 7);
    assert(sent[2].addr == 0x40004 && sent[2].data == 1);
    assert_idle();
    reset(); assert(sweet_rpmh_vreg_enable("ldoc11", 2949) == EINVAL && !map_calls);
    assert(sweet_rpmh_vreg_enable("cx.lvl", 3200) == EINVAL && !map_calls);
    /* ARC: LOW_SVS selects the table index, one command, to the ARC address. */
    reset();
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == 0);
    assert(level == 2 && nsent == 1 && sent[0].addr == 0x30000 && sent[0].data == 2);
    assert_idle();
    /* A second vote on the freed TCS works (state fully restored). */
    assert(sweet_rpmh_arc_set("cx.lvl", 0, &level) == 0);
    assert(level == 0 && nsent == 2 && sent[1].addr == 0x30000 && sent[1].data == 0);
    assert_idle();
    /* MX has no 64 entry: first level >= corner (192) is index 2. */
    assert(sweet_rpmh_arc_set("mx.lvl", 64, &level) == 0);
    assert(level == 2 && sent[2].addr == 0x30010 && sent[2].data == 2);
    assert(sweet_rpmh_arc_set("mx.lvl", 128, &level) == 0 && sent[3].data == 2);
    assert(sweet_rpmh_arc_set("cx.lvl", 16, &level) == 0 && sent[4].data == 1);
    assert_idle();
    /* Policy rejections send nothing. */
    reset(); assert(sweet_rpmh_arc_set("gfx.lvl", 64, &level) == EINVAL && !map_calls);
    assert(sweet_rpmh_arc_set("cx.lvl", 129, &level) == EINVAL && !map_calls);
    assert(sweet_rpmh_arc_set(NULL, 64, &level) == EINVAL);
    reset(); { const uint16_t t[] = {0, 16, 32}; table(AUX, t, 3); db16(AUX + 6, 0);
        db16(144 + 20, 6); }
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EINVAL && !nsent);
    assert(sweet_rpmh_arc_set("cx.lvl", 32, &level) == 0 && sent[0].data == 2);
    reset(); { const uint16_t t[] = {16, 64}; table(AUX, t, 2); }
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EINVAL && !nsent);
    reset(); { const uint16_t t[] = {0, 64, 64, 128}; table(AUX, t, 4); }
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EINVAL && !nsent);
    reset(); { const uint16_t t[] = {0, 128, 64}; table(AUX, t, 3); }
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EINVAL && !nsent);
    /* Release needs table[0] == 0 as well. */
    reset(); { const uint16_t t[] = {16, 64}; table(AUX, t, 2); }
    assert(sweet_rpmh_arc_set("cx.lvl", 0, &level) == EINVAL && !nsent);
    /* Bad entries: odd length, oversize, wrong slave type, bad address type. */
    reset(); db16(144 + 20, 5);
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EINVAL && !nsent);
    reset(); db16(144 + 20, 0);
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EINVAL && !nsent);
    reset(); db16(144 + 20, 34);
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EINVAL && !nsent);
    reset(); db16(144 + 22, 0xffff);
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EINVAL && !nsent);
    reset(); db32(144 + 16, 0x40000);
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EINVAL && !nsent);
    reset(); db32(144 + 16, 0x30004);
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EINVAL && !nsent);
    reset(); assert(sweet_rpmh_vreg_enable("ldoc11", 3200) == 0); /* VRM entry ok */
    reset(); db16(24, 3); db16(8, 4); /* swap slave types: cx.lvl now in VRM */
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EINVAL && !nsent);
    reset(); { const unsigned o = AUX + 1; /* odd, uint16 crossing a word */
        db16(144 + 22, 1);
        const uint16_t t[] = {0, 16, 60, 300};
        for (unsigned i = 0; i < 4; i++) db16(o + 2 * i, t[i]);
        db16(144 + 20, 8); }
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == 0 && sent[0].data == 3);
    /* Missing and duplicated resources. */
    reset(); memset((char *)db + 144, 0, 8);
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == ENODEV && !nsent);
    reset(); memcpy((char *)db + 168, (char *)db + 144, 8);
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == ENODEV && !nsent);
    /* Inherited request on the same rail, or no free ACTIVE TCS: nothing sent. */
    reset(); tcs[(RH_ENABLE) / 4] = 1; tcs[(RH_ADDR) / 4] = 0x30000;
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EBUSY && !nsent);
    assert(!rh_poisoned);
    reset(); tcs[(RH_CONTROL) / 4] = 1; tcs[(RH_STATUS + RH_TCS_STRIDE) / 4] = 0;
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EBUSY && !nsent);
    /* Busy lock never enters the client. */
    reset(); rh_lock = 1;
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EBUSY && !map_calls);
    /* A poisoned client refuses ARC votes too. */
    reset(); rh_poisoned = true;
    assert(sweet_rpmh_arc_set("cx.lvl", 64, &level) == EIO && !map_calls);
    puts("PASS: rpmh LDO + ARC cases");
    return 0;
}
'''


if __name__ == '__main__':
    unittest.main()
