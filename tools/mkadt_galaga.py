#!/usr/bin/env python3
"""Apple Device Tree for the Nothing A001 "Galaga" (MediaTek MT6878), built on mkadt.py.

Same tree as sweet's (the kernel's SWEET drivers match its compatible strings), with
Galaga's hardware from the live FDT our milestone-0 shim dumped (HARDWARE_MAP.md):

- RAM handed to XNU: 0x1_4000_0000 .. 0x2_3dc0_0000, the clean part of the upper DDR
  above dramc-rk0 (0x1_3ffff000) and below GenieZone's gz-log (0x2_3de00000).
- GICv3: GICD 0x0c000000 (0x40000), GICR 0x0c040000 (0x200000).
- Generic timer: 13 MHz; virtual timer PPI 11 = INTID 27.
- Framebuffer: LK's videolfb at 0xfe0d0000, 1080x2392, 4352 bytes per line.
- UFS: the MediaTek UFSHCI at 0x112b0000 (0x2300) LK leaves running; same JEDEC register
  set as sweet's Qualcomm host. Patch 0083 finds the LU with the userdata GPT (LU 2 here).
  The driver stays read-only unless boot-arg ufsrw=1. --no-ufs leaves the node out.

usage: mkadt_galaga.py OUT.adt [--dump] [--no-ufs]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt  # noqa: E402
import mkadt  # noqa: E402

mkadt.HIGH_PHYS_BASE = 0x1_4000_0000
mkadt.HIGH_MEM_SIZE = 0x2_3dc0_0000 - 0x1_4000_0000
mkadt.GICD, mkadt.GICD_SIZE = 0x0c000000, 0x40000
mkadt.GICR, mkadt.GICR_SIZE = 0x0c040000, 0x200000
mkadt.TIMEBASE = 13000000
mkadt.VTIMER_INTID = 27
mkadt.FB, mkadt.FB_SIZE = 0xfe0d0000, 0x1df0000
mkadt.FB_W, mkadt.FB_H, mkadt.FB_STRIDE = 1080, 2392, 1088 * 4
mkadt.SWEET_ECID = 0x47414c4147410001  # 'GALAGA' + 1, synthetic
mkadt.UFS, mkadt.UFS_SIZE = 0x112b0000, 0x2300


def build(ufs=True):
    root = mkadt.build(highmem=True)
    name = lambda n: dict((k, v) for k, f, v in n.props).get('name', b'').rstrip(b'\0').decode()
    if not ufs:
        root.children = [c for c in root.children if name(c) != 'sweet-ufs']
    for c in root.children:
        if name(c) == 'sweet-ufs':
            c.props = [(k, f, b'mediatek,mt8183-ufshci\0' if k == 'compatible' else v) for k, f, v in c.props]
    for k, (key, flags, val) in enumerate(root.props):
        if key == 'compatible':
            # keep D22AP/iPhone10,3 for the userland and xiaomi,sweet for SweetPlatformExpert
            root.props[k] = (key, flags, val.replace(b'qcom,sm7150\0', b'mediatek,mt6878\0'))
    for c in root.children:
        if name(c) == 'chosen':
            for k, (key, flags, val) in enumerate(c.props):
                if key in ('firmware-version', 'system-firmware-version'):
                    c.props[k] = (key, flags, b'galaga-shim\0')
    return root


if __name__ == '__main__':
    root = build(ufs='--no-ufs' not in sys.argv)
    blob = adt.serialize(root)
    open(sys.argv[1], 'wb').write(blob)
    if '--dump' in sys.argv:
        adt.dump(adt.parse(blob)[0])
    print(f'{sys.argv[1]}: {len(blob)} bytes', file=sys.stderr)
