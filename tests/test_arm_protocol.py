import unittest

from arm_protocol import build_packet, parse_frame, split_frames


class ArmProtocolTests(unittest.TestCase):
    def test_documented_position_packet(self):
        packet = build_packet(1, 0x03, [0x2A, 0x00, 0x08, 0x00, 0x00, 0xE8, 0x03])
        self.assertEqual(packet.hex(" ").upper(), "FF FF 01 09 03 2A 00 08 00 00 E8 03 D5")
        frame = parse_frame(packet)
        self.assertEqual(frame.servo_id, 1)
        self.assertEqual(frame.payload, bytes([0x03, 0x2A, 0x00, 0x08, 0x00, 0x00, 0xE8, 0x03]))

    def test_split_incomplete_and_complete(self):
        packet = build_packet(1, 0x01)
        frames, remainder = split_frames(packet[:4])
        self.assertEqual(frames, [])
        self.assertEqual(remainder, packet[:4])
        frames, remainder = split_frames(remainder + packet[4:])
        self.assertEqual(len(frames), 1)
        self.assertEqual(remainder, b"")


if __name__ == "__main__":
    unittest.main()
