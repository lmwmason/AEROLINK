import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from aerolink_pi.fake_uart import fake_uart_pair
from aerolink_pi.protocol import (
    Frame, MessageType, ProtocolError, RejectCode, SequenceTracker,
    StreamDecoder, encode_hello, encode_setpoint,
)

VECTORS = Path(__file__).parent / "vectors" / "uart_v1.json"


class GoldenVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = json.loads(VECTORS.read_text())

    def test_valid_vectors_decode_and_reencode_exactly(self):
        for vector in self.vectors["valid"]:
            with self.subTest(vector["name"]):
                encoded = bytes.fromhex(vector["hex"])
                frame = Frame.decode(encoded)
                self.assertEqual(frame.message_type.name, vector["message_type"])
                self.assertEqual(frame.vehicle_id, vector["vehicle_id"])
                self.assertEqual(frame.sequence, vector["sequence"])
                self.assertEqual(frame.encode(), encoded)

    def test_invalid_vectors_reject_with_fixed_reason(self):
        for vector in self.vectors["invalid"]:
            with self.subTest(vector["name"]):
                with self.assertRaises(ProtocolError) as caught:
                    Frame.decode(bytes.fromhex(vector["hex"]))
                self.assertEqual(caught.exception.code.name, vector["reject"])


class ProtocolTests(unittest.TestCase):
    def test_stream_arbitrary_chunks_noise_and_concatenation(self):
        first = Frame(MessageType.HELLO, 7, 0, 10, 1000, encode_hello(1, 42)).encode()
        second = Frame(MessageType.HEARTBEAT, 7, 2, 11, 1010, b"abc").encode()
        decoder = StreamDecoder(expected_vehicle_id=7)
        output = []
        wire = b"noise" + first + second
        for byte in wire:
            output.extend(decoder.feed(bytes([byte])))
        self.assertEqual([f.message_type for f in output], [MessageType.HELLO, MessageType.HEARTBEAT])
        self.assertLessEqual(decoder.buffered_bytes, 533)

    def test_crc_and_vehicle_identity_rejected(self):
        encoded = bytearray(Frame(MessageType.HEARTBEAT, 3, 0, 1, 10, b"x").encode())
        encoded[-1] ^= 1
        with self.assertRaises(ProtocolError) as caught:
            Frame.decode(encoded)
        self.assertEqual(caught.exception.code, RejectCode.BAD_CRC)
        good = Frame(MessageType.HEARTBEAT, 3, 0, 1, 10).encode()
        with self.assertRaises(ProtocolError) as caught:
            Frame.decode(good, expected_vehicle_id=4)
        self.assertEqual(caught.exception.code, RejectCode.VEHICLE_MISMATCH)

    def test_sequence_duplicate_reorder_and_wrap(self):
        tracker = SequenceTracker()
        make = lambda seq: Frame(MessageType.HEARTBEAT, 1, 0, seq, 0)
        tracker.accept(make(0xFFFFFFFF))
        tracker.accept(make(0))
        with self.assertRaises(ProtocolError) as duplicate:
            tracker.accept(make(0))
        self.assertEqual(duplicate.exception.code, RejectCode.DUPLICATE)
        with self.assertRaises(ProtocolError) as reordered:
            tracker.accept(make(0xFFFFFFFF))
        self.assertEqual(reordered.exception.code, RejectCode.REORDERED)

    def test_setpoint_bounds_and_no_arm_message(self):
        encode_setpoint(1, 3000, -3000, 18000, -300, 100)
        with self.assertRaises(ProtocolError) as caught:
            encode_setpoint(1, 3001, 0, 0, 0, 100)
        self.assertEqual(caught.exception.code, RejectCode.OUT_OF_RANGE)
        names = {member.name for member in MessageType}
        self.assertFalse(names & {"ARM", "MOTOR", "THROTTLE", "MIXER"})

    def test_fake_uart_disconnect_drops_stale_bytes(self):
        pi, fc = fake_uart_pair()
        frame = Frame(MessageType.HELLO, 1, 0, 1, 1, encode_hello(1, 99)).encode()
        pi.write(frame, chunk_size=3)
        fc.disconnect()
        fc.reconnect()
        self.assertEqual(fc.read(), b"")
        pi.write(frame)
        self.assertEqual(fc.read(), frame)


if __name__ == "__main__":
    unittest.main()
