"""
FastCDC: Fast Content-Defined Chunking using Gear Hash.
Based on the USENIX ATC '16 research paper:
"FastCDC: a Fast and Efficient Content-Defined Chunking Approach for Data Deduplication"
(Wen Xia, Yukun Zhou, Hong Jiang, Dan Feng, Yu Hua, Yuchong Hu, Qing Liu).
"""

import hashlib
from typing import Generator, Iterable, List

# Deterministic 256-entry 64-bit Gear Table
GEAR_TABLE: List[int] = [
    int.from_bytes(hashlib.sha256(f"FastCDC_Gear_Table_{i}".encode("ascii")).digest()[:8], "little")
    for i in range(256)
]


def fastcdc_chunk_stream(
    stream: Iterable[bytes],
    min_chunk: int,
    avg_chunk: int,
    max_chunk: int,
) -> Generator[bytes, None, None]:
    """
    Chunks a stream of byte buffers using FastCDC normalized dual-mask Gear hash.
    Provides boundary alignment resilience against byte-insertions and byte-shifts.
    """
    buffer = bytearray()
    bits = max(8, int.bit_length(avg_chunk) - 1)
    mask_s = (1 << (bits - 1)) - 1
    mask_l = (1 << (bits + 1)) - 1
    table = GEAR_TABLE

    for chunk in stream:
        if not chunk:
            continue
        buffer.extend(chunk)

        while len(buffer) >= max_chunk:
            limit = max_chunk
            mid = avg_chunk
            cut = limit
            fp = 0

            # 1. Sub-minimum jump: bytes 0..min_chunk are skipped for boundary checking
            # 2. Normal region: min_chunk to avg_chunk with mask_s
            for i in range(min_chunk, mid):
                fp = ((fp << 1) + table[buffer[i]]) & 0xFFFFFFFFFFFFFFFF
                if (fp & mask_s) == 0:
                    cut = i + 1
                    break
            else:
                # 3. Extended region: avg_chunk to max_chunk with mask_l
                for i in range(mid, limit):
                    fp = ((fp << 1) + table[buffer[i]]) & 0xFFFFFFFFFFFFFFFF
                    if (fp & mask_l) == 0:
                        cut = i + 1
                        break

            yield bytes(buffer[:cut])
            del buffer[:cut]

    # Process residual bytes
    while len(buffer) > min_chunk:
        rem = len(buffer)
        limit = min(rem, max_chunk)
        mid = min(limit, avg_chunk)
        cut = limit
        fp = 0

        for i in range(min_chunk, mid):
            fp = ((fp << 1) + table[buffer[i]]) & 0xFFFFFFFFFFFFFFFF
            if (fp & mask_s) == 0:
                cut = i + 1
                break
        else:
            for i in range(mid, limit):
                fp = ((fp << 1) + table[buffer[i]]) & 0xFFFFFFFFFFFFFFFF
                if (fp & mask_l) == 0:
                    cut = i + 1
                    break

        yield bytes(buffer[:cut])
        del buffer[:cut]

    if buffer:
        yield bytes(buffer)
