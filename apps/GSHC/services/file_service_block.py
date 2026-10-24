"""Negotiated LOGFILE block v1 wire codec; no I/O or implicit retry."""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

BLOCK_SIZE = 512
HEADER = struct.Struct('<4sBBHQIIIIIIHH')
RAW_LIMIT = HEADER.size + BLOCK_SIZE + 4
WIRE_LIMIT = RAW_LIMIT + RAW_LIMIT // 254 + 3


class BlockIntegrityError(ValueError):
    """A complete delimited frame failed framing/CRC; bounded POLL replay is safe."""


@dataclass(frozen=True)
class LogBlock:
    transfer: int
    request_id: int
    sequence: int
    file_id: int
    whole_crc: int
    size: int
    offset: int
    eof: bool
    data: bytes


def Cobs_Decode(encoded: bytes) -> bytes:
    if not encoded or len(encoded) > WIRE_LIMIT - 2 or b'\0' in encoded:
        raise BlockIntegrityError('Invalid COBS extent')
    output = bytearray()
    position = 0
    while position < len(encoded):
        code = encoded[position]
        position += 1
        end = position + code - 1
        if end > len(encoded):
            raise BlockIntegrityError('Truncated COBS run')
        output.extend(encoded[position:end])
        position = end
        if code != 255 and position < len(encoded):
            output.append(0)
        if len(output) > RAW_LIMIT:
            raise BlockIntegrityError('Oversized decoded block')
    return bytes(output)


def Block_Decode(encoded: bytes) -> LogBlock:
    raw = Cobs_Decode(encoded)
    if len(raw) < HEADER.size + 4:
        raise BlockIntegrityError('Truncated block')
    if zlib.crc32(raw[:-4]) != int.from_bytes(raw[-4:], 'little'):
        raise BlockIntegrityError('Block CRC mismatch')
    magic, version, kind, flags, transfer, rid, sequence, file_id, whole, size, offset, length, reserved = HEADER.unpack_from(raw)
    if (magic != b'SLB1' or version != 1 or kind != 1 or flags & ~1
            or reserved or not transfer or not rid or not 1 <= file_id <= 999999
            or offset > size or length != min(BLOCK_SIZE, size - offset)
            or len(raw) != HEADER.size + length + 4
            or bool(flags & 1) != (offset + length == size)):
        raise ValueError('Invalid block header/extent/EOF')
    return LogBlock(transfer, rid, sequence, file_id, whole, size, offset,
                    bool(flags & 1), raw[HEADER.size:-4])
