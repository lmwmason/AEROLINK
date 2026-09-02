# Betaflight SITL transport

This gate is software-only and non-actuating. AEROLINK is compiled only for the
SITL target when `AEROLINK_SITL=1` is passed to `make`; it is then enabled at
runtime only when `--aerolink-vehicle 1..15` is passed. Both gates default off.

The endpoint owns simulated UART8. Instance `n` (zero based) listens on TCP
port `5768 + 64*n`; UART1 uses `5761 + 64*n`. No physical UART pins, baud, or
electrical properties are selected by this mapping. The supervisor assigns
vehicle `i` to instance `i-1`, so the 15 AEROLINK ports are 5768, 5832, …,
6664. Simulator UDP ports are separated by an independent instance offset.

The low-priority 200 Hz scheduler task reads at most 256 bytes and produces at
most 16 telemetry frames per invocation. Its parser buffer is bounded at 533
bytes. It implements HELLO, CAPABILITIES, HEARTBEAT, NODE_STATUS, HEALTH,
ACK/REJECT, FAULT encoding, session reset, and watchdog state updates. Exact
wire conformance starts with `raspberry-pi/tests/vectors/uart_v1.json`.

Build and run from the repository root:

```sh
make -C flight-controller TARGET=SITL AEROLINK_SITL=1 AUTOHYDRATE_SUBMODULES= BETAFLIGHT_CONFIG=src/config
PYTHONPATH=server/src:raspberry-pi/src python3 server/tools/run_real_sitl.py --nodes 1
PYTHONPATH=server/src:raspberry-pi/src python3 server/tools/run_real_sitl.py --nodes 3
PYTHONPATH=server/src:raspberry-pi/src python3 server/tools/run_real_sitl.py --nodes 15
```

Each run creates a temporary artifact directory unless `--artifacts PATH` is
given. It contains per-node SITL logs, Pi JSONL logs, and `result.json`.
Startup, port readiness, process deadlines, restart, termination, and log
collection are deterministic. The HTTP server binds only to `127.0.0.1` and
requires the configured bearer token for registration and telemetry writes.

`SET_STABILIZED_SETPOINT` is validated and acknowledged only. The transport
source has no PID, attitude, RC, arming, mixer, motor, or payload dependency;
there is deliberately no adapter beyond the state machine. An accepted frame
therefore cannot change those outputs in this gate.
