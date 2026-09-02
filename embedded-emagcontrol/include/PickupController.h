#pragma once
#include <Arduino.h>

struct ControllerUpdate {
  bool nearGround;
  bool magnetChanged;
  bool magnetOn;
};

// Toggles the magnet on confirmed descent below the pickup height, and stays
// armed until the drone rises above the (higher) re-arm height. The
// EnteringNear/EnteringFar states require the new reading to hold for
// kStableTimeMs before committing, so a single noisy sample near a threshold
// can't cause spurious relay chatter.
class PickupController {
 public:
  ControllerUpdate update(float distanceCm, bool readingValid, uint32_t nowMs);
  bool magnetOn() const { return magnetOn_; }
  bool nearGround() const { return state_ == AltitudeState::Near; }

 private:
  enum class AltitudeState : uint8_t { Far, EnteringNear, Near, EnteringFar };
  AltitudeState state_ = AltitudeState::Far;
  uint32_t transitionStartedMs_ = 0;
  bool magnetOn_ = false;
};
