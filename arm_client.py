"""Client for the local MI-to-arm JSON-lines bridge."""

from __future__ import annotations

import json
import socket
from typing import Any


class ArmBridgeClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8766, timeout: float = 120.0):
        self.host, self.port, self.timeout = host, int(port), float(timeout)

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                part = sock.recv(4096)
                if not part:
                    break
                data += part
            if not data:
                raise ConnectionError("arm bridge returned no response")
            return json.loads(data.decode("utf-8"))
