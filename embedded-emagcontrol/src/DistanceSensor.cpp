#include "DistanceSensor.h"
#include <math.h>
#include "AppConfig.h"

DistanceSensor::DistanceSensor(uint8_t analogPin) : analogPin_(analogPin) {}
void DistanceSensor::begin() { pinMode(analogPin_, INPUT); }

DistanceReading DistanceSensor::read() {
  const int raw = analogRead(analogPin_);
  if (raw <= 0 || raw >= 1023) return {0.0F, false};

  const float voltage = raw * (config::kAdcReferenceVoltage / 1023.0F);
  if (!filterInitialized_) {
    filteredVoltage_ = voltage;
    filterInitialized_ = true;
  } else {
    filteredVoltage_ += config::kFilterAlpha * (voltage - filteredVoltage_);
  }

  const float distance =
      config::kSensorCoefficient * powf(filteredVoltage_, config::kSensorExponent);
  const bool valid = isfinite(distance) &&
                     distance >= config::kMinValidDistanceCm &&
                     distance <= config::kMaxValidDistanceCm;
  return {distance, valid};
}
