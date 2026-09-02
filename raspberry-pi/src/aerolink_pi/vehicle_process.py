"""Executable vehicle process used by real multiprocess SITL validation."""
from __future__ import annotations
import argparse,json,secrets,time,urllib.request
from pathlib import Path
from aerolink_server.security import node_headers,verify_server_response
from .protocol import MessageType,RejectCode,encode_heartbeat,encode_hello,encode_mode,encode_setpoint
from .sitl_client import SitlUartClient,ack_results

def post(url,path,node_id,key,data):
    body=json.dumps(data,separators=(",",":"),sort_keys=True).encode();headers={"Content-Type":"application/json",**node_headers(node_id,key,"POST",path,body)};request_nonce=headers["X-AEROLINK-Nonce"]
    req=urllib.request.Request(url+path,data=body,headers=headers)
    with urllib.request.urlopen(req,timeout=2) as response:
        response_body=response.read();verify_server_response(key,path,response_body,response.headers,request_nonce);return json.loads(response_body)

def main():
    p=argparse.ArgumentParser();p.add_argument("--vehicle",type=int,required=True);p.add_argument("--uart-port",type=int,required=True);p.add_argument("--server",required=True);p.add_argument("--node-key-hex",required=True);p.add_argument("--log",required=True);p.add_argument("--golden",action="store_true");a=p.parse_args();node_key=bytes.fromhex(a.node_key_hex)
    session=secrets.randbits(64) or 1;c=SitlUartClient(a.vehicle,a.uart_port,session);events=[]
    try:
        c.connect();events.append({"event":"connected","port":a.uart_port})
        if a.golden:
            vector_path=Path(__file__).resolve().parents[2]/"tests/vectors/uart_v1.json"
            vectors=json.loads(vector_path.read_text())
            hello=next(v for v in vectors["valid"] if v["name"]=="hello_pi_vehicle_1")
            c.send_raw(bytes.fromhex(hello["hex"]),(1,2,3,5),(1,4,2,3));golden=c.drain()
            golden_acks=ack_results(golden);golden_ok=RejectCode.OK.value in golden_acks
            events.append({"event":"golden_vector","name":hello["name"],"accepted":golden_ok,"acks":golden_acks,"types":[x.message_type.name for x in golden],"decoder_rejections":[x.code.name for x in c.decoder.rejections]})
            if not golden_ok:raise RuntimeError("golden HELLO vector rejected")
        c.send(MessageType.HELLO,encode_hello(1,session),(1,2,3,5));c.send(MessageType.HEARTBEAT,encode_heartbeat(session,2));c.send(MessageType.SET_MODE,encode_mode(session,2));c.send(MessageType.SET_MODE,encode_mode(session,3));c.send(MessageType.SET_STABILIZED_SETPOINT,encode_setpoint(session,0,0,0,0,100));initial=c.drain()
        initial_types={x.message_type for x in initial};initial_acks=ack_results(initial);events.append({"event":"handshake_heartbeat_setpoint","session":session,"types":sorted(x.name for x in initial_types),"acks":initial_acks})
        if not {MessageType.HELLO,MessageType.CAPABILITIES,MessageType.NODE_STATUS,MessageType.HEALTH}<=initial_types or initial_acks.count(RejectCode.OK.value)!=5:raise RuntimeError("initial transport exchange failed")
        post(a.server,"/api/register",a.vehicle,node_key,{"vehicle_id":a.vehicle,"session":session,"health":"online","packet_age_ms":0,"faults":[]})
        # Exercise guarded mode/setpoint parsing only. The FC transport has no control adapter.
        sp=initial;events.append({"event":"non_actuating_setpoint","acks":initial_acks})
        # Corrupt CRC and verify deterministic rejection.
        wire,_=c.send(MessageType.HEARTBEAT,encode_heartbeat(session,3));wire=bytearray(wire);wire[-1]^=1;c.sock.sendall(wire);bad=c.drain();bad_acks=ack_results(bad);events.append({"event":"corrupt","acks":bad_acks})
        # Bind a new session; the previous session must then be rejected.
        old=session;session=secrets.randbits(64) or 2;c.session=session;c.send(MessageType.HELLO,encode_hello(1,session));c.send(MessageType.HEARTBEAT,encode_heartbeat(old,2));stale=c.drain();stale_acks=ack_results(stale);events.append({"event":"old_session","acks":stale_acks})
        session=secrets.randbits(64) or 3;c.session=session;c.send(MessageType.HELLO,encode_hello(1,session));c.send(MessageType.SET_MODE,encode_mode(session,2));c.send(MessageType.HEARTBEAT,encode_heartbeat(session,2));c.send(MessageType.SET_MODE,encode_mode(session,3));c.send(MessageType.SET_STABILIZED_SETPOINT,encode_setpoint(session,0,0,0,0,100));c.drain();time.sleep(.35);wd=c.heartbeat();statuses=[f.payload for f in wd if f.message_type==MessageType.NODE_STATUS];events.append({"event":"watchdog","status":[x.hex() for x in statuses]})
        post(a.server,"/api/telemetry",a.vehicle,node_key,{"vehicle_id":a.vehicle,"session":session,"health":"online","packet_age_ms":0,"faults":["corrupt_rejected","old_session_rejected"],"latency_ms":max(c.latencies_ms)})
        watchdog_abort=any(x and x[0] in (4,5) for x in statuses)
        all_acks=ack_results(c.received)
        ok=initial_acks.count(RejectCode.OK.value)==5 and RejectCode.BAD_CRC.value in all_acks and RejectCode.SESSION_MISMATCH.value in all_acks and watchdog_abort
        events.append({"event":"complete","ok":ok,"observed_ack_codes":sorted(set(all_acks))})
        if not ok:raise RuntimeError("conformance rejection missing")
    finally:
        c.close();open(a.log,"w").write("\n".join(json.dumps(x,sort_keys=True) for x in events)+"\n")

if __name__=="__main__":main()
