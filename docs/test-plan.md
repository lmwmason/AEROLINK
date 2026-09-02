# Test plan and gates

## Automated suites

- Verify official upstream tag and commit and absence of nested Git metadata.
- Encode/decode fixed valid UART frames from golden hex.
- Reject bad magic, CRC, version, length, vehicle identity, unsupported type,
  duplicate/reordered sequence, stale frames, and out-of-range setpoints.
- Exercise arbitrary chunking, concatenated frames, noise resynchronization,
  bounded buffering, a fake duplex UART, handshake, and reconnect behavior.
- Confirm protocol enums expose no arming or direct-motor command.
- Compile the FC endpoint with/without `USE_AEROLINK`, covering state,
  watchdog, takeover, restart, and telemetry.
- Test Fake FC/Fake Server integration and authenticated fleet validation.
- Replay deterministic 1, 3, and 15-node Fake FC scenarios.
- Run 1, 3, and 15 independent Betaflight SITL/Pi process pairs, validate the
  exact HELLO golden vector, collect scheduler/resource metrics, and inject
  partial/corrupt TCP, latency/jitter, disconnect, Pi/SITL/server restart, stale
  session, and simultaneous-node faults.

## Later gates

The completed gate is transport-only. The next gate is a reviewed adapter into
an existing bounded Betaflight stabilized-control interface, still in SITL and
with actuator-invariance instrumentation. That integration remains
unimplemented and requires qualified adult-supervised review before any later
physical test. This repository does not authorize flashing or physical tests.
