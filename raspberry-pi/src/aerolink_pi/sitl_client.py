"""Real TCP-UART client for the non-actuating Betaflight SITL endpoint."""
from __future__ import annotations
from collections import defaultdict
import socket,struct,time
from .protocol import Frame,MessageType,RejectCode,StreamDecoder,encode_heartbeat,encode_hello,encode_mode,encode_setpoint

class SitlUartClient:
    def __init__(self,vehicle_id:int,port:int,session:int):
        self.vehicle_id=vehicle_id;self.port=port;self.session=session;self.sock=None
        self.decoder=StreamDecoder(expected_vehicle_id=vehicle_id);self.sequences=defaultdict(int);self.received=[];self.latencies_ms=[];self.last_first_byte_at=None
    def connect(self,timeout=10):
        deadline=time.monotonic()+timeout
        while True:
            try:self.sock=socket.create_connection(("127.0.0.1",self.port),timeout=.5);self.sock.settimeout(.005);return
            except OSError:
                if time.monotonic()>=deadline:raise
                time.sleep(.05)
    @staticmethod
    def now_ms():return int(time.monotonic()*1000)&0xffffffff
    def send(self,kind:MessageType,payload:bytes,chunks:tuple[int,...]=()):
        self.sequences[kind]+=1;frame=Frame(kind,self.vehicle_id,0,self.sequences[kind],self.now_ms(),payload).encode();started=time.monotonic()
        if chunks:
            pos=0
            for size in chunks:self.sock.sendall(frame[pos:pos+size]);pos+=size;time.sleep(.002)
            self.sock.sendall(frame[pos:])
        else:self.sock.sendall(frame)
        return frame,started
    def send_raw(self,frame:bytes,chunks:tuple[int,...]=(),delays_ms:tuple[int,...]=()):
        """Send an exact conformance vector, optionally as TCP partial frames."""
        pos=0
        for index,size in enumerate(chunks):
            self.sock.sendall(frame[pos:pos+size]);pos+=size
            time.sleep((delays_ms[index] if index<len(delays_ms) else 2)/1000)
        self.sock.sendall(frame[pos:])
    def drain(self,duration=2.0):
        deadline=time.monotonic()+duration;quiet_deadline=None;out=[];self.last_first_byte_at=None
        while time.monotonic()<deadline:
            try:data=self.sock.recv(4096)
            except socket.timeout:
                if quiet_deadline is not None and time.monotonic()>=quiet_deadline:break
                continue
            if not data:break
            if self.last_first_byte_at is None:self.last_first_byte_at=time.monotonic()
            out.extend(self.decoder.feed(data));quiet_deadline=time.monotonic()+.1
        self.received.extend(out);return out
    def handshake(self,partial=False):
        _,started=self.send(MessageType.HELLO,encode_hello(1,self.session),(1,2,3,5) if partial else ())
        frames=self.drain();self.latencies_ms.append(((self.last_first_byte_at or time.monotonic())-started)*1000)
        types={f.message_type for f in frames}
        if not {MessageType.ACK,MessageType.HELLO,MessageType.CAPABILITIES}<=types:raise RuntimeError(f"handshake responses missing: {types}")
        return frames
    def heartbeat(self):
        _,started=self.send(MessageType.HEARTBEAT,encode_heartbeat(self.session,2));frames=self.drain();self.latencies_ms.append(((self.last_first_byte_at or time.monotonic())-started)*1000);return frames
    def set_mode(self,state:int):self.send(MessageType.SET_MODE,encode_mode(self.session,state));return self.drain()
    def setpoint(self):self.send(MessageType.SET_STABILIZED_SETPOINT,encode_setpoint(self.session,0,0,0,0,100));return self.drain()
    def close(self):
        if self.sock:self.sock.close();self.sock=None

def ack_results(frames):
    return [f.payload[5] for f in frames if f.message_type==MessageType.ACK and len(f.payload)==6]
