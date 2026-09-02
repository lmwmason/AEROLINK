# Software verification report

Top-level index of what has been verified in this repository and where
the evidence lives. Everything here is software-only: no flight
controller has been flashed, no UART pin or payload GPIO has been
physically configured, and no motor or payload has been powered. Read
[`docs/limitations.md`](limitations.md) alongside this report before
acting on any number in it.

## Verification gates (`PRD.md` §10, items 1-7 — the items an autonomous
agent may complete)

| Gate | Status | Evidence |
|---|---|---|
| 1. Unmodified Betaflight baseline and SITL build | Done | `flight-controller/UPSTREAM.md`; feature-off (`sitl-feature-off`) and feature-on (`AEROLINK_SITL=1`, `sitl-feature-on`) builds both pass in every fast/all CI run |
| 2. Protocol unit/fuzz/conformance tests in both folders | Done | [`docs/protocol-conformance.md`](protocol-conformance.md) |
| 3. FC state-machine and watchdog tests | Done | `flight-controller/src/test/unit/aerolink_native_test.c`, `run_aerolink_native.sh`; `schemas/state-machines.json`'s `fc` machine, exhaustively explored by `scripts/state_explorer.py` |
| 4. One Pi process connected to one Betaflight SITL instance | Done | `server/tools/run_real_sitl.py --nodes 1`; see [`docs/simulation-report.md`](simulation-report.md) |
| 5. 15 Pi processes and one server on a simulated private LAN, each Pi UART-connected to its own SITL instance | Done (with a known flaky readiness probe, see below) | `server/tools/run_real_sitl.py --nodes 15`; [`docs/simulation-report.md`](simulation-report.md), [`docs/scale-test-report.md`](scale-test-report.md) |
| 6. Injected UART/LAN latency, jitter, loss, corruption, node restart, server restart/loss, simultaneous node faults | Done | The `faults` map in every `run_real_sitl.py` result (`corrupt_crc`, `tcp_partial`, `latency_jitter`, `pi_restart`, `sitl_restart`, `server_restart`, `stale_session_rejected`, `simultaneous_node_failure`, `unselected_node_failure`); additional server-scale reliability soak in [`docs/scale-test-report.md`](scale-test-report.md) |
| 7. Recorded route/formation simulation with no physical hardware | Done | The Home → Locker F1 → stairwell → Robotics Lab F2 → Home route replay recorded in every `run_real_sitl.py`/`run_simulation.py` result |

Gates 8-9 (a human-approved props-off bench test and the separately
reviewed guarded physical progression) are explicitly out of scope for
autonomous work; see `AGENT.md`'s mandatory safety rules and
[`docs/limitations.md`](limitations.md).

## Test suite summary (representative counts; read `artifacts/test-report.json`
for the current run's actual numbers, not this table)

| Suite | Count | Command |
|---|---:|---|
| FC native (golden vectors, state machine, watchdog) | — | `sh flight-controller/src/test/run_aerolink_native.sh` |
| Raspberry Pi (`raspberry-pi/tests`) | 16 | `python3 -m unittest discover -s raspberry-pi/tests` |
| Server (`server/tests`) | 45 | `PYTHONPATH=server/src:raspberry-pi/src python3 -m unittest discover -s server/tests` |
| Fake-FC fleet replay (1/3/15) | 3 sub-tests | `python3 server/tools/run_simulation.py` |
| Protocol verification (generated cases/mutations/coverage) | 505 generated, 256 mutations | `python3 scripts/protocol_coverage.py` |
| State-space exploration (5 machines) | 34 states, 71 edges | `python3 scripts/state_explorer.py` |
| Security/dependency scan + SBOM | — | `python3 scripts/security_scan.py` |
| Repository validation (docs links, JSON/Python/shell syntax, actuator-boundary scan) | — | `python3 scripts/validate_repo.py` |
| Real Betaflight SITL, 1/3/15 nodes | — | `python3 server/tools/run_real_sitl.py --nodes {1,3,15}` |

One-command entry points: `scripts/test-fast.sh` (everything above except
the two builds and the 3/15-node real runs), `scripts/test-all.sh` (adds
both builds and the 1/3-node real runs), `scripts/test-15-node.sh` (the
feature-on build, the 15-node real run, and the reliability soak). See
[`docs/ci.md`](ci.md).

## By subsystem

- **Protocol** — [`docs/protocol-conformance.md`](protocol-conformance.md).
- **State machines** — exhaustively explored (not sampled) by
  `scripts/state_explorer.py` against `schemas/state-machines.json`;
  cross-checked against the Python implementations in
  `server/tests/test_state_models.py`.
- **Security/authentication** — [`docs/security-review.md`](security-review.md),
  [`docs/threat-model.md`](threat-model.md).
- **Server persistence, mission workflow, reservations** — see the commit
  "Add SQLite persistence, mission workflow, reservations, and
  maintenance" and `server/tests/test_storage.py`; restart reconciliation
  is verified to never resume an old mission or reuse an old epoch.
- **Advisory AI boundary** — [`docs/ai-safety-boundary.md`](ai-safety-boundary.md);
  every allowed task validated, with an adversarial evaluator set in
  `server/tests/fixtures/ai_evaluator_cases.json`.
- **Observability** — [`docs/observability.md`](observability.md).
- **Reliability/scale** — [`docs/scale-test-report.md`](scale-test-report.md),
  including two real bugs this pass found and fixed (a `FleetServer`
  thread-safety race and a restart-reconciliation reservation leak).

## Known open items

- The real 15-node SITL gate has a pre-existing, host-load-dependent
  flaky readiness probe; it has passed on retry every time observed in
  this repository's history. See [`docs/scale-test-report.md`](scale-test-report.md).
- Actual MCU flash/RAM/CPU/loop-time impact is unmeasured — see
  [`docs/limitations.md`](limitations.md).
- No real AI provider, no production identity provider, no HSM/KMS
  integration — see [`docs/ai-safety-boundary.md`](ai-safety-boundary.md)
  and [`docs/security-review.md`](security-review.md).
