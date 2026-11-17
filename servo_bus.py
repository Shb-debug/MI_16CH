"""Safe, small FT-SCS/STS serial bus driver."""

from __future__ import annotations

import time
import threading
from pathlib import Path
from typing import Iterable

from arm_protocol import BROADCAST_ID, ServoFrame, build_packet, from_u16le, u16le

try:
    import serial
except ImportError:  # pragma: no cover - exercised when dependencies are missing
    serial = None


PING = 0x01
READ = 0x02
WRITE = 0x03
SYNC_READ = 0x82
SYNC_WRITE = 0x83

TORQUE_ADDRESS = 0x28
ACCELERATION_ADDRESS = 0x29
TARGET_POSITION_ADDRESS = 0x2A
CURRENT_POSITION_ADDRESS = 0x38
STATUS_ADDRESS = 0x41
MOVING_ADDRESS = 0x42


class ServoBusError(RuntimeError):
    pass


class ServoBus:
    def __init__(self, port: str, baudrate: int = 1_000_000, timeout: float = 0.15, dry_run: bool = False):
        self.port = str(port)
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)
        self.dry_run = bool(dry_run)
        self.serial = None
        # A request consists of write + optional response read.  Keep that
        # pair atomic so polling feedback cannot interleave with a command.
        self._io_lock = threading.Lock()

    def open(self) -> None:
        if self.dry_run:
            return
        if serial is None:
            raise ServoBusError("pyserial is not installed; install requirements.txt")
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.01,
                write_timeout=0.5,
            )
        except Exception as exc:
            raise ServoBusError(f"cannot open {self.port} at {self.baudrate} baud: {exc}") from exc

    def close(self) -> None:
        if self.serial is not None:
            self.serial.close()
            self.serial = None

    def __enter__(self) -> "ServoBus":
        self.open()
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def send(self, packet: bytes, expect_response: bool = True) -> ServoFrame | None:
        if self.dry_run:
            return None
        if self.serial is None:
            raise ServoBusError("serial bus is not open")
        with self._io_lock:
            self.serial.reset_input_buffer()
            self.serial.write(packet)
            self.serial.flush()
            if not expect_response:
                return None
            return self._read_frame(packet[2])

    def _read_frame(self, expected_id: int) -> ServoFrame:
        if self.serial is None:
            raise ServoBusError("serial bus is not open")
        deadline = time.monotonic() + self.timeout
        buffer = bytearray()
        while time.monotonic() < deadline:
            part = self.serial.read(64)
            if part:
                buffer.extend(part)
                start = buffer.find(b"\xff\xff")
                if start >= 0 and len(buffer) >= start + 4:
                    length = buffer[start + 3]
                    total = length + 4
                    if len(buffer) >= start + total:
                        from arm_protocol import parse_frame
                        frame = parse_frame(bytes(buffer[start:start + total]))
                        if frame.servo_id != expected_id:
                            raise ServoBusError(f"unexpected response ID {frame.servo_id}, expected {expected_id}")
                        return frame
            time.sleep(0.001)
        raise ServoBusError(f"timeout waiting for servo ID {expected_id}")

    def ping(self, servo_id: int) -> ServoFrame | None:
        return self.send(build_packet(servo_id, PING), expect_response=servo_id != BROADCAST_ID)

    def write_data(self, servo_id: int, address: int, data: Iterable[int]) -> ServoFrame | None:
        values = bytes(int(v) for v in data)
        packet = build_packet(servo_id, WRITE, [int(address), *values])
        return self.send(packet, expect_response=servo_id != BROADCAST_ID)

    def read_data(self, servo_id: int, address: int, length: int) -> bytes:
        if self.dry_run:
            return bytes(length)
        frame = self.send(build_packet(servo_id, READ, [int(address), int(length)]), expect_response=True)
        assert frame is not None
        if frame.status:
            raise ServoBusError(f"servo ID {servo_id} returned ERROR=0x{frame.status:02X}")
        if len(frame.parameters) != length:
            raise ServoBusError(f"servo ID {servo_id} returned {len(frame.parameters)} bytes, expected {length}")
        return frame.parameters

    def read_position(self, servo_id: int) -> int:
        return from_u16le(self.read_data(servo_id, CURRENT_POSITION_ADDRESS, 2))

    def sync_write(self, address: int, data_length: int, records: Iterable[tuple[int, Iterable[int]]]) -> None:
        params = [int(address), int(data_length)]
        record_count = 0
        for servo_id, data in records:
            values = bytes(int(v) for v in data)
            if len(values) != int(data_length):
                raise ServoBusError(f"sync write for ID {servo_id} has {len(values)} bytes, expected {data_length}")
            params.extend([int(servo_id), *values])
            record_count += 1
        if record_count == 0:
            return
        self.send(build_packet(BROADCAST_ID, SYNC_WRITE, params), expect_response=False)

    def torque(self, servo_ids: Iterable[int], enabled: bool) -> None:
        self.sync_write(TORQUE_ADDRESS, 1, [(servo_id, [1 if enabled else 0]) for servo_id in servo_ids])
