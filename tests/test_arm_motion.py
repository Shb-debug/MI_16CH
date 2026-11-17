import json
import tempfile
import unittest
from pathlib import Path

from arm_motion import ArmMotionController


class ArmMotionTests(unittest.TestCase):
    def test_dry_run_deduplicates_event(self):
        config = {
            "protocol": "FT-SCS-STS",
            "serial_port": "COM7",
            "baudrate": 1000000,
            "servos": [{"id": 1, "joint": "base"}],
            "poses": {"approach": {}, "grasp": {}, "lift": {}, "hold": {}},
            "sequence": ["approach", "grasp", "lift", "hold"]
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "arm.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            controller = ArmMotionController(path, allow_motion=False, dry_run=True)
            first = controller.execute_grasp("event-1", 0.9)
            second = controller.execute_grasp("event-1", 0.9)
        self.assertEqual(first["state"], "COMPLETED")
        self.assertEqual(second["state"], "DUPLICATE")


if __name__ == "__main__":
    unittest.main()
