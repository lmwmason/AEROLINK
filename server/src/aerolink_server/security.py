"""Offline application-layer authentication and authorization primitives."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,hmac,os,secrets,stat,threading,time
from pathlib import Path

MAX_HTTP_BODY=16384
REDACT_KEYS={"authorization","credential","key","secret","signature","token"}

def _digest(method,path,timestamp,nonce,body):return f"{method}\n{path}\n{timestamp}\n{nonce}\n{hashlib.sha256(body).hexdigest()}".encode()
def sign_message(key,method,path,timestamp,nonce,body):return hmac.new(key,_digest(method,path,timestamp,nonce,body),hashlib.sha256).hexdigest()

def node_headers(node_id,key,method,path,body,timestamp=None,nonce=None):
    timestamp=int(time.time()) if timestamp is None else timestamp;nonce=nonce or secrets.token_hex(16)
    return {"X-AEROLINK-Node":str(node_id),"X-AEROLINK-Time":str(timestamp),"X-AEROLINK-Nonce":nonce,"X-AEROLINK-Signature":sign_message(key,method,path,timestamp,nonce,body)}

def redact(value):
    if isinstance(value,dict):return {k:("[REDACTED]" if k.lower() in REDACT_KEYS else redact(v)) for k,v in value.items()}
    if isinstance(value,list):return [redact(v) for v in value]
    return value

def load_secret(name,path=None):
    value=os.environ.get(f"AEROLINK_SECRET_{name.upper()}")
    if value:return value.encode()
    if path:
        target=Path(path);mode=stat.S_IMODE(target.stat().st_mode)
        if mode&0o077:raise PermissionError("secret file must be owner-only")
        value=target.read_bytes().strip()
        if len(value)<32:raise ValueError("secret must contain at least 32 bytes")
        return value
    raise RuntimeError(f"secret {name} not configured")

@dataclass
class OperatorSession:
    role:str;expires_at:float

class SecurityContext:
    ROLE_PERMISSIONS={"viewer":{"read"},"operator":{"read","authorize","abort"},"admin":{"read","authorize","abort","maintenance","rotate_keys"}}
    def __init__(self,node_keys,clock=time.monotonic,wall_clock=time.time,rate=30,burst=60):
        self.node_keys=dict(node_keys);self.previous_keys={};self.clock=clock;self.wall_clock=wall_clock;self.rate=rate;self.burst=burst
        self.seen={};self.buckets={};self.sessions={};self.restart_count=0
        # SimulationHttpServer is a ThreadingHTTPServer: two concurrent
        # requests from the same node otherwise have a narrow
        # check-then-write window on both the rate-limit bucket and the
        # nonce-replay cache below.
        self._lock=threading.Lock()
    def rotate_node_key(self,node_id,new_key):
        if len(new_key)<32:raise ValueError("node key too short")
        self.previous_keys[node_id]=self.node_keys[node_id];self.node_keys[node_id]=new_key
    def create_operator_session(self,role,ttl_seconds=900):
        if role not in self.ROLE_PERMISSIONS or not 1<=ttl_seconds<=3600:raise ValueError("invalid role/session lifetime")
        token=secrets.token_urlsafe(32);self.sessions[token]=OperatorSession(role,self.clock()+ttl_seconds);return token
    def authorize_operator(self,token,permission):
        session=self.sessions.get(token)
        if not session or self.clock()>=session.expires_at or permission not in self.ROLE_PERMISSIONS[session.role]:raise PermissionError("operator authorization denied")
        return session.role
    def verify_node(self,headers,method,path,body,expected_node):
        if len(body)>MAX_HTTP_BODY:raise ValueError("request too large")
        node=int(headers.get("X-AEROLINK-Node","0"));timestamp=int(headers.get("X-AEROLINK-Time","0"));nonce=headers.get("X-AEROLINK-Nonce","");signature=headers.get("X-AEROLINK-Signature","")
        if node!=expected_node or node not in self.node_keys:raise PermissionError("unknown node identity")
        if abs(int(self.wall_clock())-timestamp)>30:raise PermissionError("request clock outside authentication window")
        with self._lock:
            now=self.clock();tokens,last=self.buckets.get(node,(self.burst,now));tokens=min(self.burst,tokens+(now-last)*self.rate)
            if tokens<1:raise PermissionError("node request rate exceeded")
            self.buckets[node]=(tokens-1,now)
            seen=self.seen.setdefault(node,{})
            for old,expiry in list(seen.items()):
                if expiry<=now:del seen[old]
            if not nonce or nonce in seen:raise PermissionError("request replay")
            valid=any(hmac.compare_digest(signature,sign_message(key,method,path,timestamp,nonce,body)) for key in (self.node_keys[node],self.previous_keys.get(node,b"")))
            if not valid:raise PermissionError("node authentication failed")
            seen[nonce]=now+60;return nonce
    def response_headers(self,node_id,path,body,request_nonce):
        timestamp=int(self.wall_clock());nonce="response:"+request_nonce
        return {"X-AEROLINK-Server-Time":str(timestamp),"X-AEROLINK-Server-Nonce":nonce,"X-AEROLINK-Server-Signature":sign_message(self.node_keys[node_id],"RESPONSE",path,timestamp,nonce,body)}

def verify_server_response(key,path,body,headers,request_nonce):
    timestamp=int(headers.get("X-AEROLINK-Server-Time","0"));nonce=headers.get("X-AEROLINK-Server-Nonce","");signature=headers.get("X-AEROLINK-Server-Signature","")
    expected="response:"+request_nonce
    if nonce!=expected or not hmac.compare_digest(signature,sign_message(key,"RESPONSE",path,timestamp,nonce,body)):raise PermissionError("server authentication failed")
