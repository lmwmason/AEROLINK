#include <Arduino.h>
#include "Actuators.h"
#include "AppConfig.h"
#include "DistanceSensor.h"
#include "PickupController.h"

DistanceSensor distanceSensor(config::kDistanceSensorPin);
PickupController pickupController;
Actuators actuators(config::kRelayPin, config::kAltitudeLedPin);
uint32_t lastSampleMs = 0;

void setup() {
  actuators.begin();
  distanceSensor.begin();
}

void loop() {
  const uint32_t nowMs = millis();
  if (nowMs - lastSampleMs < config::kSamplePeriodMs) return;
  lastSampleMs = nowMs;

  const DistanceReading reading = distanceSensor.read();
  const ControllerUpdate update =
      pickupController.update(reading.centimeters, reading.valid, nowMs);
  actuators.setNearGroundIndicator(update.nearGround);
  if (update.magnetChanged) actuators.setMagnet(update.magnetOn);
}
