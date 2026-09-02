#pragma once
#include <Arduino.h>

class Actuators {
 public:
  Actuators(uint8_t relayPin, uint8_t ledPin);
  void begin();
  void setMagnet(bool on);
  void setNearGroundIndicator(bool nearGround);

 private:
  uint8_t relayPin_;
  uint8_t ledPin_;
};
