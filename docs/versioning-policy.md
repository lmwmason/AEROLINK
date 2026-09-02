# Versioning policy

## Repository / release tags

Pre-1.0: `v0.MINOR.PATCH-software-only`. The `-software-only` suffix is
mandatory on every tag for as long as no physically actuating code path
exists, so it is never possible to mistake a tag for a flight-ready
release. Increment MINOR for a new capability (a new milestone from
`docs/software-verification-report.md`'s subsystem list); increment
PATCH for a fix that doesn't add capability (e.g. the concurrency and
reconciliation bug fixes in
[`docs/scale-test-report.md`](scale-test-report.md)). There is no `v1.0.0`
until a real flight controller, a real Pi, and a separately reviewed
physical-safety process exist — see `AGENT.md`'s hardware progression
and [`docs/limitations.md`](limitations.md).

## The two independent AEROLINK gates

`AEROLINK_SITL` (compile-time) and `--aerolink-vehicle` (runtime) are not
covered by semver: they are safety gates, not a feature flag meant to be
toggled by version. A future change that appears to "simplify" by
merging or defaulting either gate on is a breaking change requiring
explicit sign-off in `AGENT.md`'s terms, regardless of what version
number it would otherwise get.

## Protocol and schema versions

- `schemas/uart-v1.json` and `schemas/fleet-v1.json` are versioned
  independently of the repository tag (`v1` in the filename/`AEROLINK_VERSION`
  constant). A wire-format-breaking change gets a new schema version
  (`uart-v2.json`) and a new `AEROLINK_VERSION` constant so an old
  peer's HELLO negotiation fails closed and visibly, per
  `docs/protocol.md`, rather than silently misinterpreting frames.
- `schemas/state-machines.json` carries its own `schema_version` field
  (currently `1`); bump it when a state or transition is added or
  removed, not for a comment/formatting change.
- Every generated-evidence JSON document
  (`artifacts/test-report.json`, `evidence/sbom.spdx.json`,
  `evidence/dependency-scan.json`, `<artifacts>/state-exploration.json`,
  `<artifacts>/diagnostics/diagnostics.json`,
  `<artifacts>/reliability-soak.json`) carries its own `schema_version`
  for the same reason — a consumer should check it rather than assume
  the shape.

## What is NOT versioned formally

- Documentation prose (`docs/*.md`) — kept current by
  `scripts/validate_repo.py`'s link check and by
  `docs/release-checklist.md`, not by a version number.
- Measured evidence numbers (latency, CPU %, coverage percentages) —
  these are representative of one run, explicitly not a guaranteed
  contract; see the "representative" caveats throughout
  `docs/scale-test-report.md` and `docs/protocol-conformance.md`.
