#pragma once
#include <Arduino.h>

namespace config {

// --- Pins & polarity ---
constexpr uint8_t kDistanceSensorPin = A0;
constexpr uint8_t kRelayPin = 7;
constexpr uint8_t kAltitudeLedPin = 13;
constexpr bool kRelayActiveLow = true;
constexpr bool kLedActiveHigh = true;

// --- Pickup state machine ---
constexpr float kPickupHeightCm = 15.0F;
constexpr float kRearmHeightCm = 18.0F;
static_assert(kRearmHeightCm > kPickupHeightCm,
              "Rearm height must be above pickup height");
constexpr uint32_t kSamplePeriodMs = 20;   // how often the sensor is polled
constexpr uint32_t kStableTimeMs = 120;    // debounce time before a threshold crossing commits

// --- Sensor calibration ---
// distance(cm) = coefficient * voltage(V)^exponent
// Defaults target a Sharp GP2Y0A21YK0F-style analog sensor (roughly 10-80 cm).
// Re-derive coefficient/exponent from a fit against measured (voltage, distance)
// pairs when swapping sensors.
constexpr float kSensorCoefficient = 27.86F;
constexpr float kSensorExponent = -1.15F;
constexpr float kMinValidDistanceCm = 10.0F;
constexpr float kMaxValidDistanceCm = 80.0F;
constexpr float kAdcReferenceVoltage = 5.0F;
constexpr float kFilterAlpha = 0.25F;  // EMA smoothing factor, 0 (slow) - 1 (no smoothing)

}  // namespace config
