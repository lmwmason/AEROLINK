# Observability

## Structured logs and correlation

- Every state change already goes through `AuditLog.append(kind, data)`
  (`server/src/aerolink_server/core.py`), which writes one structured,
  hash-chained JSON record (`{index, kind, data, previous}`) per event.
  `data` carries whatever ID applies: `vehicle`/`vehicle_id`, `mission`,
  `group_id` (inside a mission's own audit body), `request_id` (AI
  proposals), and `session` (node telemetry). `AuditLog.for_vehicle(id)`
  and `FleetServer.node_detail(id)` filter this trail per node.
- Each real-SITL Pi worker process writes one JSON line per event to its
  own `pi.jsonl` (see `raspberry-pi/src/aerolink_pi/vehicle_process.py`
  and `server/src/aerolink_server/real_sitl.py`), and each SITL instance
  emits one `[AEROLINK_METRICS] ...` line per second to its own log
  (`flight-controller/src/main/io/aerolink_sitl.c`) with accepted/
  rejected/dropped counters, parser backlog, and max task time — this is
  the FC-side protocol reject counter and per-instance trace.
- **Trace export**: `AuditLog.export()` returns the full chain plus a
  `chain_valid` flag (also `GET /api/audit/export`); a real-SITL run's
  `result.json` under its `--artifacts` directory is the equivalent trace
  for one 1/3/15-node exchange.
- **Log retention**: the repository does not retain logs itself —
  `artifacts/`, `evidence/`, and any `--artifacts` directory are
  git-ignored, reproducible, and left to the caller (or CI's
  `upload-artifact` retention) to keep or discard. There is no unbounded
  in-repo log growth to configure.

## Metrics

`server/src/aerolink_server/metrics.py` (`FleetServer.metrics`, `GET
/api/metrics` — see [`docs/openapi.yaml`](openapi.yaml)) is derived
entirely from the audit log plus a bounded rolling sample window, so it
can never disagree with an audit export of the same server:

- audit-entry counts by kind (a coarse per-event-type counter);
- AI validation outcomes (`valid`/`invalid`) — see
  [`docs/ai-safety-boundary.md`](ai-safety-boundary.md);
- mission transition counts (created/authorize/abort-request/
  abort-confirm/complete/restart-reconciliation);
- server restart-reconciliation and maintenance-event counts;
- packet latency and packet-age histograms (count/min/max/mean/p50/p95/p99)
  built from the last 2000 `update_sim_node` samples.

UART/FC-side counters (accepted/rejected/dropped/backlog/max task time)
are per-instance in each SITL's `[AEROLINK_METRICS]` log line rather than
aggregated into the server metrics endpoint, since the server never sees
raw UART frames — only the Pi's authenticated HTTP summary of them.

## Offline diagnostics bundle

`scripts/diagnostics_bundle.py` (run as part of the fast profile) writes
`<artifacts>/diagnostics/diagnostics.json`: Python/platform version, the
current git commit/branch/dirty flag, the AEROLINK feature-gate defaults,
an example metrics-snapshot shape, the most recent local
`test-report.json` if one exists, and the most recent SBOM/dependency-scan
evidence if `scripts/security_scan.py` has been run. Everything is passed
through `aerolink_server.security.redact` before being written, so no
field named like a secret is included, and the bundle never contains raw
UART/network payloads — only counts and summaries.
