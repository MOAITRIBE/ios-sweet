#!/usr/bin/env python3
"""Retarget sweet's screen constants in the xnu patches to the Nothing A001 "Galaga".

Galaga (MediaTek MT6878): LK's framebuffer is at 0xfe0d0000, 1080x2392, 4352 bytes per
line (1088 px). The early console maps the 32 MB L2 block that holds it (0xfe000000) and
points 0xd0000 into it. Only numbers change, so every hunk keeps its line counts.

Run from the repo root: tools/galaga-retarget-patches.py   (idempotent)
"""
import pathlib
import sys

P = pathlib.Path(__file__).resolve().parent.parent / 'xnu' / 'patches'

EDITS = {
    '0010-sweet-early-framebuffer-debug.patch': [
        ('+\tMOV64\tx0, (0x9c000000 + 2368 * 4320)\n', '+\tMOV64\tx0, (0xfe0d0000 + 2360 * 4352)\n'),
        ('+\tmov\t\tx4, #4320\n', '+\tmov\t\tx4, #4352\n'),
        ('+\tMOV64\tx10, 0x9c000000\n', '+\tMOV64\tx10, 0xfe000000\n'),
        ('+#define EARLY_FB ((volatile uint32_t *)(uintptr_t)0x9c000000)\n',
         '+#define EARLY_FB ((volatile uint32_t *)(uintptr_t)0xfe0d0000)\n'),
        ('+#define EARLY_HEIGHT 2400u\n', '+#define EARLY_HEIGHT 2392u\n'),
        ('+#define EARLY_STRIDE (4320u / 4)\n', '+#define EARLY_STRIDE (4352u / 4)\n'),
    ],
    '0012-sweet-keep-debug-console-after-ttbr0.patch': [
        ('+\t*slot = 0x9c000000ULL | ARM_TTE_VALID | ARM_TTE_TYPE_BLOCK |\n',
         '+\t*slot = 0xfe000000ULL | ARM_TTE_VALID | ARM_TTE_TYPE_BLOCK |\n'),
        ('-#define EARLY_FB ((volatile uint32_t *)(uintptr_t)0x9c000000)\n',
         '-#define EARLY_FB ((volatile uint32_t *)(uintptr_t)0xfe0d0000)\n'),
        ('+static volatile uint32_t *early_fb = (volatile uint32_t *)(uintptr_t)0x9c000000;\n',
         '+static volatile uint32_t *early_fb = (volatile uint32_t *)(uintptr_t)0xfe0d0000;\n'),
        (' #define EARLY_HEIGHT 2400u\n', ' #define EARLY_HEIGHT 2392u\n'),
        (' #define EARLY_STRIDE (4320u / 4)\n', ' #define EARLY_STRIDE (4352u / 4)\n'),
        ('+\tearly_fb = (volatile uint32_t *)(uintptr_t)base;\n',
         '+\tearly_fb = (volatile uint32_t *)(uintptr_t)(base + 0xd0000);  /* Galaga FB offset in its 32MB block */\n'),
    ],
    '0061-sweet-iphone-x-display-size.patch': [
        ('+\tfLogicalH = native ? 2400 : 2436;\n', '+\tfLogicalH = native ? 2392 : 2436;\n'),
        ('+\tfOffY = (fLogicalH - 2400) / 2;\n', '+\tfOffY = (fLogicalH - 2392) / 2;\n'),
    ],
}

ok = True
for name, edits in EDITS.items():
    path = P / name
    text = path.read_text()
    for old, new in edits:
        if new in text and old not in text:
            continue                          # already applied
        n = text.count(old)
        if n != 1:
            print(f'{name}: expected 1 match, found {n}: {old.strip()!r}', file=sys.stderr)
            ok = False
            continue
        text = text.replace(old, new)
    path.write_text(text)
    print(f'{name}: ok')
sys.exit(0 if ok else 1)
