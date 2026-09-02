# AGENT.md — AEROLINK Firmware Monorepo

## Mission

Build a Betaflight-based indoor cooperative-delivery prototype with three strictly separated subsystems:

- `flight-controller/`: an official Betaflight fork running on each flight controller;
- `raspberry-pi/`: the companion software running on one Raspberry Pi mounted on each drone.
- `server/`: the central fleet-management, mission-planning, AI-assistance and operator software.

Each of up to 15 vehicles has a dedicated wired UART link: `Raspberry Pi ↔ Flight Controller`. All vehicle Pis and one central management computer are connected to the same private local network without requiring internet access. Vehicle nodes communicate with the central server; the MVP does not use a Pi 1 leader.

Read `PRD.md` before modifying code. The user's latest instruction overrides these files.

## Repository layout

```text
/
├── AGENT.md
├── PRD.md
├── README.md
├── docs/
│   ├── architecture.md
│   ├── protocol.md
│   ├── safety-case.md
│   ├── test-plan.md
│   ├── hardware-matrix.md
│   └── decisions/
├── flight-controller/
│   └── <official Betaflight fork>
├── raspberry-pi/
    ├── src/
    ├── tests/
    ├── tools/
│   └── pyproject.toml
└── server/
    ├── src/
    ├── tests/
    ├── web/
    └── pyproject.toml
```

Do not nest a second Git repository unless the user explicitly chooses submodules. Prefer one monorepo with the Betaflight source imported into `flight-controller/` and its exact upstream commit recorded in `flight-controller/UPSTREAM.md`.

## Architecture boundary

### `flight-controller/` owns

- IMU, filtering, PID/rate/attitude stabilization;
- mixer, ESC/motor outputs, RC input, arming and failsafe;
- Blackbox and low-level health reporting;
- feature-gated UART command parser;
- bounded external stabilized-setpoint mode;
- command-age watchdog and manual takeover;
- guarded payload-output interface only after hardware is verified.

### `raspberry-pi/` owns

- UART connection and protocol client;
- indoor localization adapters;
- map, room graph and route planning;
- obstacle-avoidance interface;
- trajectory generation;
- local trajectory tracking and vehicle-side formation constraints;
- local mission execution state received from the server;
- fleet communication abstraction;
- locker/phone/backend adapter;
- logs, replay and simulation tools.

### `server/` owns

- registry, health and live state for up to 15 drone nodes;
- delivery request ingestion and validation;
- deterministic fleet availability and capability filtering;
- AI-assisted payload interpretation, drone-count recommendation, anomaly explanation and operator summaries;
- deterministic mission planner that validates or rejects all AI proposals;
- fleet selection, group assignment and formation planning;
- map/room graph, global route and traffic/conflict scheduling;
- mission state machine and commands to vehicle Pis;
- operator dashboard, authorization, abort and audit log;
- simulation orchestration, replay and system-wide metrics.

AI is advisory only. It may propose structured plans, classifications or explanations, but it cannot arm, dispatch, change active trajectories, control payload hardware or bypass deterministic validation. AI output must conform to a schema, include provenance/model version, pass rule-based validation and require the configured operator authorization before a real mission.

Never put SLAM, global route planning, phone/backend code or fleet coordination inside Betaflight. Never let Raspberry Pi software write motor outputs directly.

## Hardware assumptions

- One Raspberry Pi and one FC per drone.
- FC and Pi share signal ground and use verified logic levels; exact UART pins/voltage/baud remain `TBD` until the actual boards are identified.
- Raspberry Pi power and FC power integrity must be reviewed; do not assume the Pi can be powered from an arbitrary FC rail.
- Up to 15 Raspberry Pis and one management computer join one isolated private IPv4 LAN/WLAN. The system must operate with the internet physically unavailable.
- The central management computer is the only mission coordinator in MVP. Automatic server election is out of scope.
- Static vehicle IDs and configured node addresses are the authoritative mapping. Discovery may assist setup but must not silently change vehicle identity.
- Flight controller target, IMU, receiver, ESC, motor, duct, localization sensors, tension sensors and electromagnet driver remain `TBD` unless evidenced.

## Mandatory safety rules

- Do not flash an unconfirmed Betaflight target.
- Do not arm automatically from boot, UART connection, network command or phone request.
- RC/manual disarm and takeover outrank all Pi commands.
- External commands must be versioned, bounded, sequence-checked and freshness-checked.
- UART loss, Pi reboot, parser error or stale command must enter a deterministic tested safe state.
- Electromagnet output defaults off after boot/reset/disarm/fault and cannot activate from an invalid command.
- An autonomous coding agent may run source tests and SITL only. It must stop for human confirmation before flashing hardware, powering motors or energizing payload hardware.
- Hardware progression is: single-node SITL → selected-group simulation → full 15-node/server simulation → props-off bench → guarded single drone without payload → guarded multi-drone without payload → approved dummy-load testing.
- Do not test early builds in occupied corridors or near people.
- The 3 kg value is a design target, not a safe test authorization.

## Betaflight modification policy

- Fork only the official `betaflight/betaflight` repository and record the exact upstream commit/tag.
- Preserve GPL-3.0 notices.
- Keep changes minimal, feature-gated and easy to rebase.
- Default behavior must match upstream when AEROLINK is disabled.
- Prefer documented MSP v2 extensions or a narrowly scoped framed UART protocol.
- Never reuse upstream message IDs or feature bits without checking current source.
- Do not block gyro/PID critical paths or allocate dynamically there.
- Protocol parsing never writes motors; accepted setpoints enter existing limiting and stabilized-control paths.
- Measure flash/RAM/CPU/loop-time impact.

## UART protocol rules

The shared specification lives in `docs/protocol.md`; both folders implement against it. Every frame must define:

- magic/version/message type/length;
- vehicle ID and formation ID where relevant;
- sequence number and monotonic freshness information;
- payload with explicit units/scaling/ranges;
- integrity check;
- ACK/rejection reason where required.

Minimum UART messages: `HELLO`, `CAPABILITIES`, `HEARTBEAT`, `SET_MODE`, `SET_STABILIZED_SETPOINT`, `SET_PAYLOAD_STATE`, `NODE_STATUS`, `HEALTH`, `ACK`, `FAULT`.

## Private fleet network rules

- Up to 15 Pi nodes communicate with one central server across one configured private LAN/WLAN; no cloud or internet dependency is allowed in the control path.
- Use a versioned fleet protocol independent from the FC UART protocol.
- MVP topology is central server/vehicle node: the server publishes mission epochs, group assignments, formation references and synchronized trajectory segments; every Pi returns state and health.
- High-rate state/formation traffic may use bounded UDP unicast with sequence numbers, monotonic timestamps and expiry. Safety-relevant state changes require acknowledgement/retry or another explicitly reliable mechanism.
- Do not use unauthenticated broadcast commands for arming, mode entry, payload action or trajectory execution.
- Each node validates sender identity, mission epoch, vehicle ID, sequence, age and numeric bounds before accepting data.
- Network loss, excessive jitter or central-server loss must not be hidden by extrapolation beyond a short configured horizon. Enter the documented degraded/abort policy.
- A server network packet can influence only the local Pi mission/trajectory layer. The local Pi must still pass a bounded, fresh setpoint through UART, and the FC independently validates it.
- Log network receive time, packet age, sequence gaps, peer health, coordinator epoch and state transitions.

Test valid, truncated, corrupt, stale, duplicate, reordered, out-of-range and unsupported-version frames.

## State and authority

Required FC states: `DISABLED`, `STANDBY`, `READY`, `ACTIVE`, `DEGRADED`, `ABORTING`, `FAULT`.

Authority priority:

1. physical/manual disarm;
2. RC takeover;
3. FC safety conditions;
4. UART watchdog;
5. valid Raspberry Pi setpoint;
6. mission preference.

No unspecified transition may arm, raise authority or increase thrust.

## Development workflow

1. Inspect Git state, upstream source and repository instructions.
2. Establish an unmodified reproducible Betaflight baseline.
3. Document architecture and protocol before control changes.
4. Add host and firmware protocol tests.
5. Implement heartbeat/status and state machine.
6. Implement watchdog and manual override tests.
7. Add the smallest stabilized external-setpoint path.
8. Build Betaflight native/unit and `TARGET=SITL` tests.
9. Build Raspberry Pi unit/integration tests with a fake UART peer and a simulated private LAN.
10. Run 15 isolated SITL instances with 15 Pi processes and one server on a simulated private network; allow a lower-count smoke test before the full scale test.
11. Inject UART loss plus LAN loss, latency, jitter, corruption, node restart, server loss and simultaneous node faults.
12. Record results, performance impact and the next safe gate.

After each phase, update docs and provide evidence. Compilation alone is not completion.

## Definition of done

- Both folders build/test reproducibly.
- Protocol implementations share conformance vectors.
- AEROLINK-disabled FC behavior remains upstream-compatible.
- No UART/network packet can arm or directly command motors.
- Manual override, stale commands and Pi restart are tested.
- Three simulated nodes have unique identities and independent failure containment.
- Hardware assumptions are evidenced or explicitly `TBD`.
- No physical test is performed autonomously.
