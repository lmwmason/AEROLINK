# Hardware matrix

No choice below is implied by the software scaffold. `TBD` items require
datasheet, schematic, and physical inspection evidence before configuration.

| Item | Required per system | Selected part / setting | Evidence | Gate |
|---|---:|---|---|---|
| Betaflight flight controller and target | 15 | TBD | None | Blocks flash |
| Raspberry Pi model and OS image | 15 | TBD | None | Blocks deployment |
| FC/Pi UART pins | 15 links | TBD | None | Blocks wiring |
| UART logic voltage and level shifting | 15 links | TBD | None | Blocks wiring |
| UART baud | 15 links | TBD | None | Blocks hardware config |
| Shared signal-ground arrangement | 15 | TBD | None | Blocks wiring |
| Pi and FC power architecture | 15 | TBD | None | Blocks power-up |
| RC receiver/manual cutoff | 15 | TBD | None | Blocks flight |
| IMU / FC sensors | 15 | TBD | None | Blocks target config |
| Indoor localization sensor | 15 | TBD | None | Simulator interface only |
| Obstacle sensor | 15 | TBD | None | Simulator interface only |
| LAN/WLAN AP and security profile | 1+ | TBD | None | Loopback simulation only |
| Motors, ESCs, props and guards | 15 sets | TBD | None | Blocks motor power |
| Battery and propulsion limits | 15 | TBD | None | Blocks motor power |
| Tension/load sensing | group-dependent | TBD | None | Simulator interface only |
| Electromagnet, driver and GPIO | group-dependent | TBD | None | Must remain off/absent |

Human confirmation is required before flashing, powering motors, energizing a
payload, or physical flight. Initial physical tests must be props-off and must
not occur in an occupied corridor.
