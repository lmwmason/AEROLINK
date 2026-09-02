#include "PickupController.h"
#include "AppConfig.h"

ControllerUpdate PickupController::update(float distanceCm, bool readingValid,
                                           uint32_t nowMs) {
  bool magnetChanged = false;
  if (!readingValid) return {nearGround(), false, magnetOn_};

  switch (state_) {
    case AltitudeState::Far:
      if (distanceCm <= config::kPickupHeightCm) {
        state_ = AltitudeState::EnteringNear;
        transitionStartedMs_ = nowMs;
      }
      break;
    case AltitudeState::EnteringNear:
      if (distanceCm > config::kPickupHeightCm) {
        state_ = AltitudeState::Far;
      } else if (nowMs - transitionStartedMs_ >= config::kStableTimeMs) {
        state_ = AltitudeState::Near;
        magnetOn_ = !magnetOn_;
        magnetChanged = true;
      }
      break;
    case AltitudeState::Near:
      if (distanceCm >= config::kRearmHeightCm) {
        state_ = AltitudeState::EnteringFar;
        transitionStartedMs_ = nowMs;
      }
      break;
    case AltitudeState::EnteringFar:
      if (distanceCm < config::kRearmHeightCm) {
        state_ = AltitudeState::Near;
      } else if (nowMs - transitionStartedMs_ >= config::kStableTimeMs) {
        state_ = AltitudeState::Far;
      }
      break;
  }
  return {nearGround(), magnetChanged, magnetOn_};
}
