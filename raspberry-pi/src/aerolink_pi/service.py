"""Deterministic vehicle-node core; transport loops call receive/tick."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from enum import Enum
import json, secrets
from .fleet import FleetPacket,FleetValidator
from .localization import SimulatorLocalization
from .protocol import Frame,MessageType,encode_hello,encode_setpoint

class MissionState(str,Enum):
    IDLE="IDLE"; AUTHORIZED="AUTHORIZED"; LAUNCH="LAUNCH"; FORM="FORM"; TRANSIT_TO_LOCKER="TRANSIT_TO_LOCKER"; PICKUP="PICKUP"; TRANSIT_TO_DESTINATION="TRANSIT_TO_DESTINATION"; DELIVER="DELIVER"; RETURN="RETURN"; LAND="LAND"; ABORT="ABORT"; FAULT="FAULT"

TRANSITIONS={MissionState.IDLE:{MissionState.AUTHORIZED},MissionState.AUTHORIZED:{MissionState.LAUNCH,MissionState.ABORT},MissionState.LAUNCH:{MissionState.FORM,MissionState.ABORT},MissionState.FORM:{MissionState.TRANSIT_TO_LOCKER,MissionState.ABORT},MissionState.TRANSIT_TO_LOCKER:{MissionState.PICKUP,MissionState.ABORT},MissionState.PICKUP:{MissionState.TRANSIT_TO_DESTINATION,MissionState.ABORT},MissionState.TRANSIT_TO_DESTINATION:{MissionState.DELIVER,MissionState.ABORT},MissionState.DELIVER:{MissionState.RETURN,MissionState.ABORT},MissionState.RETURN:{MissionState.LAND,MissionState.ABORT},MissionState.LAND:{MissionState.IDLE},MissionState.ABORT:{MissionState.LAND,MissionState.FAULT},MissionState.FAULT:{MissionState.IDLE}}

@dataclass
class FcCache:
    state:str="DISABLED"; healthy:bool=False; last_seen_ms:int=0; session:int=0

class VehicleService:
    def __init__(self,vehicle_id:int,server_id:str,key:bytes,uart,localization=None,queue_limit:int=16):
        if not 1<=vehicle_id<=15: raise ValueError("vehicle id")
        self.vehicle_id=vehicle_id;self.validator=FleetValidator(vehicle_id,server_id,key);self.uart=uart
        self.localization=localization or SimulatorLocalization();self.queue=deque(maxlen=queue_limit)
        self.state=MissionState.IDLE;self.fc=FcCache();self.session=secrets.randbits(64) or 1;self.seq=0;self.events=[];self.mission_id=None
    def log(self,now,event,**data): self.events.append(json.dumps({"t":now,"vehicle":self.vehicle_id,"event":event,**data},sort_keys=True))
    def connect_fc(self,now_ms:int):
        previous=self.session
        for _ in range(8):
            candidate=secrets.randbits(64)
            if candidate and candidate!=previous:break
        else:raise RuntimeError("session nonce source collision")
        self.session=candidate;self.seq+=1
        self.uart.receive(Frame(MessageType.HELLO,self.vehicle_id,0,self.seq,now_ms,encode_hello(1,self.session)),now_ms)
        self.fc=FcCache("STANDBY",True,now_ms,self.session);self.queue.clear();self.log(now_ms,"fc_session",session=self.session)
    def receive_server(self,packet:FleetPacket,now_ms:int):
        self.validator.accept(packet,now_ms)
        if len(self.queue)==self.queue.maxlen: raise BufferError("command queue full")
        self.queue.append(packet)
    def tick(self,now_ms:int):
        while self.queue:
            p=self.queue.popleft()
            if p.kind=="ASSIGN": self.mission_id=p.payload["mission_id"]; self._transition(MissionState.AUTHORIZED,now_ms)
            elif p.kind=="TRANSITION": self._transition(MissionState(p.payload["state"]),now_ms)
            elif p.kind=="ABORT": self.state=MissionState.ABORT;self.log(now_ms,"abort")
            elif p.kind=="SETPOINT":
                if self.state not in {MissionState.LAUNCH,MissionState.FORM,MissionState.TRANSIT_TO_LOCKER,MissionState.TRANSIT_TO_DESTINATION,MissionState.RETURN,MissionState.LAND}: raise ValueError("setpoint not allowed in mission state")
                vals=p.payload
                payload=encode_setpoint(self.session,int(vals["roll_cd"]),int(vals["pitch_cd"]),int(vals["yaw_rate_cds"]),int(vals["vertical_rate_cms"]),min(p.ttl_ms,100))
                self.seq+=1;self.uart.receive(Frame(MessageType.SET_STABILIZED_SETPOINT,self.vehicle_id,int(vals.get("formation_id",0)),self.seq,now_ms,payload),now_ms)
        if self.fc.healthy and now_ms-self.fc.last_seen_ms>300: self.fc.healthy=False;self.state=MissionState.ABORT;self.log(now_ms,"uart_timeout")
    def _transition(self,new:MissionState,now:int):
        if new not in TRANSITIONS.get(self.state,set()): raise ValueError(f"invalid transition {self.state}->{new}")
        old=self.state;self.state=new;self.log(now,"mission_transition",old=old.value,new=new.value)
    def replay(self): return [json.loads(e) for e in self.events]

class FakeFc:
    """Protocol-faithful simulation endpoint; never arms or models motors."""
    def __init__(self,vehicle_id:int): self.vehicle_id=vehicle_id;self.session=0;self.state="DISABLED";self.frames=[];self.online=True
    def receive(self,frame:Frame,now_ms:int):
        if not self.online: raise ConnectionError("FC offline")
        wire=frame.encode();decoded=Frame.decode(wire,expected_vehicle_id=self.vehicle_id)
        if decoded.message_type==MessageType.HELLO:
            self.session=int.from_bytes(decoded.payload[3:11],"little");self.state="STANDBY";self.frames.clear()
        elif decoded.message_type==MessageType.SET_STABILIZED_SETPOINT:
            if int.from_bytes(decoded.payload[:8],"little")!=self.session: raise ValueError("session")
        self.frames.append(decoded)
