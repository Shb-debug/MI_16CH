"""FT-SCS/STS packet builder and parser.

The protocol uses:
    FF FF ID LENGTH INSTRUCTION/PAYLOAD CHECKSUM

For a command, LENGTH is parameter_count + 2.  The checksum is the
bitwise inverse of the low byte of ID + LENGTH + all payload bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


HEADER = b"\xff\xff"
BROADCAST_ID = 0xFE


class ProtocolError(ValueError):
    pass


def checksum(servo_id: int, length: int, payload: Iterable[int]) -> int:
    values = [servo_id, length, *payload]
    if any(not 0 <= int(v) <= 0xFF for v in values):
        raise ProtocolError("packet fields must be bytes")
    return (~(sum(values) & 0xFF)) & 0xFF


def build_packet(servo_id: int, instruction: int, params: Iterable[int] = ()) -> bytes:
    if not 0 <= int(servo_id) <= 0xFE:
        raise ProtocolError("servo_id must be in 0..254")
    if not 0 <= int(instruction) <= 0xFF:
        raise ProtocolError("instruction must be a byte")
    parameter_bytes = bytes(int(v) for v in params)
    length = len(parameter_bytes) + 2
    payload = bytes([int(instruction), *parameter_bytes])
    return HEADER + bytes([int(servo_id), length]) + payload + bytes([checksum(int(servo_id), length, payload)])


@dataclass(frozen=True)
class ServoFrame:
    servo_id: int
    length: int
    payload: bytes
    checksum: int

    @property
    def status(self) -> int | None:
        return self.payload[0] if self.payload else None

    @property
    def parameters(self) -> bytes:
        return self.payload[1:]


def parse_frame(frame: bytes) -> ServoFrame:
    raw = bytes(frame)
    if len(raw) < 6 or raw[:2] != HEADER:
        raise ProtocolError("invalid frame header or frame too short")
    servo_id, length = raw[2], raw[3]
    expected_size = length + 4
    if length < 2 or len(raw) != expected_size:
        raise ProtocolError("invalid frame length")
    payload = raw[4:-1]
    received = raw[-1]
    expected = checksum(servo_id, length, payload)
    if received != expected:
        raise ProtocolError(f"checksum mismatch: received 0x{received:02X}, expected 0x{expected:02X}")
    return ServoFrame(servo_id, length, payload, received)


def split_frames(buffer: bytes) -> tuple[list[ServoFrame], bytes]:
    """Extract complete frames and return (frames, incomplete_remainder)."""
    data = bytes(buffer)
    frames: list[ServoFrame] = []
    while True:
        start = data.find(HEADER)
        if start < 0:
            return frames, b""
        if start:
            data = data[start:]
        if len(data) < 4:
            return frames, data
        expected_size = data[3] + 4
        if expected_size < 6:
            data = data[2:]
            continue
        if len(data) < expected_size:
            return frames, data
        candidate, data = data[:expected_size], data[expected_size:]
        try:
            frames.append(parse_frame(candidate))
        except ProtocolError:
            # Resynchronise on the next possible header.
            data = candidate[2:] + data


def u16le(value: int) -> bytes:
    if not 0 <= int(value) <= 0xFFFF:
        raise ProtocolError("u16 value out of range")
    value = int(value)
    return bytes((value & 0xFF, (value >> 8) & 0xFF))


def from_u16le(data: bytes) -> int:
    if len(data) != 2:
        raise ProtocolError("u16 needs exactly two bytes")
    return int(data[0]) | (int(data[1]) << 8)
