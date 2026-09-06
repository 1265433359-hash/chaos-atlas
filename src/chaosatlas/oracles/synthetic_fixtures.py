"""Bounded synthetic fixtures shared by acceptance and unified engine runs."""

from __future__ import annotations

import binascii
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import struct
from typing import Any
import zlib


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def create_unique_png(path: Path) -> dict[str, Any]:
    """Create a tiny unique RGBA fixture, then decode and validate it separately."""
    width, height = 2, 2
    pixels = os.urandom(width * height * 4)
    rows = b"".join(
        b"\x00" + pixels[index:index + width * 4]
        for index in range(0, len(pixels), width * 4)
    )
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(rows))
        + _chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return verify_png(path)


def verify_png(path: Path) -> dict[str, Any]:
    """Decode one bounded PNG independently from the fixture encoder."""
    payload = path.read_bytes()
    if not payload.startswith(b"\x89PNG\r\n\x1a\n") or len(payload) > 1048576:
        raise ValueError("invalid bounded PNG signature")
    offset, header, compressed, ended = 8, None, bytearray(), False
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ValueError("truncated PNG chunk")
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        if length > 1048576 or offset + 12 + length > len(payload):
            raise ValueError("invalid PNG chunk length")
        kind = payload[offset + 4:offset + 8]
        data = payload[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length:offset + 12 + length])[0]
        if binascii.crc32(kind + data) & 0xFFFFFFFF != expected_crc:
            raise ValueError("invalid PNG chunk checksum")
        if kind == b"IHDR":
            if header is not None or length != 13:
                raise ValueError("invalid PNG header")
            header = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            ended = True
            offset += 12 + length
            break
        offset += 12 + length
    if header != (2, 2, 8, 6, 0, 0, 0) or not ended or offset != len(payload):
        raise ValueError("unexpected PNG structure")
    decoded = zlib.decompress(bytes(compressed))
    if len(decoded) != 18 or decoded[0] != 0 or decoded[9] != 0:
        raise ValueError("unexpected decoded PNG raster")
    return {
        "decoder": "stdlib-crc-zlib-rgba8-v1",
        "width": 2,
        "height": 2,
        "byte_length": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def build_project_fixtures(
    project_id: str,
    root: Path,
    bootstrap_fixtures: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return in-memory replay fixtures plus a non-secret validation summary."""
    fixtures = dict(bootstrap_fixtures)
    if project_id != "immich":
        return fixtures, None
    path = Path(root) / "synthetic.png"
    validation = create_unique_png(path)
    fixtures = {
        "synthetic_png": path.read_bytes(),
        "fixture_timestamp": datetime.now(timezone.utc).isoformat(),
        "fixture_sha256": validation["sha256"],
    }
    return fixtures, validation
