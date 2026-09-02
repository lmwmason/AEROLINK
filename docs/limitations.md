# Limitations

Everything in this repository is software-only evidence. Read this
alongside [`docs/simulation-report.md`](simulation-report.md),
[`docs/sitl-transport.md`](sitl-transport.md), and
[`docs/ai-safety-boundary.md`](ai-safety-boundary.md).

## Scope

- No flight controller has been flashed, no UART pin or payload GPIO has
  been physically configured, and no motor or payload has been powered.
  `SET_STABILIZED_SETPOINT` reaches only the SITL transport endpoint's
  parser/state machine (`flight-controller/src/main/io/aerolink_sitl.c`);
  it is not wired to PID, attitude, RC, throttle, mixer, motor, servo,
  arming, or payload GPIO code, and `scripts/validate_repo.py` fails the
  build if any of those headers/symbols appear in that file.
- Betaflight is built with `AEROLINK_SITL` unset by default (feature-off);
  the feature-on build requires both `AEROLINK_SITL=1` at compile time and
  `--aerolink-vehicle` at runtime. Neither gate has been relaxed.
- No real vehicle performance, flight behavior, or physical timing is
  demonstrated by anything in this repository.

## What is unverified

- **MCU resource use.** The measured flash/RAM/CPU numbers in
  `docs/simulation-report.md` are for the x86 host `TARGET=SITL` build,
  not any real flight-controller MCU. The actual target board is `TBD`
  (see `AGENT.md` "Blocking hardware decisions"); flash/RAM headroom and
  loop-time impact on real hardware are unknown until that target exists.
- **UART electrical/timing behavior.** The real transport in this repo is
  a loopback TCP socket standing in for a physical UART; baud rate, pin
  assignment, logic levels, and real serial-line noise/jitter are not
  modeled.
- **Localization, obstacle avoidance, and cable/formation dynamics.**
  PI-3/PI-5 in `PRD.md` are interface-only; the actual sensors and cable
  physics remain `TBD` and are not validated here.
- **A real AI provider.** `server/src/aerolink_server/ai.py` only ships
  `DeterministicFakeProvider`; see the "What is not proven here" section
  of `docs/ai-safety-boundary.md` for what a real model integration would
  still need before this boundary could be trusted against it.
- **Multi-user/production secret management.** `security.py`'s
  `load_secret` reads a key from an environment variable or an
  owner-only-permission file; there is no HSM/KMS integration, and node
  key provisioning at fleet scale remains a manual/TBD process (see
  `docs/threat-model.md`).
- **Availability of the isolated LAN and Pi OS integrity.**
  `docs/threat-model.md` states these as assumptions, not something this
  repository proves.

## Path to physical hardware

Per `AGENT.md`'s mandatory safety rules, the required progression is:
single-node SITL → selected-group simulation → full 15-node/server
simulation → props-off bench test → guarded single drone without payload
→ guarded multi-drone without payload → approved dummy-load testing. This
repository's autonomous work stops at the software simulation gates
(`PRD.md` verification gates 1-7). Every step from a human-approved
props-off bench test onward requires qualified adult supervision and a
separate physical safety review; no automated agent may perform it. The
3 kg carry target is a design target, not a safe test authorization.
