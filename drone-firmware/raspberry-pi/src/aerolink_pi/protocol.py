"""Dependency-free AEROLINK UART v1 framing and validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import struct
import zlib

MAGIC = b"AL"
VERSION = 1
MAX_PAYLOAD = 512
HEADER = struct.Struct("<2sBBHBHII")
CRC = struct.Struct("<I")
MAX_FRAME = HEADER.size + MAX_PAYLOAD + CRC.size


class MessageType(IntEnum):
    HELLO = 0x01
    CAPABILITIES = 0x02
    HEARTBEAT = 0x03
    SET_MODE = 0x10
    SET_STABILIZED_SETPOINT = 0x11
    SET_PAYLOAD_STATE = 0x12
    NODE_STATUS = 0x20
    HEALTH = 0x21
    ACK = 0x22
    FAULT = 0x23


class RejectCode(IntEnum):
    OK = 0
    BAD_MAGIC = 1
    UNSUPPORTED_VERSION = 2
    UNSUPPORTED_TYPE = 3
    BAD_LENGTH = 4
    BAD_CRC = 5
    VEHICLE_MISMATCH = 6
    SESSION_MISMATCH = 7
    DUPLICATE = 8
    REORDERED = 9
    STALE = 10
    OUT_OF_RANGE = 11
    INVALID_STATE = 12
    MANUAL_OVERRIDE = 13
    SAFETY_LOCKOUT = 14
    FEATURE_DISABLED = 15


class ProtocolError(ValueError):
    def __init__(self, code: RejectCode, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Frame:
    message_type: MessageType
    vehicle_id: int
    formation_id: int
    sequence: int
    uptime_ms: int
    payload: bytes = b""
    version: int = VERSION

    def encode(self) -> bytes:
        _validate_fields(self)
        header = HEADER.pack(
            MAGIC, self.version, int(self.message_type), len(self.payload),
            self.vehicle_id, self.formation_id, self.sequence, self.uptime_ms,
        )
        body = header + self.payload
        return body + CRC.pack(zlib.crc32(body) & 0xFFFFFFFF)

    @classmethod
    def decode(cls, data: bytes, *, expected_vehicle_id: int | None = None) -> "Frame":
        if len(data) < HEADER.size + CRC.size:
            raise ProtocolError(RejectCode.BAD_LENGTH, "frame is truncated")
        magic, version, raw_type, length, vehicle, formation, sequence, uptime = HEADER.unpack_from(data)
        if magic != MAGIC:
            raise ProtocolError(RejectCode.BAD_MAGIC, "bad magic")
        if version != VERSION:
            raise ProtocolError(RejectCode.UNSUPPORTED_VERSION, f"unsupported version {version}")
        if length > MAX_PAYLOAD or len(data) != HEADER.size + length + CRC.size:
            raise ProtocolError(RejectCode.BAD_LENGTH, "invalid payload/frame length")
        expected_crc = CRC.unpack_from(data, HEADER.size + length)[0]
        actual_crc = zlib.crc32(data[: HEADER.size + length]) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise ProtocolError(RejectCode.BAD_CRC, "CRC mismatch")
        try:
            message_type = MessageType(raw_type)
        except ValueError as exc:
            raise ProtocolError(RejectCode.UNSUPPORTED_TYPE, f"unknown message type {raw_type}") from exc
        frame = cls(message_type, vehicle, formation, sequence, uptime, data[HEADER.size:HEADER.size + length], version)
        _validate_fields(frame)
        if expected_vehicle_id is not None and vehicle != expected_vehicle_id:
            raise ProtocolError(RejectCode.VEHICLE_MISMATCH, "frame addressed to another vehicle")
        return frame


def _validate_fields(frame: Frame) -> None:
    if frame.version != VERSION:
        raise ProtocolError(RejectCode.UNSUPPORTED_VERSION, "unsupported version")
    if not 0 <= frame.vehicle_id <= 15:
        raise ProtocolError(RejectCode.OUT_OF_RANGE, "vehicle ID must be 0..15")
    if not 0 <= frame.formation_id <= 0xFFFF:
        raise ProtocolError(RejectCode.OUT_OF_RANGE, "formation ID out of range")
    if not 0 <= frame.sequence <= 0xFFFFFFFF or not 0 <= frame.uptime_ms <= 0xFFFFFFFF:
        raise ProtocolError(RejectCode.OUT_OF_RANGE, "sequence/uptime out of range")
    if len(frame.payload) > MAX_PAYLOAD:
        raise ProtocolError(RejectCode.BAD_LENGTH, "payload is too large")


class SequenceTracker:
    """Track independent uint32 sequence spaces without accepting replay."""

    def __init__(self) -> None:
        self._last: dict[MessageType, int] = {}

    def accept(self, frame: Frame) -> None:
        previous = self._last.get(frame.message_type)
        if previous is not None:
            delta = (frame.sequence - previous) & 0xFFFFFFFF
            if delta == 0:
                raise ProtocolError(RejectCode.DUPLICATE, "duplicate sequence")
            if delta > 0x7FFFFFFF:
                raise ProtocolError(RejectCode.REORDERED, "old or reordered sequence")
        self._last[frame.message_type] = frame.sequence

    def reset(self) -> None:
        self._last.clear()


class StreamDecoder:
    """Bounded decoder that resynchronizes after noise/corruption."""

    def __init__(self, *, expected_vehicle_id: int | None = None) -> None:
        self.expected_vehicle_id = expected_vehicle_id
        self._buffer = bytearray()
        self.rejections: list[ProtocolError] = []

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[Frame]:
        self._buffer.extend(chunk)
        frames: list[Frame] = []
        while True:
            start = self._buffer.find(MAGIC)
            if start < 0:
                self._buffer[:] = self._buffer[-1:] if self._buffer.endswith(MAGIC[:1]) else b""
                break
            if start:
                del self._buffer[:start]
            if len(self._buffer) < HEADER.size:
                break
            length = struct.unpack_from("<H", self._buffer, 4)[0]
            if length > MAX_PAYLOAD:
                self.rejections.append(ProtocolError(RejectCode.BAD_LENGTH, "stream payload too large"))
                del self._buffer[0]
                continue
            total = HEADER.size + length + CRC.size
            if len(self._buffer) < total:
                break
            candidate = bytes(self._buffer[:total])
            try:
                frames.append(Frame.decode(candidate, expected_vehicle_id=self.expected_vehicle_id))
                del self._buffer[:total]
            except ProtocolError as error:
                self.rejections.append(error)
                del self._buffer[0]
        if len(self._buffer) > MAX_FRAME:
            del self._buffer[:-MAX_FRAME]
        return frames


HELLO = struct.Struct("<BBBQ")
HEARTBEAT = struct.Struct("<QBH")
SETPOINT = struct.Struct("<QhhhhH")


def encode_hello(role: int, session_nonce: int, minimum: int = VERSION, maximum: int = VERSION) -> bytes:
    if role not in (1, 2) or not 0 < session_nonce <= 0xFFFFFFFFFFFFFFFF:
        raise ProtocolError(RejectCode.OUT_OF_RANGE, "invalid role or session nonce")
    return HELLO.pack(role, minimum, maximum, session_nonce)


def encode_setpoint(session_nonce: int, roll_cd: int, pitch_cd: int,
                    yaw_rate_cds: int, vertical_rate_cms: int, ttl_ms: int) -> bytes:
    if not (-3000 <= roll_cd <= 3000 and -3000 <= pitch_cd <= 3000
            and -18000 <= yaw_rate_cds <= 18000 and -300 <= vertical_rate_cms <= 300
            and 0 < ttl_ms <= 100):
        raise ProtocolError(RejectCode.OUT_OF_RANGE, "setpoint exceeds protocol bounds")
    return SETPOINT.pack(session_nonce, roll_cd, pitch_cd, yaw_rate_cds, vertical_rate_cms, ttl_ms)

def encode_heartbeat(session_nonce: int, state: int, ttl_ms: int = 300) -> bytes:
    if not 0 <= state <= 6 or not 0 < ttl_ms <= 300:
        raise ProtocolError(RejectCode.OUT_OF_RANGE, "heartbeat bounds")
    return HEARTBEAT.pack(session_nonce, state, ttl_ms)

def encode_mode(session_nonce: int, state: int, ttl_ms: int = 100) -> bytes:
    if not 0 <= state <= 6 or not 0 < ttl_ms <= 500:
        raise ProtocolError(RejectCode.OUT_OF_RANGE, "mode bounds")
    return HEARTBEAT.pack(session_nonce, state, ttl_ms)
