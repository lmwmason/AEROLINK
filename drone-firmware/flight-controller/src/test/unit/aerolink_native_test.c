#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "io/aerolink.h"

static size_t unhex(const char *s, unsigned char *out) { size_t n=0; unsigned v; while (sscanf(s, "%2x", &v)==1) { out[n++]=(unsigned char)v; s+=2; } return n; }
static void w16(unsigned char *p, unsigned v) { p[0]=v; p[1]=v>>8; }
static void w32(unsigned char *p, unsigned v) { p[0]=v; p[1]=v>>8; p[2]=v>>16; p[3]=v>>24; }
static void w64(unsigned char *p, unsigned long long v) { w32(p,(unsigned)v); w32(p+4,(unsigned)(v>>32)); }
static unsigned crc32(const unsigned char *p,size_t n) { unsigned c=~0U; while(n--){c^=*p++;for(int i=0;i<8;i++)c=(c>>1)^(0xedb88320U&-(int)(c&1));}return ~c; }
static size_t build(unsigned char *b,unsigned type,unsigned seq,unsigned uptime,const unsigned char *p,unsigned pn) {
    b[0]='A';b[1]='L';b[2]=1;b[3]=type;w16(b+4,pn);b[6]=1;w16(b+7,0);w32(b+9,seq);w32(b+13,uptime);memcpy(b+17,p,pn);w32(b+17+pn,crc32(b,17+pn));return 21+pn;
}
static size_t command(unsigned char *b,unsigned type,unsigned seq,unsigned uptime,unsigned long long nonce,unsigned value,unsigned ttl) {
    unsigned char p[18]={0};w64(p,nonce);p[8]=value;w16(p+(type==AEROLINK_MSG_SET_STABILIZED_SETPOINT?16:9),ttl);return build(b,type,seq,uptime,p,type==AEROLINK_MSG_SET_STABILIZED_SETPOINT?18:11);
}

int main(int argc, char **argv)
{
    assert(argc == 2); FILE *fp=fopen(argv[1], "rb"); assert(fp); char json[16384]; size_t jn=fread(json,1,sizeof(json)-1,fp); fclose(fp); json[jn]=0;
    const char *hex=strstr(json, "414c01010b000100000403020140e201000101018877665544332211134541f3"); assert(hex);
    unsigned char frame[600]; size_t n=unhex(hex, frame); assert(n==32);
    aerolinkFrameView_t view; assert(aerolinkDecode(frame,n,1,&view)==AEROLINK_OK); assert(view.type==AEROLINK_MSG_HELLO); assert(view.sequence==0x01020304U);
    frame[n-1]^=1; assert(aerolinkDecode(frame,n,1,&view)==AEROLINK_BAD_CRC); frame[n-1]^=1;
    assert(aerolinkDecode(frame,n,2,&view)==AEROLINK_VEHICLE_MISMATCH);

    aerolinkConfig_t cfg; aerolinkConfigReset(&cfg); assert(!cfg.enabled);
    aerolinkEndpoint_t ep; aerolinkEndpointInit(&ep,&cfg); assert(aerolinkEndpointAccept(&ep,frame,n,123456,false,false,false)==AEROLINK_FEATURE_DISABLED);
    cfg.enabled=true; cfg.vehicleId=1; aerolinkEndpointInit(&ep,&cfg);
    assert(aerolinkEndpointAccept(&ep,frame,n,123456,false,false,false)==AEROLINK_OK); assert(ep.state==AEROLINK_STANDBY);
    assert(aerolinkEndpointAccept(&ep,frame,n,123456,false,false,false)==AEROLINK_DUPLICATE); /* Same nonce cannot reset replay state. */
    unsigned char cmd[80]; const unsigned long long nonce=0x1122334455667788ULL;
    size_t cn=command(cmd,AEROLINK_MSG_SET_MODE,1,123457,nonce,AEROLINK_READY,100);
    assert(aerolinkEndpointAccept(&ep,cmd,cn,123457,false,false,false)==AEROLINK_OK); assert(ep.state==AEROLINK_READY);
    cn=command(cmd,AEROLINK_MSG_HEARTBEAT,1,123458,nonce,AEROLINK_READY,300);
    assert(aerolinkEndpointAccept(&ep,cmd,cn,123458,false,false,false)==AEROLINK_OK);
    cn=command(cmd,AEROLINK_MSG_SET_MODE,2,123459,nonce,AEROLINK_ACTIVE,100);
    assert(aerolinkEndpointAccept(&ep,cmd,cn,123459,false,false,false)==AEROLINK_OK); assert(ep.state==AEROLINK_ACTIVE);
    cn=command(cmd,AEROLINK_MSG_SET_STABILIZED_SETPOINT,1,123460,nonce,0,100);
    assert(aerolinkEndpointAccept(&ep,cmd,cn,123460,false,false,false)==AEROLINK_OK);
    assert(aerolinkEndpointAccept(&ep,cmd,cn,123460,false,false,false)==AEROLINK_DUPLICATE);
    aerolinkEndpointUpdate(&ep,123561,false,false,false); assert(ep.state==AEROLINK_DEGRADED);
    cn=command(cmd,AEROLINK_MSG_SET_MODE,3,123562,nonce,AEROLINK_ABORTING,100);
    assert(aerolinkEndpointAccept(&ep,cmd,cn,123562,false,false,false)==AEROLINK_OK); assert(ep.state==AEROLINK_ABORTING);
    cn=command(cmd,AEROLINK_MSG_SET_MODE,4,123563,nonce,AEROLINK_STANDBY,100);
    assert(aerolinkEndpointAccept(&ep,cmd,cn,123563,false,false,false)==AEROLINK_OK); assert(ep.state==AEROLINK_STANDBY);
    aerolinkEndpointUpdate(&ep,123564,false,false,true); assert(ep.state==AEROLINK_FAULT);
    aerolinkEndpointUpdate(&ep,123565,true,false,false); assert(ep.state==AEROLINK_DISABLED);

    /* New boot nonce starts only in STANDBY and invalidates the old session. */
    unsigned char hp[11]={1,1,1}; w64(hp+3,0x99); n=build(frame,AEROLINK_MSG_HELLO,9,200000,hp,11);
    assert(aerolinkEndpointAccept(&ep,frame,n,200000,false,false,false)==AEROLINK_OK); assert(ep.state==AEROLINK_STANDBY);
    cn=command(cmd,AEROLINK_MSG_HEARTBEAT,5,200001,nonce,AEROLINK_STANDBY,300);
    assert(aerolinkEndpointAccept(&ep,cmd,cn,200001,false,false,false)==AEROLINK_SESSION_MISMATCH);

    /* RC takeover lowers ACTIVE to READY; it never raises authority. */
    cn=command(cmd,AEROLINK_MSG_SET_MODE,6,200002,0x99,AEROLINK_READY,100); assert(aerolinkEndpointAccept(&ep,cmd,cn,200002,false,false,false)==AEROLINK_OK);
    cn=command(cmd,AEROLINK_MSG_SET_MODE,7,200003,0x99,AEROLINK_ACTIVE,100); assert(aerolinkEndpointAccept(&ep,cmd,cn,200003,false,false,false)==AEROLINK_OK);
    aerolinkEndpointUpdate(&ep,200004,false,true,false); assert(ep.state==AEROLINK_READY);
    assert(ep.rejectionCount >= 3 && ep.transitionCount >= 8);
    size_t outn; assert(aerolinkBuildCapabilities(cmd,sizeof(cmd),&outn,1,10,200005));assert(aerolinkDecode(cmd,outn,1,&view)==AEROLINK_OK);assert(view.type==AEROLINK_MSG_CAPABILITIES);
    assert(aerolinkBuildNodeStatus(cmd,sizeof(cmd),&outn,1,11,200005,&ep));assert(aerolinkDecode(cmd,outn,1,&view)==AEROLINK_OK);
    assert(aerolinkBuildHealth(cmd,sizeof(cmd),&outn,1,12,200005,true,true,16000));assert(aerolinkDecode(cmd,outn,1,&view)==AEROLINK_OK);
    assert(aerolinkBuildFault(cmd,sizeof(cmd),&outn,1,13,200005,7,AEROLINK_STALE));assert(aerolinkDecode(cmd,outn,1,&view)==AEROLINK_OK);
    assert(aerolinkBuildAck(cmd,sizeof(cmd),&outn,1,14,200005,AEROLINK_MSG_HEARTBEAT,6,AEROLINK_OK));assert(aerolinkDecode(cmd,outn,1,&view)==AEROLINK_OK);
    puts("aerolink native tests: OK"); return 0;
}
