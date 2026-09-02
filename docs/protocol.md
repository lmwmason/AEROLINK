# AEROLINK UART protocol v1

Status: implementation baseline for host conformance. All multibyte integers
are little-endian. The protocol carries guarded application requests; it has no
arm or motor-output message.

## Frame

| Offset | Size | Field | Rule |
|---:|---:|---|---|
| 0 | 2 | magic | ASCII `AL` (`41 4c`) |
| 2 | 1 | version | `1` |
| 3 | 1 | message type | table below |
| 4 | 2 | payload length | `0..512` bytes |
| 6 | 1 | vehicle ID | `1..15`; `0` only during unbound discovery |
| 7 | 2 | formation ID | `0` means none |
| 9 | 4 | sequence | unsigned, per sender/session/type |
| 13 | 4 | sender uptime | monotonic milliseconds modulo 2^32 |
| 17 | N | payload | message-specific |
| 17+N | 4 | CRC-32 | IEEE CRC-32 over bytes `0..16+N` |

Maximum encoded size is 533 bytes. Receivers use a bounded buffer, scan for
magic after damage, reject the whole frame on any error, and never act on a
partial frame. CRC is an accidental corruption check, not authentication.

## Message types

| ID | Name | Direction | Control authority |
|---:|---|---|---|
| `0x01` | HELLO | both | none |
| `0x02` | CAPABILITIES | FC to Pi | none |
| `0x03` | HEARTBEAT | Pi to FC | liveness only |
| `0x10` | SET_MODE | Pi to FC | guarded state request; cannot arm |
| `0x11` | SET_STABILIZED_SETPOINT | Pi to FC | bounded stabilized reference only |
| `0x12` | SET_PAYLOAD_STATE | Pi to FC | future guarded logical request only |
| `0x20` | NODE_STATUS | FC to Pi | none |
| `0x21` | HEALTH | FC to Pi | none |
| `0x22` | ACK | FC to Pi | none |
| `0x23` | FAULT | FC to Pi | none |

Unknown IDs are rejected as `UNSUPPORTED_TYPE`. There is deliberately no ARM,
THROTTLE, MOTOR, MIXER, or raw actuator message.

## Sessions, ordering, and freshness

HELLO payload is `<role:u8, min_version:u8, max_version:u8,
session_nonce:u64>`. Role is `1` for Pi and `2` for FC. A random nonzero nonce
changes on every process/FC boot. No state-changing request is accepted before
two-way version negotiation binds both nonces and the configured vehicle ID.

Sequence counters begin at a random value after HELLO and increment separately
per message type. A value is newer when unsigned subtraction from the last
accepted value is in `1..0x7fffffff`; duplicates and older/reordered values are
rejected. A new nonce clears prior sequence state but never restores ACTIVE.

Sender uptime is monotonic, never wall clock. During HELLO, each side estimates
the peer uptime offset using request/response receive times. A control frame is
fresh only if its estimated age is nonnegative within configured clock-skew
tolerance and no greater than its message TTL. The FC additionally starts its
heartbeat/setpoint watchdog at local receive time, so clock estimation cannot
extend authority. Required initial maxima are heartbeat 300 ms, mode 500 ms,
setpoint 100 ms, and payload request 100 ms. Exact operational values remain
configuration subject to SITL evidence and cannot exceed these maxima in v1.

## Initial payload encodings

- HEARTBEAT: `<session_nonce:u64, state:u8, ttl_ms:u16>`.
- SET_MODE: `<session_nonce:u64, requested_state:u8, ttl_ms:u16>`. State values
  are `0 DISABLED`, `1 STANDBY`, `2 READY`, `3 ACTIVE`, `4 DEGRADED`,
  `5 ABORTING`, `6 FAULT`. ACTIVE is control authority only after normal
  Betaflight arming checks are independently satisfied; it never arms.
- SET_STABILIZED_SETPOINT:
  `<session_nonce:u64, roll_cd:i16, pitch_cd:i16, yaw_rate_cds:i16,
  vertical_rate_cms:i16, ttl_ms:u16>`. Initial protocol bounds are roll/pitch
  ±3000 centidegrees, yaw rate ±18000 centidegrees/s, vertical rate ±300 cm/s,
  and TTL ≤100 ms. Firmware may impose tighter configured limits and slew
  limits. There is no throttle field.
- SET_PAYLOAD_STATE: `<session_nonce:u64, requested:u8, ttl_ms:u16>`, where
  `0` is OFF and `1` is ON. FC support is absent/default-off until reviewed
  hardware exists; unsupported requests are rejected and cannot select GPIO.
- ACK: `<acked_type:u8, acked_sequence:u32, result:u8>`.

- CAPABILITIES: `<protocol_version:u8, feature_bits:u32, max_payload:u16>`.
  Feature bits are initially zero: no payload GPIO or direct actuator feature.
- NODE_STATUS: `<state:u8, last_reject:u8, transition_count:u32>`.
- HEALTH: `<estimator_healthy:u8, control_healthy:u8, battery_mv:u16>`.
- FAULT: `<fault_code:u16, reject_reason:u8>`.

A v1 receiver rejects a recognized type whose payload length does not match
its implemented schema. Telemetry fields may be appended only in a new protocol
version; reserved capability bits must be zero.

## Reject codes

`0 OK`, `1 BAD_MAGIC`, `2 UNSUPPORTED_VERSION`, `3 UNSUPPORTED_TYPE`,
`4 BAD_LENGTH`, `5 BAD_CRC`, `6 VEHICLE_MISMATCH`, `7 SESSION_MISMATCH`,
`8 DUPLICATE`, `9 REORDERED`, `10 STALE`, `11 OUT_OF_RANGE`,
`12 INVALID_STATE`, `13 MANUAL_OVERRIDE`, `14 SAFETY_LOCKOUT`,
`15 FEATURE_DISABLED`.

Golden byte vectors are version-controlled in
`raspberry-pi/tests/vectors/uart_v1.json`. Any C implementation must consume the
same vectors rather than regenerate expected values inside its tests.
