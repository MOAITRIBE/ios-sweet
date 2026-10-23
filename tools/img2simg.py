#!/usr/bin/env python3
"""Convert a raw image to an Android sparse image (what AOSP's img2simg does).

fastboot on macOS cannot flash a raw multi-GiB image ("Failed reading from userdata":
read() refuses >2 GiB), but it streams sparse images in max-download-size pieces.
Runs of all-zero blocks become DONT_CARE chunks, so the empty part of the HFS+ volume
is neither sent nor written (fastboot/LK leave those blocks as they are; HFS+ does not
read unallocated blocks).

usage: img2simg.py RAW.img OUT.simg [block_size]
"""
import struct
import sys

SPARSE_MAGIC = 0xed26ff3a
CHUNK_RAW, CHUNK_DONT_CARE = 0xcac1, 0xcac3
FILE_HDR, CHUNK_HDR = 28, 12
RUN_LIMIT = 16 * 1024 * 1024        # bytes per RAW chunk


def main():
    src, dst = sys.argv[1], sys.argv[2]
    bs = int(sys.argv[3]) if len(sys.argv) > 3 else 4096
    zero = bytes(bs)
    with open(src, 'rb') as f, open(dst, 'wb') as o:
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        assert size % bs == 0, 'image size is not a multiple of the block size'
        total = size // bs
        o.write(bytes(FILE_HDR))
        chunks = 0
        raw = bytearray()           # pending RAW data
        dont = 0                    # pending DONT_CARE blocks

        def flush_raw():
            nonlocal raw, chunks
            if raw:
                o.write(struct.pack('<HHII', CHUNK_RAW, 0, len(raw) // bs, CHUNK_HDR + len(raw)))
                o.write(raw)
                chunks += 1
                raw = bytearray()

        def flush_dont():
            nonlocal dont, chunks
            if dont:
                o.write(struct.pack('<HHII', CHUNK_DONT_CARE, 0, dont, CHUNK_HDR))
                chunks += 1
                dont = 0

        done = 0
        while True:
            buf = f.read(bs * 256)
            if not buf:
                break
            for i in range(0, len(buf), bs):
                b = buf[i:i + bs]
                if b == zero:
                    flush_raw()
                    dont += 1
                else:
                    flush_dont()
                    raw += b
                    if len(raw) >= RUN_LIMIT:
                        flush_raw()
            done += len(buf)
            if done % (1 << 30) < len(buf):
                print(f'{done >> 30} / {size >> 30} GiB', flush=True)
        flush_raw()
        flush_dont()
        o.seek(0)
        o.write(struct.pack('<IHHHHIIII', SPARSE_MAGIC, 1, 0, FILE_HDR, CHUNK_HDR, bs, total, chunks, 0))
    print(f'{dst}: {total} blocks of {bs}, {chunks} chunks')


if __name__ == '__main__':
    main()
