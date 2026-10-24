#!/usr/bin/env python3
"""Map runtime addresses from SWEET 'SMP'/'CRASH' samples to dylibs (and exported symbols)
in an iOS dyld shared cache.

  dsc_whereis.py CACHE_DIR SLIDE ADDR [ADDR ...]

CACHE_DIR holds dyld_shared_cache_arm64 and its .01.. subcaches. SLIDE is the
'slide 0x…' value printed with the sample. Prints image path and the nearest
exported symbol at or below each unslid address (local symbols live in the
.symbols subcache and are not read, so names can be the closest export).
"""
import glob
import os
import struct
import sys


def mappings(path):
    with open(path, 'rb') as f:
        h = f.read(0x200)
        moff, mcount = struct.unpack_from('<II', h, 0x10)
        f.seek(moff)
        m = [struct.unpack('<QQQII', f.read(32)) for _ in range(mcount)]
    return [(addr, size, foff, path) for addr, size, foff, _, _ in m]


def main():
    d, slide = sys.argv[1], int(sys.argv[2], 16)
    main_cache = os.path.join(d, 'dyld_shared_cache_arm64')
    files = [main_cache] + sorted(p for p in glob.glob(main_cache + '.*') if not p.endswith('.symbols'))
    maps = [m for p in files for m in mappings(p)]

    def read(addr, n):
        for a, s, o, p in maps:
            if a <= addr < a + s:
                with open(p, 'rb') as f:
                    f.seek(o + addr - a)
                    return f.read(n)
        return None

    with open(main_cache, 'rb') as f:
        h = f.read(0x200)
    ioff, icount = struct.unpack_from('<II', h, 0x1c0)
    with open(main_cache, 'rb') as f:
        f.seek(ioff)
        infos = [struct.unpack('<QQQII', f.read(32)) for _ in range(icount)]
        images = []
        for addr, _, _, poff, _ in infos:
            f.seek(poff)
            images.append((addr, f.read(256).split(b'\0')[0].decode()))
    images.sort()

    def text_range(base):
        hdr = read(base, 32)
        ncmds, sizeofcmds = struct.unpack_from('<II', hdr, 16)
        cmds = read(base + 32, sizeofcmds)
        off = 0
        for _ in range(ncmds):
            cmd, size = struct.unpack_from('<II', cmds, off)
            if cmd == 0x19 and cmds[off + 8:off + 24].split(b'\0')[0] == b'__TEXT':
                vmaddr, vmsize = struct.unpack_from('<QQ', cmds, off + 24)
                return vmaddr, vmaddr + vmsize
            off += size
        return base, base

    for a in sys.argv[3:]:
        un = int(a, 16) - slide
        cand = [im for im in images if im[0] <= un]
        if not cand:
            print(f'{a}: 0x{un:x} below the cache')
            continue
        base, path = cand[-1]
        lo, hi = text_range(base)
        where = path if lo <= un < hi else f'(not in __TEXT of {path})'
        print(f'{a}: 0x{un:x} {where} +0x{un - base:x}')


if __name__ == '__main__':
    main()


def exports(read, base):
    """(offset, name) for every export of the image at base, from its export trie."""
    hdr = read(base, 32)
    ncmds, sizeofcmds = struct.unpack_from('<II', hdr, 16)
    cmds = read(base + 32, sizeofcmds)
    off, link, trie = 0, None, None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', cmds, off)
        if cmd == 0x19 and cmds[off + 8:off + 24].split(b'\0')[0] == b'__LINKEDIT':
            vmaddr, vmsize, fileoff = struct.unpack_from('<QQQ', cmds, off + 24)
            link = (vmaddr, fileoff)
        elif cmd in (0x80000033,):                     # LC_DYLD_EXPORTS_TRIE
            trie = struct.unpack_from('<II', cmds, off + 8)
        elif cmd in (0x22, 0x80000022) and trie is None:  # LC_DYLD_INFO(_ONLY)
            t = struct.unpack_from('<10I', cmds, off + 8)
            trie = (t[8], t[9])
        off += size
    if not link or not trie or not trie[1]:
        return []
    data = read(link[0] + trie[0] - link[1], trie[1])
    out = []

    def uleb(p):
        r = s = 0
        while True:
            b = data[p]; p += 1
            r |= (b & 0x7f) << s; s += 7
            if b < 0x80:
                return r, p

    def walk(p, prefix):
        size, q = uleb(p)
        if size:
            flags, r = uleb(q)
            if not flags & 0x8:                       # not a re-export
                addr, _ = uleb(r)
                out.append((addr, prefix))
        q += size
        n = data[q]; q += 1
        for _ in range(n):
            e = data.index(b'\0', q)
            edge = data[q:e].decode(errors='replace'); q = e + 1
            child, q = uleb(q)
            walk(child, prefix + edge)
    walk(0, '')
    return sorted(out)
