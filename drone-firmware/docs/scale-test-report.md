# Scale and reliability test report

Software-only evidence. See [`docs/simulation-report.md`](simulation-report.md)
for the real Betaflight-SITL 1/3/15-node transport gates (unique ports,
conformance vectors, fault injection, measured host-process resource
use) — that report is not duplicated here.

## What this report covers

`server/tests/test_reliability.py` (unit/integration, part of the fast
profile) and `scripts/reliability_soak.py` (part of the `15-node` /
weekly-scale CI profile, wired in `scripts/run_tests.py`) exercise
`FleetServer`, `SqliteRepository`, and `SimulationHttpServer` at server
scale — deliberately not by spawning real Betaflight processes, which
`server/tools/run_real_sitl.py` already covers and which is expensive to
run repeatedly. Nothing here connects a setpoint to flight-control
behavior.

| Requirement | Where it is exercised |
|---|---|
| Repeated 15-node registration cycles | `test_repeated_15_node_registration_cycles_bounded_state`; soak script's 200-cycle registration phase |
| Bounded memory checks | `test_metrics_sample_window_stays_bounded_under_long_telemetry_soak` (rolling window capped at 2000 samples after 3000 updates); soak script reports RSS growth |
| Server restart loops | `test_repeated_restart_reconciliation_cycles` (10 cycles); soak script's 20-cycle restart phase reporting DB write latency |
| Concurrent delivery requests | `test_concurrent_delivery_requests_never_double_assign_a_vehicle` (6 threads racing `create_mission`) |
| Duplicate mission submissions | `test_duplicate_mission_submission_cannot_reuse_assigned_vehicles` |
| Insufficient available fleet | `test_insufficient_available_fleet_is_rejected` |
| Mixed healthy/degraded/maintenance fleet | `test_mixed_healthy_degraded_maintenance_only_healthy_available_allocated` |
| Database unavailable | `test_write_after_repository_closed_raises_instead_of_silently_dropping` |
| Slow dashboard client | `test_slow_sse_client_does_not_block_a_concurrent_fast_client` |
| Graceful shutdown / orphan-process detection | `test_graceful_shutdown_frees_the_port_for_a_new_server`; `server/src/aerolink_server/real_sitl.py`'s `Supervisor.close()` terminates every SITL process it started, waits, then SIGKILLs on timeout |
| CPU/RSS/FD/queue depth/DB latency/dropped messages | reported by `scripts/reliability_soak.py` (see below) |
| Randomized packet damage, queue saturation (UART-level) | already covered by `raspberry-pi/tests/test_protocol_properties.py` (mutation/fuzz tests) and the real-SITL fault matrix's `corrupt_crc`/`tcp_partial` checks — not duplicated at the server layer, which never sees raw UART frames |

## A concurrency bug this testing found and fixed

Writing `test_concurrent_delivery_requests_never_double_assign_a_vehicle`
against `SimulationHttpServer` (a `ThreadingHTTPServer`) surfaced that
`FleetServer`'s state-mutating methods were not thread-safe:
`allocate()` and `create_mission()` were two separate, unsynchronized
steps, so two concurrent `POST /api/missions` calls could both read the
same "available" vehicle before either wrote its assignment, double
allocating a vehicle to two missions. `FleetServer` now holds a
`threading.RLock()` around every state-mutating method
(`server/src/aerolink_server/core.py`); this is an application-layer
concurrency fix, not a protocol or AEROLINK-gate change.

## A restart-reconciliation bug this testing found and fixed

`test_repeated_restart_reconciliation_cycles` (running 10 back-to-back
create→authorize→restart cycles) caught a second bug: `_reconcile()`
restored a corridor/stairwell reservation for any persisted mission that
was not `PLANNED`/`AUTHORIZED` — including a mission the *previous*
restart's reconciliation had already force-transitioned to
`ABORT_REQUESTED` — so the reservation was silently re-created on every
subsequent restart and never released, letting one stuck mission
permanently block that corridor. `_reconcile()` no longer restores
reservations for any persisted mission; only a live `AUTHORIZED` mission
created after the current reconciliation holds one, and every
non-terminal persisted mission's reservation (and vehicles) are released
during reconciliation instead.

## Measured evidence (representative run, this host)

```json
{
  "registration_cycles": 200, "mission_cycles": 50, "restart_cycles": 20,
  "max_mission_queue_depth": 1, "dropped_or_rejected_missions": 0,
  "reconciliation_ok_after_restart_cycles": true,
  "db_write_latency_ms": {"count": 20, "mean": 0.11, "max": 0.13},
  "http_request_latency_ms": {"count": 100, "mean": 16.9, "max": 1064.3},
  "http_errors": 0,
  "resource": {"rss_kb_growth": 5784, "fd_growth": 0}
}
```

This is one representative run on the CI/dev host, not a performance
guarantee; the exact numbers vary with host load. `http_errors` and
`reconciliation_ok_after_restart_cycles` are the pass/fail gate the
script exits non-zero on; the latency/resource numbers are evidence, not
thresholds. The one high `max` HTTP latency observed above is thread
start/connect overhead on the very first concurrent batch, not a
representative steady-state number — see `http_request_latency_ms.mean`.

## A known flaky gate this testing did not touch

The real 15-node `server/tools/run_real_sitl.py` gate occasionally times
out waiting for one SITL instance's TCP-UART readiness probe under host
load (observed independently of any change in this work — see the
retries already present in this repository's commit history for the
same symptom). This is a transport/orchestration timing characteristic,
not a server-layer reliability issue, and fixing it would mean touching
`flight-controller/src/main/drivers/serial_tcp.c` or
`server/src/aerolink_server/real_sitl.py`'s readiness probe — outside
this reliability-testing pass's scope, and risks weakening an existing
gate rather than hardening it. It has been observed to pass on retry
every time in this session; if it becomes a recurring CI problem, treat
it as a distinct transport-layer investigation.
