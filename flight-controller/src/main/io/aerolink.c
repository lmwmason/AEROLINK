/* GPL-3.0-or-later; see aerolink.h and the Betaflight LICENSE. */
#ifndef AEROLINK_NATIVE_TEST
#include "platform.h"
#endif
#include "io/aerolink.h"

#include <string.h>

#ifdef USE_AEROLINK

static uint16_t u16(const uint8_t *p) { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }
static int16_t i16(const uint8_t *p) { return (int16_t)u16(p); }
static uint32_t u32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static uint64_t u64(const uint8_t *p) { return (uint64_t)u32(p) | ((uint64_t)u32(p + 4) << 32); }
static void w16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static void w32(uint8_t *p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }

static uint32_t crc32(const uint8_t *data, size_t length)
{
    uint32_t crc = 0xffffffffU;
    while (length--) {
        crc ^= *data++;
        for (unsigned bit = 0; bit < 8; bit++)
            crc = (crc >> 1) ^ (0xedb88320U & (uint32_t)-(int32_t)(crc & 1U));
    }
    return crc ^ 0xffffffffU;
}

static bool knownType(uint8_t type)
{
    switch (type) {
    case AEROLINK_MSG_HELLO: case AEROLINK_MSG_CAPABILITIES:
    case AEROLINK_MSG_HEARTBEAT: case AEROLINK_MSG_SET_MODE:
    case AEROLINK_MSG_SET_STABILIZED_SETPOINT: case AEROLINK_MSG_SET_PAYLOAD_STATE:
    case AEROLINK_MSG_NODE_STATUS: case AEROLINK_MSG_HEALTH:
    case AEROLINK_MSG_ACK: case AEROLINK_MSG_FAULT: return true;
    default: return false;
    }
}

void aerolinkConfigReset(aerolinkConfig_t *config)
{
    config->enabled = false;
    config->vehicleId = 0;
    config->heartbeatTimeoutMs = 300;
    config->setpointTimeoutMs = 100;
}

void aerolinkEndpointInit(aerolinkEndpoint_t *endpoint, const aerolinkConfig_t *config)
{
    memset(endpoint, 0, sizeof(*endpoint));
    endpoint->config = *config;
    endpoint->state = AEROLINK_DISABLED;
    endpoint->lastReject = AEROLINK_OK;
}

aerolinkReject_e aerolinkDecode(const uint8_t *b, size_t length, uint8_t vehicleId, aerolinkFrameView_t *frame)
{
    if (length < AEROLINK_HEADER_SIZE + AEROLINK_CRC_SIZE) return AEROLINK_BAD_LENGTH;
    if (b[0] != 'A' || b[1] != 'L') return AEROLINK_BAD_MAGIC;
    if (b[2] != AEROLINK_VERSION) return AEROLINK_UNSUPPORTED_VERSION;
    const uint16_t payloadLength = u16(b + 4);
    if (payloadLength > AEROLINK_MAX_PAYLOAD || length != AEROLINK_HEADER_SIZE + payloadLength + AEROLINK_CRC_SIZE) return AEROLINK_BAD_LENGTH;
    if (u32(b + AEROLINK_HEADER_SIZE + payloadLength) != crc32(b, AEROLINK_HEADER_SIZE + payloadLength)) return AEROLINK_BAD_CRC;
    if (!knownType(b[3])) return AEROLINK_UNSUPPORTED_TYPE;
    if (vehicleId && b[6] != vehicleId) return AEROLINK_VEHICLE_MISMATCH;
    frame->type = b[3]; frame->vehicleId = b[6]; frame->formationId = u16(b + 7);
    frame->sequence = u32(b + 9); frame->uptimeMs = u32(b + 13);
    frame->payload = b + AEROLINK_HEADER_SIZE; frame->payloadLength = payloadLength;
    return AEROLINK_OK;
}

static unsigned sequenceSlot(uint8_t type)
{
    switch (type) { case AEROLINK_MSG_HEARTBEAT: return 0; case AEROLINK_MSG_SET_MODE: return 1; case AEROLINK_MSG_SET_STABILIZED_SETPOINT: return 2; default: return 3; }
}

static aerolinkReject_e sequenceValidate(const aerolinkEndpoint_t *ep, const aerolinkFrameView_t *f)
{
    unsigned slot = sequenceSlot(f->type);
    if (ep->sequenceSeen[slot]) {
        uint32_t delta = f->sequence - ep->lastSequence[slot];
        if (!delta) return AEROLINK_DUPLICATE;
        if (delta > 0x7fffffffU) return AEROLINK_REORDERED;
    }
    return AEROLINK_OK;
}

static void sequenceCommit(aerolinkEndpoint_t *ep, const aerolinkFrameView_t *f)
{
    const unsigned slot = sequenceSlot(f->type);
    ep->lastSequence[slot] = f->sequence; ep->sequenceSeen[slot] = true;
}

static bool transitionAllowed(aerolinkState_e from, aerolinkState_e to)
{
    if (to == AEROLINK_DISABLED || to == AEROLINK_ABORTING || to == AEROLINK_FAULT) return true;
    if (from == AEROLINK_DISABLED) return to == AEROLINK_STANDBY;
    if (from == AEROLINK_STANDBY) return to == AEROLINK_READY;
    if (from == AEROLINK_READY) return to == AEROLINK_STANDBY || to == AEROLINK_ACTIVE;
    if (from == AEROLINK_ACTIVE) return to == AEROLINK_READY || to == AEROLINK_DEGRADED;
    if (from == AEROLINK_DEGRADED) return to == AEROLINK_ABORTING || to == AEROLINK_READY;
    if (from == AEROLINK_ABORTING) return to == AEROLINK_STANDBY;
    return false;
}

static aerolinkReject_e reject(aerolinkEndpoint_t *ep, aerolinkReject_e reason)
{
    ep->lastReject = reason; ep->rejectionCount++; return reason;
}

aerolinkReject_e aerolinkEndpointAccept(aerolinkEndpoint_t *ep, const uint8_t *bytes, size_t length, uint32_t nowMs, bool disarmed, bool rc, bool safety)
{
    if (!ep->config.enabled) return reject(ep, AEROLINK_FEATURE_DISABLED);
    if (ep->config.vehicleId < 1 || ep->config.vehicleId > 15) return reject(ep, AEROLINK_OUT_OF_RANGE);
    aerolinkFrameView_t f;
    aerolinkReject_e result = aerolinkDecode(bytes, length, ep->config.vehicleId, &f);
    if (result) return reject(ep, result);
    if (f.type == AEROLINK_MSG_HELLO) {
        if (f.payloadLength != 11 || f.payload[0] != 1 || f.payload[1] > 1 || f.payload[2] < 1 || !u64(f.payload + 3)) return reject(ep, AEROLINK_OUT_OF_RANGE);
        if (ep->sessionBound && ep->peerSession == u64(f.payload + 3)) return reject(ep, AEROLINK_DUPLICATE);
        ep->peerSession = u64(f.payload + 3); ep->sessionBound = true;
        memset(ep->sequenceSeen, 0, sizeof(ep->sequenceSeen));
        ep->peerClockOffsetMs = nowMs - f.uptimeMs; ep->peerClockKnown = true;
        if (ep->state != AEROLINK_STANDBY) { ep->state = AEROLINK_STANDBY; ep->transitionCount++; }
        ep->lastReject = AEROLINK_OK; return AEROLINK_OK;
    }
    if (!ep->sessionBound) return reject(ep, AEROLINK_SESSION_MISMATCH);
    if (disarmed) { ep->state = AEROLINK_DISABLED; return reject(ep, AEROLINK_MANUAL_OVERRIDE); }
    if (rc) { if (ep->state == AEROLINK_ACTIVE) ep->state = AEROLINK_READY; return reject(ep, AEROLINK_MANUAL_OVERRIDE); }
    if (safety) { ep->state = AEROLINK_FAULT; return reject(ep, AEROLINK_SAFETY_LOCKOUT); }
    if (f.payloadLength < 11 || u64(f.payload) != ep->peerSession) return reject(ep, AEROLINK_SESSION_MISMATCH);
    const uint16_t ttl = u16(f.payload + f.payloadLength - 2);
    const int32_t age = (int32_t)(nowMs - (f.uptimeMs + ep->peerClockOffsetMs));
    if (!ttl || age > (int32_t)ttl || age < -(int32_t)ttl) return reject(ep, AEROLINK_STALE);
    result = sequenceValidate(ep, &f); if (result) return reject(ep, result);
    if (f.type == AEROLINK_MSG_HEARTBEAT) {
        if (f.payloadLength != 11 || ttl > 300) return reject(ep, AEROLINK_OUT_OF_RANGE);
        ep->lastHeartbeatAtMs = nowMs;
    } else if (f.type == AEROLINK_MSG_SET_MODE) {
        if (f.payloadLength != 11 || ttl > 500 || f.payload[8] > AEROLINK_FAULT) return reject(ep, AEROLINK_OUT_OF_RANGE);
        aerolinkState_e requested = (aerolinkState_e)f.payload[8];
        if (!transitionAllowed(ep->state, requested)) return reject(ep, AEROLINK_INVALID_STATE);
        if (requested != ep->state) { ep->state = requested; ep->transitionCount++; }
    } else if (f.type == AEROLINK_MSG_SET_STABILIZED_SETPOINT) {
        if (f.payloadLength != 18 || ttl > 100 || i16(f.payload + 8) < -3000 || i16(f.payload + 8) > 3000 || i16(f.payload + 10) < -3000 || i16(f.payload + 10) > 3000 || i16(f.payload + 12) < -18000 || i16(f.payload + 12) > 18000 || i16(f.payload + 14) < -300 || i16(f.payload + 14) > 300) return reject(ep, AEROLINK_OUT_OF_RANGE);
        if (ep->state != AEROLINK_ACTIVE) return reject(ep, AEROLINK_INVALID_STATE);
        ep->lastSetpointAtMs = nowMs; /* Stored reference is intentionally not wired to motors here. */
    } else if (f.type == AEROLINK_MSG_SET_PAYLOAD_STATE) {
        return reject(ep, AEROLINK_FEATURE_DISABLED); /* No GPIO implementation. */
    } else return reject(ep, AEROLINK_UNSUPPORTED_TYPE);
    sequenceCommit(ep, &f);
    ep->lastReject = AEROLINK_OK; return AEROLINK_OK;
}

void aerolinkEndpointUpdate(aerolinkEndpoint_t *ep, uint32_t nowMs, bool disarmed, bool rc, bool safety)
{
    if (!ep->config.enabled || disarmed) { if (ep->state != AEROLINK_DISABLED) ep->transitionCount++; ep->state = AEROLINK_DISABLED; return; }
    if (safety) { if (ep->state != AEROLINK_FAULT) ep->transitionCount++; ep->state = AEROLINK_FAULT; return; }
    if (rc && ep->state == AEROLINK_ACTIVE) { ep->state = AEROLINK_READY; ep->transitionCount++; return; }
    if ((ep->state == AEROLINK_READY || ep->state == AEROLINK_ACTIVE) && nowMs - ep->lastHeartbeatAtMs > ep->config.heartbeatTimeoutMs) { ep->state = AEROLINK_ABORTING; ep->transitionCount++; }
    else if (ep->state == AEROLINK_ACTIVE && nowMs - ep->lastSetpointAtMs > ep->config.setpointTimeoutMs) { ep->state = AEROLINK_DEGRADED; ep->transitionCount++; }
}

static bool buildFrame(uint8_t *out, size_t cap, size_t *length, uint8_t type, uint8_t vehicleId, uint32_t sequence, uint32_t uptime, const uint8_t *payload, uint16_t payloadLength)
{
    const size_t n = AEROLINK_HEADER_SIZE + payloadLength + AEROLINK_CRC_SIZE;
    if (cap < n || vehicleId < 1 || vehicleId > 15) return false;
    out[0]='A'; out[1]='L'; out[2]=1; out[3]=type; w16(out+4,payloadLength); out[6]=vehicleId; w16(out+7,0); w32(out+9,sequence); w32(out+13,uptime);
    memcpy(out+17,payload,payloadLength);w32(out+17+payloadLength,crc32(out,17+payloadLength));*length=n;return true;
}
bool aerolinkBuildAck(uint8_t *o,size_t c,size_t *n,uint8_t v,uint32_t q,uint32_t t,uint8_t a,uint32_t z,aerolinkReject_e r){uint8_t p[6];p[0]=a;w32(p+1,z);p[5]=r;return buildFrame(o,c,n,AEROLINK_MSG_ACK,v,q,t,p,sizeof(p));}
bool aerolinkBuildHello(uint8_t *o,size_t c,size_t*n,uint8_t v,uint32_t q,uint32_t t,uint64_t s){uint8_t p[11]={2,1,1};w32(p+3,(uint32_t)s);w32(p+7,(uint32_t)(s>>32));return s&&buildFrame(o,c,n,AEROLINK_MSG_HELLO,v,q,t,p,sizeof(p));}
bool aerolinkBuildCapabilities(uint8_t *o,size_t c,size_t*n,uint8_t v,uint32_t q,uint32_t t){uint8_t p[7]={1,0,0,0,0,2,0};/* v1; 512-byte parser; no payload GPIO */return buildFrame(o,c,n,AEROLINK_MSG_CAPABILITIES,v,q,t,p,sizeof(p));}
bool aerolinkBuildNodeStatus(uint8_t*o,size_t c,size_t*n,uint8_t v,uint32_t q,uint32_t t,const aerolinkEndpoint_t*e){uint8_t p[6];p[0]=e->state;p[1]=e->lastReject;w32(p+2,e->transitionCount);return buildFrame(o,c,n,AEROLINK_MSG_NODE_STATUS,v,q,t,p,sizeof(p));}
bool aerolinkBuildHealth(uint8_t*o,size_t c,size_t*n,uint8_t v,uint32_t q,uint32_t t,bool eh,bool ch,uint16_t mv){uint8_t p[4]={eh,ch,0,0};w16(p+2,mv);return buildFrame(o,c,n,AEROLINK_MSG_HEALTH,v,q,t,p,sizeof(p));}
bool aerolinkBuildFault(uint8_t*o,size_t c,size_t*n,uint8_t v,uint32_t q,uint32_t t,uint16_t f,aerolinkReject_e r){uint8_t p[3];w16(p,f);p[2]=r;return buildFrame(o,c,n,AEROLINK_MSG_FAULT,v,q,t,p,sizeof(p));
}

#else
void aerolinkConfigReset(aerolinkConfig_t *c) { memset(c, 0, sizeof(*c)); }
void aerolinkEndpointInit(aerolinkEndpoint_t *e, const aerolinkConfig_t *c) { memset(e, 0, sizeof(*e)); e->config = *c; }
aerolinkReject_e aerolinkDecode(const uint8_t *b, size_t n, uint8_t v, aerolinkFrameView_t *f) { (void)b;(void)n;(void)v;(void)f; return AEROLINK_FEATURE_DISABLED; }
aerolinkReject_e aerolinkEndpointAccept(aerolinkEndpoint_t *e,const uint8_t*b,size_t n,uint32_t t,bool d,bool r,bool s){(void)e;(void)b;(void)n;(void)t;(void)d;(void)r;(void)s;return AEROLINK_FEATURE_DISABLED;}
void aerolinkEndpointUpdate(aerolinkEndpoint_t *e,uint32_t t,bool d,bool r,bool s){(void)e;(void)t;(void)d;(void)r;(void)s;}
bool aerolinkBuildAck(uint8_t*o,size_t c,size_t*l,uint8_t v,uint32_t q,uint32_t t,uint8_t a,uint32_t z,aerolinkReject_e r){(void)o;(void)c;(void)l;(void)v;(void)q;(void)t;(void)a;(void)z;(void)r;return false;}
bool aerolinkBuildCapabilities(uint8_t*o,size_t c,size_t*l,uint8_t v,uint32_t q,uint32_t t){(void)o;(void)c;(void)l;(void)v;(void)q;(void)t;return false;}
bool aerolinkBuildHello(uint8_t*o,size_t c,size_t*l,uint8_t v,uint32_t q,uint32_t t,uint64_t s){(void)o;(void)c;(void)l;(void)v;(void)q;(void)t;(void)s;return false;}
bool aerolinkBuildNodeStatus(uint8_t*o,size_t c,size_t*l,uint8_t v,uint32_t q,uint32_t t,const aerolinkEndpoint_t*e){(void)o;(void)c;(void)l;(void)v;(void)q;(void)t;(void)e;return false;}
bool aerolinkBuildHealth(uint8_t*o,size_t c,size_t*l,uint8_t v,uint32_t q,uint32_t t,bool e,bool h,uint16_t m){(void)o;(void)c;(void)l;(void)v;(void)q;(void)t;(void)e;(void)h;(void)m;return false;}
bool aerolinkBuildFault(uint8_t*o,size_t c,size_t*l,uint8_t v,uint32_t q,uint32_t t,uint16_t f,aerolinkReject_e r){(void)o;(void)c;(void)l;(void)v;(void)q;(void)t;(void)f;(void)r;return false;}
#endif
