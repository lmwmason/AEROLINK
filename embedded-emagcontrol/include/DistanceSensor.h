#pragma once
#include <Arduino.h>

struct DistanceReading {
  float centimeters;
  bool valid;
};

class DistanceSensor {
 public:
  explicit DistanceSensor(uint8_t analogPin);
  void begin();
  DistanceReading read();

 private:
  uint8_t analogPin_;
  float filteredVoltage_ = 0.0F;
  bool filterInitialized_ = false;
};
