# Drone electromagnet controller

Arduino Mega controller that toggles an electromagnet on each confirmed descent
below a configured pickup height. The state is retained during ascent. After the
drone climbs above the re-arm height, the next descent toggles it again. An LED is
on while the drone is in the near-ground state.

## Wiring

| Device | Mega pin | Notes |
|---|---:|---|
| Analog IR sensor output | A0 | Sensor and Arduino must share GND |
| Relay control input | D7 | Active-low by default |
| Altitude-state LED | D13 | ON means near ground |

Do not power the electromagnet from an Arduino pin. Use a rated external supply,
relay/driver, fuse, and a flyback diode across a DC electromagnet.

## Configuration

Edit `include/AppConfig.h`: pickup/re-arm heights, pin numbers, relay polarity,
timing, and the sensor calibration curve are all kept there. The supplied curve
is only a starting point for a Sharp GP2Y0A21YK0F-style sensor. Calibrate the
actual sensor at known distances before flight.

The default pickup threshold is 15 cm. The controller must rise above the 18 cm
re-arm threshold before another descent can toggle the electromagnet.

```sh
pio run
pio run --target upload
```
