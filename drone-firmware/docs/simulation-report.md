# Simulation report — 2026-09-02

## Scope and result

The non-actuating transport gate passed. No flight controller was flashed, no
physical UART pin or payload GPIO was configured, and no motor or payload was
powered. The official Betaflight base remains tag `2026.6.1`, commit
`6dbc4218fd6bc33bf16ea32c670304d4f89321d5`.

There are three distinct evidence layers:

- Fake FC tests: dependency-free protocol, vehicle-service, deterministic
  fleet, AI-validator, and fault semantics. These remain fast unit/integration
  tests and do not claim Betaflight execution.
- Real Betaflight SITL transport: independent OS processes exchange UART v1
  frames over TCP UART8. The exact existing vehicle-1 HELLO golden vector is
  accepted before fresh session negotiation. Fifteen Pi processes register
  through authenticated HTTP with the central simulation server.
- Disconnected features: the accepted stabilized setpoint is retained only as
  state-machine timing. There is no attitude/PID, throttle, RC, arming, mixer,
  motor, servo, or payload adapter. Flight-control behavior is therefore not
  implemented or validated by this gate.

## Automated suites

Commands and latest results:

```sh
PYTHONPATH=raspberry-pi/src python3 -m unittest discover -s raspberry-pi/tests -v
# 11 tests passed

PYTHONPATH=server/src:raspberry-pi/src python3 -m unittest discover -s server/tests -v
# 7 tests passed, including 1/3/15 Fake FC subtests and HTTP authorization/UI

sh flight-controller/src/test/run_aerolink_native.sh
# native golden/state/watchdog suite and feature-off compile passed

make -C flight-controller TARGET=SITL AUTOHYDRATE_SUBMODULES= BETAFLIGHT_CONFIG=src/config
# default, AEROLINK endpoint absent: text=441023 data=2524 bss=79240 total=522787

make -C flight-controller TARGET=SITL AEROLINK_SITL=1 AUTOHYDRATE_SUBMODULES= BETAFLIGHT_CONFIG=src/config
# gated endpoint present: text=448000 data=2564 bss=80008 total=530572

PYTHONPATH=server/src:raspberry-pi/src python3 server/tools/run_real_sitl.py --nodes 1
PYTHONPATH=server/src:raspberry-pi/src python3 server/tools/run_real_sitl.py --nodes 3
PYTHONPATH=server/src:raspberry-pi/src python3 server/tools/run_real_sitl.py --nodes 15
# all passed
```

## Real multiprocess results

| Setup | SITL/Pi pairs | Registered | Selected | Peak task | Peak backlog | Max packet latency | RSS growth |
|---|---:|---:|---|---:|---:|---:|---:|
| 1 node | 1 | 1 | 1 | 80 µs | 167 B | 10.4 ms | 128 KiB |
| 3 nodes | 3 | 3 | 1,2,3 | 81 µs | 167 B | 10.4 ms | 0 B |
| 15 nodes | 15 | 15 | 1,2,3 | 313 µs | 167 B | 10.6 ms | 0 B |

The 15-node initial exchange consumed 207 aggregate Linux scheduler ticks over
1.51 seconds across the SITL processes, or 137.3% of one host CPU core in
aggregate. This is host-process evidence, not embedded MCU CPU or loop-time
evidence. The route replay was Home → Locker F1 → stairwell →
Robotics Lab F2 → stairwell → Locker F1 → Home under unique `mission-1` and
`group-1` identifiers.

The endpoint adds 6,977 bytes text, 40 bytes initialized data, and 768 bytes
BSS (7,785 bytes total) to this host SITL build compared with the feature-off
multi-instance build. The feature-off image is 560 text bytes above the earlier
upstream baseline because generic multi-instance SITL arguments and port
offsetting remain available without AEROLINK. Hardware flash, RAM, and real
flight-loop impact are not measurable or claimed without a selected target.

## Fault and conformance evidence

Passed in real SITL: TCP partial-frame delivery with deterministic 1/4/2/3 ms
jitter, corrupt CRC rejection and resynchronization, UART disconnect/reconnect,
Pi restart with a new session, SITL restart with a new session, stale-session
rejection, central HTTP server loss/restart with retained deterministic state,
simultaneous selected-node failures, and an unselected-node failure in the
15-node run. Each endpoint used only its matching deterministic TCP port.

The Fake FC/server suites additionally cover bad magic, unsupported version and
type, wrong vehicle, bad length, duplicate/reordered/stale packets, bounds,
manual priority, invalid AI recommendations, server-command authentication,
and insufficient healthy vehicles. AI remains deterministic and advisory and
has no arming, setpoint, motor, or payload method.

## Defects found and limitations

Real integration found and fixed a missing target-feature include and a
freshness bug where small future clock skew underflowed to a very old unsigned
age. The wire protocol and golden vectors were not changed.

The isolated LAN is represented by authenticated unicast loopback TCP, not a
network namespace or RF WLAN model. Latency/jitter are deterministic UART/TCP
chunk delays; broad stochastic LAN loss/reordering remains covered only by the
Fake FC/server model. HTTP server restart is an in-process service restart,
while every Pi and Betaflight SITL endpoint is a separate OS process. Host
measurements vary with load and are not real-time guarantees.

## Remaining TBDs and next gate

All physical target, UART pins, voltage, baud, power, sensors, payload GPIO,
propulsion, and localization hardware remain `TBD` in the hardware matrix.

Stop here. The next simulation-only gate is a separately reviewed, bounded
adapter into an existing Betaflight stabilized-control interface with direct
before/after attitude, throttle, mixer, motor, arming, and payload invariance
instrumentation. That work is unimplemented. It requires qualified
adult-supervised review before any physical testing; this report authorizes no
flash, motor power, payload energization, or flight.
