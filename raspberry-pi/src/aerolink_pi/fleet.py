"""Authenticated, versioned private-LAN messages for one configured server."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, hmac, json
from .generated_protocol import FLEET_MAX_CANONICAL_BYTES

VERSION = 1
ALLOWED_KINDS = {"ASSIGN", "TRANSITION", "SETPOINT", "ABORT", "PING"}

@dataclass(frozen=True)
class FleetPacket:
    sender: str
    vehicle_id: int
    epoch: int
    sequence: int
    issued_ms: int
    ttl_ms: int
    kind: str
    payload: dict
    signature: str = ""
    version: int = VERSION

    def canonical(self) -> bytes:
        body={"version":self.version,"sender":self.sender,"vehicle_id":self.vehicle_id,"epoch":self.epoch,"sequence":self.sequence,"issued_ms":self.issued_ms,"ttl_ms":self.ttl_ms,"kind":self.kind,"payload":self.payload}
        return json.dumps(body,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

    def sign(self, key: bytes) -> "FleetPacket":
        return FleetPacket(**{**self.__dict__,"signature":hmac.new(key,self.canonical(),hashlib.sha256).hexdigest()})

class FleetValidator:
    def __init__(self, vehicle_id:int, server_id:str, key:bytes):
        if not 1 <= vehicle_id <= 15 or not key: raise ValueError("invalid identity/key")
        self.vehicle_id,self.server_id,self.key=vehicle_id,server_id,key
        self.epoch=0; self.last_sequence=-1
    def accept(self,p:FleetPacket,now_ms:int)->None:
        if p.version!=VERSION: raise ValueError("version")
        if p.sender!=self.server_id or p.vehicle_id!=self.vehicle_id: raise ValueError("identity")
        if p.kind not in ALLOWED_KINDS or not 0 < p.ttl_ms <= 1000: raise ValueError("kind/bounds")
        if len(p.canonical())>FLEET_MAX_CANONICAL_BYTES: raise ValueError("packet too large")
        if not hmac.compare_digest(p.signature,hmac.new(self.key,p.canonical(),hashlib.sha256).hexdigest()): raise ValueError("authentication")
        if p.issued_ms>now_ms+10 or now_ms-p.issued_ms>p.ttl_ms: raise ValueError("stale")
        if p.epoch<self.epoch or (p.epoch==self.epoch and p.sequence<=self.last_sequence): raise ValueError("replay")
        if p.epoch>self.epoch: self.epoch=p.epoch; self.last_sequence=-1
        self.last_sequence=p.sequence
