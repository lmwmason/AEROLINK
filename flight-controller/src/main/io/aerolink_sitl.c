/* SITL-only, non-actuating AEROLINK serial transport. GPL-3.0-or-later. */
#include "platform.h"
#if defined(USE_AEROLINK) && ENABLE_SIMULATOR

#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "common/time.h"
#include "drivers/serial.h"
#include "drivers/time.h"
#include "io/aerolink.h"
#include "io/aerolink_sitl.h"
#include "io/serial.h"

#define RX_BUDGET_PER_RUN 256U
#define TELEMETRY_BUDGET_PER_RUN 16U

extern unsigned targetGetAerolinkVehicleId(void);

static serialPort_t *port;
static aerolinkEndpoint_t endpoint;
static uint8_t rx[AEROLINK_MAX_FRAME_SIZE];
static size_t rxLength;
static uint64_t fcSession;
static uint32_t txSequence;
static uint32_t accepted, rejected, dropped, maxBacklog, maxTaskUs;
static uint32_t lastMetricsMs;

static uint16_t readU16(const uint8_t *p) { return p[0] | (uint16_t)p[1] << 8; }
static void send(const uint8_t *data, size_t length) { if (port && length <= UINT16_MAX) serialWriteBuf(port, data, (int)length); }
static void sendAck(uint8_t type, uint32_t sequence, aerolinkReject_e result, uint32_t now)
{
    uint8_t out[64]; size_t length;
    if (aerolinkBuildAck(out,sizeof(out),&length,endpoint.config.vehicleId,++txSequence,now,type,sequence,result)) send(out,length);
}
static void sendStatus(uint32_t now)
{
    uint8_t out[64]; size_t length;
    if (aerolinkBuildNodeStatus(out,sizeof(out),&length,endpoint.config.vehicleId,++txSequence,now,&endpoint)) send(out,length);
    if (aerolinkBuildHealth(out,sizeof(out),&length,endpoint.config.vehicleId,++txSequence,now,true,true,0)) send(out,length);
}
static void consume(size_t count) { rxLength -= count; memmove(rx,rx+count,rxLength); }

static unsigned processFrames(uint32_t now)
{
    unsigned telemetry = 0;
    while (rxLength >= AEROLINK_HEADER_SIZE + AEROLINK_CRC_SIZE && telemetry < TELEMETRY_BUDGET_PER_RUN) {
        if (rx[0] != 'A' || rx[1] != 'L') { consume(1); dropped++; continue; }
        const uint16_t payloadLength=readU16(rx+4);
        if (payloadLength>AEROLINK_MAX_PAYLOAD) { sendAck(rx[3],0,AEROLINK_BAD_LENGTH,now);consume(1);rejected++;telemetry++;continue; }
        const size_t frameLength=AEROLINK_HEADER_SIZE+payloadLength+AEROLINK_CRC_SIZE;
        if (rxLength<frameLength) break;
        aerolinkFrameView_t view; const aerolinkReject_e decoded=aerolinkDecode(rx,frameLength,endpoint.config.vehicleId,&view);
        const uint8_t type=rx[3];const uint32_t sequence=decoded==AEROLINK_OK?view.sequence:0;
        const aerolinkReject_e result=aerolinkEndpointAccept(&endpoint,rx,frameLength,now,false,false,false);
        if (result==AEROLINK_OK) accepted++; else rejected++;
        sendAck(type,sequence,result,now);telemetry++;
        if (result==AEROLINK_OK && type==AEROLINK_MSG_HELLO && telemetry+2<=TELEMETRY_BUDGET_PER_RUN) {
            uint8_t out[64];size_t n;
            if (aerolinkBuildHello(out,sizeof(out),&n,endpoint.config.vehicleId,++txSequence,now,fcSession)) send(out,n);
            if (aerolinkBuildCapabilities(out,sizeof(out),&n,endpoint.config.vehicleId,++txSequence,now)) send(out,n);
            telemetry+=2;
        } else if (type==AEROLINK_MSG_HEARTBEAT && telemetry+2<=TELEMETRY_BUDGET_PER_RUN) { sendStatus(now); telemetry+=2; }
        consume(frameLength);
    }
    return telemetry;
}

void aerolinkSitlInit(void)
{
    aerolinkConfig_t config;aerolinkConfigReset(&config);
    const unsigned vehicle=targetGetAerolinkVehicleId();
    if (!vehicle) { aerolinkEndpointInit(&endpoint,&config); return; }
    config.enabled=true;config.vehicleId=(uint8_t)vehicle;aerolinkEndpointInit(&endpoint,&config);
    fcSession=((uint64_t)(unsigned)getpid()<<32)^micros64_real()^0xa34e4f4c494e4bULL;
    if (!fcSession) fcSession=1;
    port=openSerialPort(AEROLINK_UART,FUNCTION_AEROLINK,NULL,NULL,115200,MODE_RXTX,SERIAL_NOT_INVERTED);
    if (!port) { fprintf(stderr,"[AEROLINK] failed to open SITL UART\n"); config.enabled=false;endpoint.config=config;return; }
    fprintf(stderr,"[AEROLINK] ready vehicle=%u tcp_uart=8 session=%llu\n",vehicle,(unsigned long long)fcSession);
}

void aerolinkSitlTask(timeUs_t currentTimeUs)
{
    if (!port) return;
    const uint32_t started=micros();const uint32_t now=millis();unsigned budget=RX_BUDGET_PER_RUN;
    while (budget-- && serialRxBytesWaiting(port)) {
        if (rxLength<sizeof(rx)) rx[rxLength++]=serialRead(port); else { consume(1);rx[rxLength++]=serialRead(port);dropped++; }
    }
    if (rxLength>maxBacklog) maxBacklog=(uint32_t)rxLength;
    aerolinkEndpointUpdate(&endpoint,now,false,false,false);
    processFrames(now);
    const uint32_t elapsed=micros()-started;if(elapsed>maxTaskUs)maxTaskUs=elapsed;
    if (now-lastMetricsMs>=1000) { lastMetricsMs=now;fprintf(stderr,"[AEROLINK_METRICS] vehicle=%u accepted=%u rejected=%u last_reject=%u dropped=%u backlog=%u max_task_us=%u state=%u control_path_connected=0\n",endpoint.config.vehicleId,accepted,rejected,endpoint.lastReject,dropped,maxBacklog,maxTaskUs,endpoint.state); }
    (void)currentTimeUs;
}
#endif
