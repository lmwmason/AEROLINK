# AEROLINK firmware monorepo

AEROLINK is an offline-first indoor cooperative-delivery research prototype for
up to 15 guarded quadcopters. Each vehicle has one Raspberry Pi connected by a
dedicated UART to one Betaflight flight controller. One central server is the
only MVP fleet coordinator.

The control trust path is deliberately two-hop:

```text
central server -> authenticated private LAN -> local Pi
               -> framed UART -> local Betaflight SITL transport endpoint
```

Neither hop may arm a vehicle or write motor outputs. Manual disarm, RC
takeover, and Betaflight safety logic always have higher authority than
companion input. AEROLINK FC functionality is disabled by default.

## Primary implementation folders

- `flight-controller/`: unmodified official Betaflight `2026.6.1` baseline at
  commit `6dbc4218fd6bc33bf16ea32c670304d4f89321d5`; see
  `flight-controller/UPSTREAM.md`.
- `raspberry-pi/`: per-vehicle Linux companion protocol and service code.
- `server/`: central deterministic fleet manager and advisory-AI boundary.

The simulation implementation includes the UART codec, a doubly gated SITL
endpoint, vehicle/server state machines, an HTTP fleet dashboard, Fake FC
replay, and real 1/3/15-node multiprocess transport validation. Stabilized
setpoints stop at the parser/state machine and are not connected to flight
control, arming, mixing, motors, or payload outputs. No hardware is operated.

## Setup and one-command test suites

Python 3.11 or newer is recommended; the test suite has no third-party runtime
dependency.

```sh
scripts/setup.sh        # checks the toolchain, generates test-only local credentials
scripts/test-fast.sh    # unit/protocol/state/security tests — seconds
scripts/test-all.sh     # + feature-off/on SITL builds and real 1/3-node runs
scripts/test-15-node.sh # + the 15-node real-SITL gate and a reliability soak
```

Or run any suite directly:

```sh
python3 -m unittest discover -s raspberry-pi/tests -v
PYTHONPATH=server/src:raspberry-pi/src python3 -m unittest discover -s server/tests -v
sh flight-controller/src/test/run_aerolink_native.sh
python3 server/tools/run_simulation.py
cd flight-controller && make TARGET=SITL AEROLINK_SITL=1 AUTOHYDRATE_SUBMODULES= BETAFLIGHT_CONFIG=src/config
PYTHONPATH=server/src:raspberry-pi/src python3 server/tools/run_real_sitl.py --nodes 1
PYTHONPATH=server/src:raspberry-pi/src python3 server/tools/run_real_sitl.py --nodes 3
PYTHONPATH=server/src:raspberry-pi/src python3 server/tools/run_real_sitl.py --nodes 15
```

## Where to go next

- `docs/software-verification-report.md` — what is verified, and where.
- `docs/architecture.md`, `docs/protocol.md`, `docs/sitl-transport.md`,
  `docs/hardware-matrix.md`, `docs/test-plan.md` — read before extending the
  control path.
- `docs/security-review.md`, `docs/threat-model.md`,
  `docs/ai-safety-boundary.md` — the security and AI-advisory boundaries.
- `docs/api-examples.md`, `docs/openapi.yaml` — the operator/node HTTP API.
- `docs/limitations.md` — what this repository does *not* prove.
- `CONTRIBUTING.md` — workflow, the hard non-actuating boundary, and where
  the rest of the developer-experience docs (`docs/coding-standards.md`,
  `docs/troubleshooting.md`, `docs/release-checklist.md`) live.
