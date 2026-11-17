"""Pre-programmed arm motion macros.

This module intentionally does not invent joint positions.  Real motion is
refused until the user supplies calibrated poses in arm_config.json.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from servo_bus import ServoBus, ServoBusError
from servo_bus import TARGET_POSITION_ADDRESS
from servo_bus import u16le


class MotionConfigError(ValueError):
    pass


class ArmMotionController:
    def __init__(self, config_path: str | Path, *, allow_motion: bool = False, dry_run: bool = True):
        self.config_path = Path(config_path)
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.allow_motion = bool(allow_motion)
        self.dry_run = bool(dry_run)
        self._lock = threading.Lock()
        self._motion_lock = threading.Lock()
        self._seen_events: set[str] = set()
        self.state = "DISABLED" if not self.allow_motion else "IDLE"
        self._validate_config()
        self.bus = ServoBus(
            self.config["serial_port"],
            int(self.config["baudrate"]),
            float(self.config.get("response_timeout_seconds", 0.15)),
            dry_run=self.dry_run,
        )

    def _validate_config(self) -> None:
        if self.config.get("protocol") != "FT-SCS-STS":
            raise MotionConfigError("arm_config.json protocol must be FT-SCS-STS")
        if not self.config.get("servos"):
            raise MotionConfigError("arm_config.json must contain at least one servo")
        ids = [int(x["id"]) for x in self.config["servos"]]
        if len(ids) != len(set(ids)) or any(i < 0 or i > 253 for i in ids):
            raise MotionConfigError("servo IDs must be unique and in 0..253")
        poses = self.config.get("poses", {})
        if not self.dry_run and self.allow_motion:
            for name in set(self.config.get("sequence", [])) | {"home"}:
                if not poses.get(name):
                    raise MotionConfigError(f"real motion requires calibrated pose: {name}")

    @property
    def servo_ids(self) -> list[int]:
        return [int(x["id"]) for x in self.config["servos"]]

    def open(self) -> None:
        if self.dry_run:
            return
        self.bus.open()
        self.state = "IDLE" if self.allow_motion else "DISABLED"

    def close(self) -> None:
        self.bus.close()

    def ping_all(self) -> dict[str, Any]:
        results = []
        for servo_id in self.servo_ids:
            if self.dry_run:
                results.append({"id": servo_id, "ok": True, "simulated": True})
                continue
            try:
                frame = self.bus.ping(servo_id)
                results.append({"id": servo_id, "ok": frame is not None, "error": frame.status if frame else None})
            except Exception as exc:
                results.append({"id": servo_id, "ok": False, "error": str(exc)})
        return {"state": "PING_COMPLETE", "servos": results, "simulated": self.dry_run}

    def read_positions(self) -> dict[str, Any]:
        results = []
        for servo_id in self.servo_ids:
            if self.dry_run:
                results.append({"id": servo_id, "ok": True, "position": None, "simulated": True})
                continue
            try:
                results.append({"id": servo_id, "ok": True, "position": self.bus.read_position(servo_id)})
            except Exception as exc:
                results.append({"id": servo_id, "ok": False, "error": str(exc)})
        return {"state": "POSITIONS_READ", "servos": results, "simulated": self.dry_run}

    def read_feedback(self) -> dict[str, Any]:
        results = []
        for servo_id in self.servo_ids:
            if self.dry_run:
                results.append({"id": servo_id, "ok": True, "simulated": True})
                continue
            try:
                data = self.bus.read_data(servo_id, 0x38, 8)
                results.append({
                    "id": servo_id,
                    "ok": True,
                    "position": int(data[0]) | (int(data[1]) << 8),
                    "speed_raw": int(data[2]) | (int(data[3]) << 8),
                    "load_raw": int(data[4]) | (int(data[5]) << 8),
                    "voltage_raw": int(data[6]),
                    "temperature_c": int(data[7]),
                    "status": int(self.bus.read_data(servo_id, 0x41, 1)[0]),
                    "moving": int(self.bus.read_data(servo_id, 0x42, 1)[0]),
                })
            except Exception as exc:
                results.append({"id": servo_id, "ok": False, "error": str(exc)})
        return {"state": "FEEDBACK_READ", "servos": results, "simulated": self.dry_run}

    def execute_grasp(self, event_id: str, confidence: float | None = None) -> dict[str, Any]:
        event_key = str(event_id)
        if not self._motion_lock.acquire(blocking=False):
            return {"state": "BUSY", "event_id": event_key, "simulated": self.dry_run}
        with self._lock:
            if event_key in self._seen_events:
                self._motion_lock.release()
                return {"state": "DUPLICATE", "event_id": event_key, "simulated": self.dry_run}
            if not self.allow_motion and not self.dry_run:
                self._motion_lock.release()
                return {"state": "DISABLED", "event_id": event_key, "simulated": False}
            self._seen_events.add(event_key)
            self.state = "RUNNING"

        try:
            sequence = self.config.get("sequence", ["approach", "grasp", "lift", "hold"])
            self._set_torque(True)
            for pose_name in sequence:
                pose = self.config.get("poses", {}).get(pose_name, {})
                if pose:
                    self._move_pose(pose_name, pose)
                    self._wait_for_pose(pose_name, pose)
                time.sleep(float(self.config.get("pose_settle_seconds", 0.25)))
            with self._lock:
                self.state = "HOLD"
            return {"state": "COMPLETED", "event_id": event_key, "confidence": confidence, "simulated": self.dry_run}
        except Exception as exc:
            with self._lock:
                self.state = "ERROR"
            return {"state": "ERROR", "event_id": event_key, "reason": str(exc), "simulated": self.dry_run}
        finally:
            self._motion_lock.release()

    def move_to_pose(self, pose_name: str) -> dict[str, Any]:
        if not self.allow_motion and not self.dry_run:
            return {"state": "DISABLED", "pose": pose_name, "simulated": False}
        pose = self.config.get("poses", {}).get(str(pose_name))
        if not pose:
            return {"state": "ERROR", "pose": pose_name, "reason": "unknown or empty pose", "simulated": self.dry_run}
        self._motion_lock.acquire()
        try:
            with self._lock:
                self.state = "RUNNING"
            self._set_torque(True)
            self._move_pose(str(pose_name), pose)
            self._wait_for_pose(str(pose_name), pose)
            time.sleep(float(self.config.get("pose_settle_seconds", 0.8)))
            with self._lock:
                self.state = "HOLD" if pose_name in {"hold", "lift"} else "IDLE"
            return {"state": "COMPLETED", "pose": pose_name, "simulated": self.dry_run}
        except Exception as exc:
            with self._lock:
                self.state = "ERROR"
            return {"state": "ERROR", "pose": pose_name, "reason": str(exc), "simulated": self.dry_run}
        finally:
            self._motion_lock.release()

    def stop(self) -> dict[str, Any]:
        try:
            self._set_torque(False)
        finally:
            self.state = "STOPPED"
        return {"state": "STOPPED", "simulated": self.dry_run}

    def _set_torque(self, enabled: bool) -> None:
        if self.dry_run:
            return
        self.bus.torque(self.servo_ids, enabled)

    def _move_pose(self, name: str, pose: dict[str, Any]) -> None:
        records = []
        for servo in self.config["servos"]:
            servo_id = int(servo["id"])
            item = pose.get(str(servo_id))
            if item is None:
                raise MotionConfigError(f"pose {name} missing servo ID {servo_id}")
            position = int(item["position"])
            speed = int(item.get("speed", self.config.get("default_speed", 150)))
            if not 0 <= position <= 0xFFFF or not 0 <= speed <= 0xFFFF:
                raise MotionConfigError(f"pose {name} ID {servo_id} position/speed out of range")
            data = u16le(position) + b"\x00\x00" + u16le(speed)
            records.append((servo_id, data))
        self.bus.sync_write(TARGET_POSITION_ADDRESS, 6, records)

    def _wait_for_pose(self, name: str, pose: dict[str, Any]) -> None:
        """Wait until every servo reports the requested position.

        The arm must not receive the next pose merely because a fixed delay
        elapsed.  This is especially important at speed 250: a pose can take
        several seconds to reach.  A timeout remains as a hardware-fault
        guard, so a disconnected or blocked servo cannot hang forever.
        """
        if self.dry_run:
            return
        targets = {
            int(servo["id"]): int(pose[str(int(servo["id"]))]["position"])
            for servo in self.config["servos"]
        }
        tolerance = int(self.config.get("position_tolerance", 25))
        timeout = float(self.config.get("pose_timeout_seconds", 20.0))
        deadline = time.monotonic() + timeout
        last_positions: dict[int, int] = {}
        while time.monotonic() < deadline:
            last_positions = {servo_id: self.bus.read_position(servo_id) for servo_id in targets}
            if all(abs(last_positions[servo_id] - target) <= tolerance for servo_id, target in targets.items()):
                return
            time.sleep(0.1)
        raise ServoBusError(
            f"pose {name} did not reach target within {timeout:.1f}s; "
            f"target={targets}, actual={last_positions}, tolerance={tolerance}"
        )
