/*
 * This file is part of Betaflight.
 *
 * Betaflight is free software: you can redistribute it and/or modify it under
 * the terms of the GNU General Public License as published by the Free Software
 * Foundation, either version 3 of the License, or (at your option) any later
 * version.
 */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define AEROLINK_VERSION 1U
#define AEROLINK_MAX_PAYLOAD 512U
#define AEROLINK_HEADER_SIZE 17U
#define AEROLINK_CRC_SIZE 4U
#define AEROLINK_MAX_FRAME_SIZE (AEROLINK_HEADER_SIZE + AEROLINK_MAX_PAYLOAD + AEROLINK_CRC_SIZE)

typedef enum {
    AEROLINK_MSG_HELLO = 0x01,
    AEROLINK_MSG_CAPABILITIES = 0x02,
    AEROLINK_MSG_HEARTBEAT = 0x03,
    AEROLINK_MSG_SET_MODE = 0x10,
    AEROLINK_MSG_SET_STABILIZED_SETPOINT = 0x11,
    AEROLINK_MSG_SET_PAYLOAD_STATE = 0x12,
    AEROLINK_MSG_NODE_STATUS = 0x20,
    AEROLINK_MSG_HEALTH = 0x21,
    AEROLINK_MSG_ACK = 0x22,
    AEROLINK_MSG_FAULT = 0x23,
} aerolinkMessageType_e;

typedef enum {
    AEROLINK_OK = 0, AEROLINK_BAD_MAGIC = 1, AEROLINK_UNSUPPORTED_VERSION = 2,
    AEROLINK_UNSUPPORTED_TYPE = 3, AEROLINK_BAD_LENGTH = 4,
    AEROLINK_BAD_CRC = 5, AEROLINK_VEHICLE_MISMATCH = 6,
    AEROLINK_SESSION_MISMATCH = 7, AEROLINK_DUPLICATE = 8,
    AEROLINK_REORDERED = 9, AEROLINK_STALE = 10,
    AEROLINK_OUT_OF_RANGE = 11, AEROLINK_INVALID_STATE = 12,
    AEROLINK_MANUAL_OVERRIDE = 13, AEROLINK_SAFETY_LOCKOUT = 14,
    AEROLINK_FEATURE_DISABLED = 15,
} aerolinkReject_e;

typedef enum {
    AEROLINK_DISABLED = 0, AEROLINK_STANDBY = 1, AEROLINK_READY = 2,
    AEROLINK_ACTIVE = 3, AEROLINK_DEGRADED = 4, AEROLINK_ABORTING = 5,
    AEROLINK_FAULT = 6,
} aerolinkState_e;

typedef struct {
    bool enabled;                 /* Runtime gate: reset/default must be false. */
    uint8_t vehicleId;            /* 1..15 when enabled. */
    uint16_t heartbeatTimeoutMs;  /* <= 300. */
    uint16_t setpointTimeoutMs;   /* <= 100. */
} aerolinkConfig_t;

typedef struct {
    aerolinkConfig_t config;
    aerolinkState_e state;
    uint64_t peerSession;
    bool sessionBound;
    uint32_t lastSequence[4];
    bool sequenceSeen[4];
    uint32_t lastHeartbeatAtMs;
    uint32_t lastSetpointAtMs;
    uint32_t peerClockOffsetMs;
    bool peerClockKnown;
    aerolinkReject_e lastReject;
    uint32_t transitionCount;
    uint32_t rejectionCount;
} aerolinkEndpoint_t;

typedef struct {
    uint8_t type;
    uint8_t vehicleId;
    uint16_t formationId;
    uint32_t sequence;
    uint32_t uptimeMs;
    const uint8_t *payload;
    uint16_t payloadLength;
} aerolinkFrameView_t;

void aerolinkConfigReset(aerolinkConfig_t *config);
void aerolinkEndpointInit(aerolinkEndpoint_t *endpoint, const aerolinkConfig_t *config);
aerolinkReject_e aerolinkDecode(const uint8_t *bytes, size_t length, uint8_t expectedVehicleId, aerolinkFrameView_t *frame);
aerolinkReject_e aerolinkEndpointAccept(aerolinkEndpoint_t *endpoint, const uint8_t *bytes, size_t length, uint32_t nowMs, bool manuallyDisarmed, bool rcTakeover, bool fcSafetyLockout);
void aerolinkEndpointUpdate(aerolinkEndpoint_t *endpoint, uint32_t nowMs, bool manuallyDisarmed, bool rcTakeover, bool fcSafetyLockout);
bool aerolinkBuildAck(uint8_t *output, size_t capacity, size_t *length, uint8_t vehicleId, uint32_t sequence, uint32_t uptimeMs, uint8_t ackedType, uint32_t ackedSequence, aerolinkReject_e result);
bool aerolinkBuildCapabilities(uint8_t *output, size_t capacity, size_t *length, uint8_t vehicleId, uint32_t sequence, uint32_t uptimeMs);
bool aerolinkBuildHello(uint8_t *output, size_t capacity, size_t *length, uint8_t vehicleId, uint32_t sequence, uint32_t uptimeMs, uint64_t sessionNonce);
bool aerolinkBuildNodeStatus(uint8_t *output, size_t capacity, size_t *length, uint8_t vehicleId, uint32_t sequence, uint32_t uptimeMs, const aerolinkEndpoint_t *endpoint);
bool aerolinkBuildHealth(uint8_t *output, size_t capacity, size_t *length, uint8_t vehicleId, uint32_t sequence, uint32_t uptimeMs, bool estimatorHealthy, bool controlHealthy, uint16_t batteryMv);
bool aerolinkBuildFault(uint8_t *output, size_t capacity, size_t *length, uint8_t vehicleId, uint32_t sequence, uint32_t uptimeMs, uint16_t faultCode, aerolinkReject_e reason);
