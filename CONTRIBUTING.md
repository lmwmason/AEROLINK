# Contributing

Read `AGENT.md` and `PRD.md` first — they are the authoritative
architecture boundary and mandatory safety rules for this repository, and
they take precedence over anything below.

## Before you start

1. `scripts/setup.sh` — checks the toolchain, makes scripts executable,
   generates test-only local credentials.
2. `scripts/test-fast.sh` — should pass on a clean checkout in seconds.
3. Read `docs/software-verification-report.md` for what is already
   verified and where, so you don't re-derive it from scratch.

## The hard boundary

This repository is, and must remain, physically non-actuating:

- `SET_STABILIZED_SETPOINT` may reach only the transport parser/state
  machine (`flight-controller/src/main/io/aerolink_sitl.c`), never PID,
  attitude, RC, throttle, mixer, motor, servo, arming, or payload GPIO
  code. `scripts/validate_repo.py` enforces this with a keyword scan and
  fails the build if it is violated — do not weaken or remove that check.
- Do not implement physical flight instructions, target pin assignments,
  flashing, motor tests, or payload activation.
- Do not weaken the `AEROLINK_SITL=1` compile-time gate or the
  `--aerolink-vehicle` runtime gate.
- If a change would connect network/UART data to an actuator or
  flight-control path, stop and say so instead of implementing it — that
  requires a separate, explicitly authorized safety review (see
  `AGENT.md`'s hardware-progression rule).

## Workflow

1. Run the relevant test suite before and after your change
   (`scripts/test-fast.sh` at minimum; `scripts/test-all.sh` if you
   touched the FC transport or the real-SITL harness).
2. Keep commits coherent and scoped — one logical change per commit, in
   the spirit of this repository's existing history (CI, protocol/state
   verification, security, persistence/API, AI boundary, observability,
   reliability, documentation were each their own commit).
3. Update the relevant `docs/*.md` in the same change, not as a
   follow-up — `scripts/validate_repo.py` checks that every relative
   Markdown link resolves.
4. If you touch a schema (`schemas/*.json`) or the generated protocol
   file, run `python3 scripts/generate_protocol.py` and commit the
   regenerated output; `--check` in CI fails if it's out of date.
5. Never commit a real secret or credential. `scripts/security_scan.py`
   scans for likely secrets, but it is a heuristic, not a guarantee — see
   `docs/security-review.md`.

See `docs/coding-standards.md` for style, `docs/troubleshooting.md` for
common local failures, and `docs/release-checklist.md` before tagging a
release.
