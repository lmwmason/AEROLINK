# Coding standards

## Python (`server/`, `raspberry-pi/`, `scripts/`)

- No third-party runtime dependency (`server/pyproject.toml`,
  `raspberry-pi/pyproject.toml` list none). If a task seems to need one,
  prefer a small dependency-free implementation — see
  `server/src/aerolink_server/metrics.py`'s hand-rolled histogram/
  percentile functions and `ai.py`'s hand-rolled schema validator for the
  established pattern, and `scripts/security_scan.py`/`state_explorer.py`
  for the same in tooling.
- The existing modules (`core.py`, `security.py`, `http_api.py`, `ai.py`,
  `metrics.py`, `storage.py`) use a deliberately dense, single-line-per-
  statement style (`;`-separated) for short, self-contained methods. Match
  it for code at that level (small, well-named methods); do not force a
  long or branching function onto one line just for consistency — clarity
  wins once a method needs more than a few statements or a real
  control-flow decision (see `_reconcile()` for the threshold in
  practice: it takes multiple physical lines with comments once the logic
  is non-trivial and safety-relevant).
- Type hints on public function signatures (`from __future__ import
  annotations` + hints), but no strict type-checker is wired in; don't
  add one without discussing it, since it would be the project's first
  external dev-dependency.
- Comments are reserved for the *why*, especially for a safety-relevant
  or non-obvious decision (see `_reconcile()`'s comment on why
  reservations are never restored from persisted state, or `ai.py`'s
  module docstring). Don't restate what the code already says.
- Tests use `unittest` (stdlib only), one file per module under test,
  named `test_<module>.py`. Prefer one assertion-rich test over many
  trivial ones when they share setup, matching the existing files.

## C (`flight-controller/`)

- This is an official Betaflight fork: match upstream style in files you
  did not create, and keep AEROLINK-specific files
  (`io/aerolink.c/.h`, `io/aerolink_sitl.c/.h`) feature-gated behind
  `USE_AEROLINK` so the default build is byte-for-byte upstream behavior.
- Preserve GPL-3.0 notices; keep changes minimal, feature-gated, and easy
  to rebase against upstream — see `AGENT.md`'s Betaflight modification
  policy for the full rule set (never block gyro/PID critical paths, no
  dynamic allocation there, measure flash/RAM/CPU/loop-time impact).
- `aerolink.c` compiles both as part of the firmware and as a native host
  test (`AEROLINK_NATIVE_TEST`, see
  `flight-controller/src/test/run_aerolink_native.sh`) — keep it free of
  anything that only exists in the firmware build environment, or gate it
  behind `#ifndef AEROLINK_NATIVE_TEST`.

## Schemas and generated code

- `schemas/*.json` is the reviewed source of truth; generated code
  (`raspberry-pi/src/aerolink_pi/generated_protocol.py`) is committed, not
  built at test time, so a diff is visible in review. Regenerate with
  `python3 scripts/generate_protocol.py`; CI's `--check` fails if the
  committed file doesn't match.
- State machines belong in `schemas/state-machines.json`, not
  re-declared ad hoc in code — see `server/tests/test_state_models.py`
  for how an implementation (e.g. `MISSION_TRANSITIONS` in `core.py`) is
  asserted to match the schema exactly.

## Documentation

- A doc that states a measured number (latency, coverage, byte counts) is
  representative evidence from one run, not a guarantee — say so
  explicitly (see the pattern in `docs/scale-test-report.md` and
  `docs/protocol-conformance.md`) rather than implying every future run
  will match.
- Every relative Markdown link must resolve;
  `scripts/validate_repo.py` checks this in CI.
