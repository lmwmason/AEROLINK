# Protocol conformance

Covers `docs/protocol.md`'s UART v1 wire format and the fleet-LAN
protocol (`raspberry-pi/src/aerolink_pi/fleet.py`). Both are described in
`schemas/uart-v1.json` and `schemas/fleet-v1.json`, and
`raspberry-pi/src/aerolink_pi/generated_protocol.py` is generated from
those schemas by `scripts/generate_protocol.py` (`--check` verifies the
committed file is reproducible from the schema; this runs in every fast
CI profile as part of `repo-validation`).

## What is verified, and where

| Property | Test |
|---|---|
| Golden vectors decode/re-encode exactly; invalid vectors reject with a fixed reason | `raspberry-pi/tests/test_protocol.py::GoldenVectorTests` against `raspberry-pi/tests/vectors/uart_v1.json` (3 valid, 5 invalid, shared with the FC native test via `flight-controller/src/test/unit/aerolink_native_test.c`) |
| CRC and vehicle-identity rejection, sequence duplicate/reorder/wrap, stream chunking/noise/concatenation, setpoint bounds, no arm message | `raspberry-pi/tests/test_protocol.py::ProtocolTests` |
| Endian/numeric-boundary and sequence-wraparound property tests (500 seeded cases plus explicit `0`, `1`, `0x7fffffff`, `0xfffffffe`, `0xffffffff`) | `raspberry-pi/tests/test_protocol_properties.py::test_seeded_roundtrip_endian_and_boundaries` |
| Mutation testing (256 single-bit-flip mutations of the golden HELLO vector) and a bounded 64 KiB noise/resource-exhaustion stream | `test_seeded_mutations_and_stream_resource_bound` |
| Session-nonce collision handling on reconnect | `test_sequence_wrap_and_nonce_collision` (mocks `secrets.randbits` to force a collision, asserts the retry produces a distinct session) |
| Fleet-packet version/epoch rollback and canonical-size limits | `test_fleet_version_epoch_rollback_and_size` |
| The generated schema contains no actuator command | `test_generated_schema_has_no_actuator_command` (also enforced independently by `scripts/validate_repo.py`'s scan of `aerolink_sitl.c` for flight/mixer/motor/RC/arming symbols) |
| Oversized-payload / parser allocation limits | `RX_BUDGET_PER_RUN`/`TELEMETRY_BUDGET_PER_RUN` in `flight-controller/src/main/io/aerolink_sitl.c` bound per-scheduler-tick work; `MAX_HTTP_BODY` (16 KiB) bounds the fleet-side HTTP body in `server/src/aerolink_server/security.py` |
| Partial-read / stream-resynchronization | `test_stream_arbitrary_chunks_noise_and_concatenation`; the real-SITL harness additionally sends the golden HELLO vector as deliberately split TCP writes (`sitl_client.py`'s `send_raw(..., chunks=...)`) |
| Cross-version compatibility | `AEROLINK_VERSION` is checked on HELLO; an unsupported version is a fixed rejection code, exercised by the golden invalid-vector set |
| A byte-identical golden vector actually accepted by the real FC transport, not just the offline decoder | `server/src/aerolink_server/real_sitl.py`'s `golden_vector_match` fault check (see `docs/simulation-report.md`) |

`scripts/protocol_coverage.py` (part of the fast profile as
`protocol-verification`) runs the protocol-focused test modules under
`trace.Trace` and reports executable/hit line counts for
`aerolink_pi/protocol.py` and `aerolink_pi/fleet.py`, plus the generated
case/mutation counts, so a coverage regression is visible in every run's
`artifacts/test-report.json` without a third-party dependency. A
representative run: 12 tests, 505 generated cases, 256 mutations, 0
actuator commands found; `protocol.py` and `fleet.py` line coverage
varies run to run as tests are added — read the current number from
`artifacts/protocol-coverage.json` rather than this document, which is
not kept in sync with every commit.

## Fuzz corpus

`raspberry-pi/tests/fuzz_corpus/seeds.hex` (see its own README) is a
small, reviewed seed corpus — empty/noise, the exact valid HELLO vector,
an oversized length prefix, and a corrupted-CRC frame — that the
deterministic property tests mutate and replay rather than depending on
an external, non-reproducible fuzzer.

## State-machine conformance

`schemas/state-machines.json` is the single machine-readable source for
all five state machines in this system (FC AEROLINK, Pi mission, server
mission, fleet-node lifecycle, and server restart-reconciliation).
`scripts/state_explorer.py` (part of the fast profile as
`state-exploration`) exhaustively explores the transition table for each
machine — 34 states and 71 explicit edges combined — and asserts:

- every table is total (every listed state has a transition entry, every
  transition target is itself a listed state);
- the FC's two `direct_forbidden` edges (`DISABLED -> ACTIVE`,
  `FAULT -> ACTIVE`) are absent from the transition table;
- stale input cannot raise authority, network recovery cannot skip
  reconciliation, restart cannot resume an old mission, and AI cannot
  create an executable command (a keyword scan of the whole schema for
  `AI_COMMAND`/`ARM`/`MOTOR`/`THROTTLE`/`PAYLOAD_ACTIVATE`).

`server/tests/test_state_models.py` additionally asserts the *Python*
implementations match the schema exactly (`aerolink_pi.service.TRANSITIONS`
for `pi_mission`; `aerolink_server.core.MISSION_TRANSITIONS` for
`server_mission`), so the schema cannot silently drift from the code
that enforces it — see [`docs/ai-safety-boundary.md`](ai-safety-boundary.md)
for how the AI boundary is verified against the same "no executable
command" property.
