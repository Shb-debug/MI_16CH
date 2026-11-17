"""Local JSON-lines bridge between MI_16CH and the STS servo bus.

Default mode is dry-run.  Real motion requires both calibrated poses and the
explicit --allow-motion flag.
"""

from __future__ import annotations

import argparse
import json
import socketserver
from pathlib import Path

from arm_motion import ArmMotionController


class BridgeHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        controller: ArmMotionController = self.server.controller  # type: ignore[attr-defined]
        for raw in self.rfile:
            try:
                request = json.loads(raw.decode("utf-8"))
                command = request.get("command")
                if command == "PING":
                    response = controller.ping_all()
                elif command == "READ_POSITIONS":
                    response = controller.read_positions()
                elif command == "READ_FEEDBACK":
                    response = controller.read_feedback()
                elif command == "MOVE_POSE":
                    response = controller.move_to_pose(request.get("pose", ""))
                elif command == "LEFT_HAND_GRASP":
                    response = controller.execute_grasp(request.get("event_id", "unknown"), request.get("confidence"))
                elif command == "STOP":
                    response = controller.stop()
                elif command == "STATUS":
                    response = {"state": controller.state, "simulated": controller.dry_run}
                else:
                    response = {"state": "ERROR", "reason": f"unknown command: {command}"}
            except Exception as exc:
                response = {"state": "ERROR", "reason": str(exc)}
            self.wfile.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()


class BridgeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, address, handler, controller):
        super().__init__(address, handler)
        self.controller = controller


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="arm_config.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--allow-motion", action="store_true")
    parser.add_argument("--real", action="store_true", help="open the real serial port; otherwise use dry-run")
    args = parser.parse_args()
    controller = ArmMotionController(Path(args.config), allow_motion=args.allow_motion, dry_run=not args.real)
    controller.open()
    server = BridgeServer((args.host, args.port), BridgeHandler, controller)
    print(f"[ARM] bridge listening on {args.host}:{args.port} dry_run={controller.dry_run} state={controller.state}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        controller.close()


if __name__ == "__main__":
    main()
