# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/);
versioning follows [`docs/versioning-policy.md`](docs/versioning-policy.md).
Nothing has been tagged yet — everything below is `Unreleased`.

## Unreleased

Software-only. See
[`docs/software-verification-report.md`](docs/software-verification-report.md)
for full evidence and [`docs/limitations.md`](docs/limitations.md) for
what remains unverified.

### Added

- Betaflight upstream baseline (`2026.6.1`) with a feature-gated,
  doubly-gated (`AEROLINK_SITL` compile-time + `--aerolink-vehicle`
  runtime) non-actuating UART transport endpoint and FC-side state
  machine/watchdog.
- Shared UART v1 and fleet-LAN protocol libraries, generated from
  `schemas/uart-v1.json`/`fleet-v1.json`, with golden-vector, property-
  based, mutation, and fuzz-corpus tests
  ([`docs/protocol-conformance.md`](docs/protocol-conformance.md)).
- Exhaustive state-space verification of all five system state machines
  (`schemas/state-machines.json`) via `scripts/state_explorer.py`.
- Raspberry Pi vehicle service and central `FleetServer`: deterministic
  registry/allocation, a schema-conformant mission workflow
  (`PLANNED -> AUTHORIZED -> ABORT_REQUESTED -> ABORTED | COMPLETED`),
  corridor/stairwell reservations, and maintenance status.
- Optional SQLite persistence (`aerolink_server.storage`) with restart
  reconciliation that never resumes an old mission or replays an old
  mission epoch.
- Mutual node/server HMAC authentication, role-scoped operator sessions,
  replay/rate/size limits, secure secret loading, log redaction, and a
  hash-chained audit log with tamper detection
  ([`docs/security-review.md`](docs/security-review.md),
  [`docs/threat-model.md`](docs/threat-model.md)).
- Authenticated operator HTTP API (mission workflow, maintenance, node
  detail, mission history, health timeline, hash-chained audit export,
  metrics, an SSE dashboard stream) documented in
  [`docs/openapi.yaml`](docs/openapi.yaml).
- Provider-neutral advisory AI boundary (deterministic fake provider,
  strict per-task schemas, a forbidden-control-token scan, domain-rule
  validation, deterministic fallback, full audit provenance, and a
  reviewed adversarial evaluator set) —
  [`docs/ai-safety-boundary.md`](docs/ai-safety-boundary.md).
- Audit-derived metrics endpoint and an offline, redacted diagnostics
  bundle — [`docs/observability.md`](docs/observability.md).
- Reproducible CI (`scripts/test-fast.sh`/`test-all.sh`/`test-15-node.sh`,
  machine-readable `test-report.json`, per-case log bundles) —
  [`docs/ci.md`](docs/ci.md).
- Real Betaflight-SITL 1/3/15-node multiprocess transport validation
  with fault injection (corrupt/partial frames, latency/jitter, Pi/SITL/
  server restarts, stale session, simultaneous node failure) —
  [`docs/simulation-report.md`](docs/simulation-report.md).
- Server-scale reliability/soak testing
  ([`docs/scale-test-report.md`](docs/scale-test-report.md)): repeated
  registration/restart cycles, concurrent-request safety, mixed fleet
  health, database-unavailable and slow-client behavior.
- Developer experience: `scripts/setup.sh`,
  `scripts/generate_dev_credentials.py`, `config/dev.env.example`,
  [`docs/api-examples.md`](docs/api-examples.md),
  [`CONTRIBUTING.md`](CONTRIBUTING.md),
  [`docs/coding-standards.md`](docs/coding-standards.md),
  [`docs/troubleshooting.md`](docs/troubleshooting.md),
  [`docs/release-checklist.md`](docs/release-checklist.md).

### Fixed

- `FleetServer` state-mutating methods were not thread-safe against
  `SimulationHttpServer`'s `ThreadingHTTPServer`, allowing two concurrent
  delivery requests to double-assign the same vehicle. Now guarded by a
  `threading.RLock()`.
- Restart reconciliation could silently re-create a corridor/stairwell
  reservation for a mission a previous restart had already force-aborted,
  permanently blocking that corridor across repeated restarts.
  Reservations are no longer restored from persisted mission state.

### Explicitly not done (by design)

- No flight-control, arming, mixer, motor, RC-control, or payload
  adapter exists or is planned by an automated process — see `AGENT.md`
  and [`docs/limitations.md`](docs/limitations.md).
- No physical hardware has been operated.
