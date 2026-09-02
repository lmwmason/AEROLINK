#include "Actuators.h"
#include "AppConfig.h"

namespace {
uint8_t outputLevel(bool on, bool activeHigh) {
  return on == activeHigh ? HIGH : LOW;
}
}  // namespace

Actuators::Actuators(uint8_t relayPin, uint8_t ledPin)
    : relayPin_(relayPin), ledPin_(ledPin) {}

void Actuators::begin() {
  digitalWrite(relayPin_, outputLevel(false, !config::kRelayActiveLow));
  digitalWrite(ledPin_, outputLevel(false, config::kLedActiveHigh));
  pinMode(relayPin_, OUTPUT);
  pinMode(ledPin_, OUTPUT);
}
void Actuators::setMagnet(bool on) {
  digitalWrite(relayPin_, outputLevel(on, !config::kRelayActiveLow));
}
void Actuators::setNearGroundIndicator(bool nearGround) {
  digitalWrite(ledPin_, outputLevel(nearGround, config::kLedActiveHigh));
}
