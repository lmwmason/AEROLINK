"""Loopback-only simulation API, operator dashboard, and SSE telemetry."""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import json,threading,time
from .security import MAX_HTTP_BODY

# Maps a Vehicle.state value to a human label and the CSS badge class
# that colors it in the dashboard below (PRD SV-5: the UI must clearly
# distinguish available/assigned/degraded/maintenance/unavailable nodes).
STATE_LABEL={"available":("Available","ok"),"assigned":("Assigned","assigned"),"degraded":("Degraded","degraded"),"maintenance":("Maintenance","maintenance"),"offline":("Unavailable","offline"),"online":("Online","ok")}
DASHBOARD=("""<!doctype html><meta charset=utf-8><title>AEROLINK SITL Fleet</title>
<style>
body{font:14px system-ui,sans-serif;margin:1.5rem;color:#1a1a1a}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:.4rem .6rem;text-align:left}
.badge{padding:.1rem .5rem;border-radius:1rem;font-size:.8rem;color:#fff;background:#57606a}
.ok{background:#1a7f37}.assigned{background:#0969da}.degraded{background:#bf8700}.maintenance{background:#6e7781}.offline{background:#cf222e}
</style>
<h1>AEROLINK simulated fleet</h1>
<p>Read-only, non-actuating transport validation dashboard. Every node here is a
software SITL/Fake-FC node; nothing on this page arms, flies, or activates
payload hardware.</p>
<table id=fleet><thead><tr><th>ID<th>State<th>Session<th>Packet age ms<th>Mission<th>Faults</thead><tbody></tbody></table>
<h2>Missions</h2>
<table id=missions><thead><tr><th>ID<th>State<th>Vehicles<th>Authorized</thead><tbody></tbody></table>
<script>
const STATE_LABEL=__STATE_LABEL_JSON__;
async function refresh(){
  let d=await(await fetch('/api/fleet')).json();
  fleet.tBodies[0].innerHTML=d.vehicles.map(v=>{let l=STATE_LABEL[v.state]||[v.state,''];return `<tr><td>${v.vehicle_id}<td><span class="badge ${l[1]}">${l[0]}</span><td>${v.session}<td>${v.packet_age_ms}<td>${v.mission_id||''}<td>${(v.faults||[]).join(', ')}</tr>`}).join('');
  missions.tBodies[0].innerHTML=d.missions.map(m=>`<tr><td>${m.mission_id}<td>${m.state}<td>${m.vehicles.join(',')}<td>${m.authorized}</tr>`).join('');
}
refresh();setInterval(refresh,1000);
</script>""".replace("__STATE_LABEL_JSON__",json.dumps(STATE_LABEL))).encode()

def _vehicle_id(path,prefix):
    rest=path[len(prefix):]
    if not rest.isdigit():raise ValueError("invalid vehicle id")
    return int(rest)

class SimulationHttpServer:
    def __init__(self,fleet,security,operator_token,port=0):
        self.fleet=fleet;self.security=security;self.operator_token=operator_token
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send_json(self,code,obj,headers=None):
                body=json.dumps(obj,default=str).encode();self.send_response(code);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)))
                for key,value in (headers or {}).items():self.send_header(key,value)
                self.end_headers();self.wfile.write(body)
            def operator_token(self):
                query=parse_qs(urlsplit(self.path).query)
                if "token" in query:return query["token"][0]
                auth=self.headers.get("Authorization","")
                if auth.startswith("Bearer "):return auth[7:]
                for item in self.headers.get("Cookie","").split(";"):
                    if item.strip().startswith("aerolink_session="):return item.strip().split("=",1)[1]
                return ""
            def require(self,permission):return owner.security.authorize_operator(self.operator_token(),permission)
            def path_only(self):return urlsplit(self.path).path
            def do_GET(self):
                path=self.path_only()
                try:self.require("read")
                except PermissionError:self.send_json(403,{"error":"forbidden"});return
                if path=="/api/fleet":self.send_json(200,owner.fleet.dashboard())
                elif path=="/api/missions":self.send_json(200,{"missions":owner.fleet.mission_history()})
                elif path=="/api/health-timeline":self.send_json(200,{"events":owner.fleet.health_timeline()})
                elif path=="/api/metrics":self.send_json(200,owner.fleet.metrics.snapshot())
                elif path=="/api/audit/export":self.send_json(200,owner.fleet.audit.export())
                elif path.startswith("/api/vehicles/"):
                    try:vehicle_id=_vehicle_id(path,"/api/vehicles/");self.send_json(200,owner.fleet.node_detail(vehicle_id))
                    except (ValueError,KeyError):self.send_json(404,{"error":"unknown vehicle"})
                elif path=="/api/stream":self.stream()
                elif path=="/":
                    self.send_response(200);self.send_header("Content-Type","text/html");self.send_header("Set-Cookie",f"aerolink_session={self.operator_token()}; HttpOnly; SameSite=Strict");self.send_header("Content-Length",str(len(DASHBOARD)));self.end_headers();self.wfile.write(DASHBOARD)
                else:self.send_json(404,{"error":"not found"})
            def stream(self):
                self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Cache-Control","no-cache");self.send_header("Connection","keep-alive");self.end_headers()
                try:
                    for _ in range(20):
                        chunk=f"data: {json.dumps(owner.fleet.dashboard(),default=str)}\n\n".encode()
                        self.wfile.write(chunk);self.wfile.flush();time.sleep(.2)
                except (BrokenPipeError,ConnectionResetError):pass
            def read_json(self):
                length=int(self.headers.get("Content-Length","0"))
                if length<0 or length>MAX_HTTP_BODY:raise ValueError("request too large")
                body=self.rfile.read(length);return (json.loads(body) if body else {}),body
            def do_POST(self):
                path=self.path_only()
                if path in ("/api/register","/api/telemetry"):return self.do_node_post(path)
                try:
                    if path=="/api/missions":
                        self.require("authorize");data,_=self.read_json();m=owner.fleet.create_mission(int(data["count"]));self.send_json(200,{"mission_id":m.mission_id,"state":m.state,"vehicles":m.vehicles})
                    elif path.startswith("/api/missions/") and path.endswith("/authorize"):
                        self.require("authorize");data,_=self.read_json();mission_id=path[len("/api/missions/"):-len("/authorize")]
                        owner.fleet.authorize(mission_id,str(data.get("operator","operator")));self.send_json(200,{"mission_id":mission_id,"state":owner.fleet.missions[mission_id].state})
                    elif path.startswith("/api/missions/") and path.endswith("/abort-request"):
                        self.require("abort");data,_=self.read_json();mission_id=path[len("/api/missions/"):-len("/abort-request")]
                        owner.fleet.request_abort(mission_id,str(data.get("operator","operator")));self.send_json(200,{"mission_id":mission_id,"state":owner.fleet.missions[mission_id].state})
                    elif path.startswith("/api/missions/") and path.endswith("/abort-confirm"):
                        self.require("abort");data,_=self.read_json();mission_id=path[len("/api/missions/"):-len("/abort-confirm")]
                        owner.fleet.confirm_abort(mission_id,str(data.get("operator","operator")));self.send_json(200,{"mission_id":mission_id,"state":owner.fleet.missions[mission_id].state})
                    elif path.startswith("/api/missions/") and path.endswith("/complete"):
                        self.require("authorize");mission_id=path[len("/api/missions/"):-len("/complete")]
                        owner.fleet.complete_mission(mission_id);self.send_json(200,{"mission_id":mission_id,"state":owner.fleet.missions[mission_id].state})
                    elif path=="/api/ai/fleet-size":
                        self.require("read");data,_=self.read_json();proposal,valid=owner.fleet.advise_fleet_size(float(data.get("estimated_kg",1.0)))
                        self.send_json(200,{"valid":valid,"model":proposal.model,"version":proposal.version,"confidence":proposal.confidence,"output":proposal.output if valid else None})
                    elif path=="/api/ai/anomaly-summary":
                        self.require("read");proposal,valid=owner.fleet.advise_anomaly_summary()
                        self.send_json(200,{"valid":valid,"model":proposal.model,"version":proposal.version,"confidence":proposal.confidence,"output":proposal.output if valid else None})
                    elif path.startswith("/api/missions/") and path.endswith("/ai-summary"):
                        self.require("read");mission_id=path[len("/api/missions/"):-len("/ai-summary")];proposal,valid=owner.fleet.advise_mission_summary(mission_id)
                        self.send_json(200,{"valid":valid,"model":proposal.model,"version":proposal.version,"confidence":proposal.confidence,"output":proposal.output if valid else None})
                    elif path.startswith("/api/vehicles/") and path.endswith("/maintenance"):
                        self.require("maintenance");data,_=self.read_json();vehicle_id=int(path[len("/api/vehicles/"):-len("/maintenance")])
                        operator=str(data.get("operator","operator"))
                        if data.get("action")=="clear":owner.fleet.clear_maintenance(vehicle_id,operator)
                        else:owner.fleet.set_maintenance(vehicle_id,operator,str(data.get("note","")))
                        self.send_json(200,{"vehicle_id":vehicle_id,"state":owner.fleet.vehicles[vehicle_id].state})
                    else:self.send_json(404,{"error":"not found"})
                except PermissionError:self.send_json(403,{"error":"forbidden"})
                except (KeyError,ValueError) as exc:self.send_json(400,{"error":str(exc)})
            def do_node_post(self,path):
                length=int(self.headers.get("Content-Length","0"))
                if length<0 or length>MAX_HTTP_BODY:self.send_json(413,{"error":"request too large"});return
                try:
                    body=self.rfile.read(length);data=json.loads(body);node=int(data["vehicle_id"]);request_nonce=owner.security.verify_node(self.headers,"POST",path,body,node);owner.fleet.update_sim_node(data)
                    response=json.dumps({"accepted":True}).encode();headers=owner.security.response_headers(node,path,response,request_nonce)
                    self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(response)))
                    for key,value in headers.items():self.send_header(key,value)
                    self.end_headers();self.wfile.write(response)
                except Exception as exc:self.send_json(400,{"error":str(exc)})
        ThreadingHTTPServer.allow_reuse_address=True
        self.http=ThreadingHTTPServer(("127.0.0.1",port),Handler);self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
    @property
    def port(self):return self.http.server_address[1]
    def start(self):self.thread.start()
    def stop(self):self.http.shutdown();self.http.server_close();self.thread.join()
