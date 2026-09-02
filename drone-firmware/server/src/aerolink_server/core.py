"""Offline deterministic fleet management and advisory-AI boundary."""
from __future__ import annotations
from dataclasses import asdict,dataclass
from enum import Enum
import hashlib,json,threading,uuid
from .ai import AdvisoryAiService,AiTask,DeterministicFakeProvider
from .metrics import MetricsRegistry

class FleetState(str,Enum):
    ONLINE="online";OFFLINE="offline";DEGRADED="degraded";MAINTENANCE="maintenance";AVAILABLE="available";ASSIGNED="assigned"
@dataclass
class Vehicle:
    vehicle_id:int;state:FleetState=FleetState.OFFLINE;healthy:bool=False;battery_pct:int=0;capacity_kg:float=1.0;last_seen_ms:int=0;mission_id:str|None=None;session:int=0;packet_age_ms:float=0;faults:list[str]|None=None;latency_ms:float=0
@dataclass(frozen=True)
class AiProposal:
    model:str;version:str;kind:str;output:dict;confidence:float;input_ref:str
class FakeAi:
    def recommend_count(self,payload_kg:float,input_ref="test")->AiProposal:
        return AiProposal("deterministic-fake","1","fleet_size",{"count":max(1,int(payload_kg+0.999))},1.0,input_ref)
class AiValidator:
    def validate(self,p:AiProposal)->bool:
        return p.model!="" and p.kind in {"fleet_size","delivery","route_ranking","anomaly"} and 0<=p.confidence<=1 and (p.kind!="fleet_size" or isinstance(p.output.get("count"),int) and 1<=p.output["count"]<=15)
class AuditLog:
    def __init__(self,repository=None):self.entries=[];self._hash="0"*64;self.repository=repository
    def append(self,kind:str,data:dict):
        body=json.dumps({"index":len(self.entries),"kind":kind,"data":data,"previous":self._hash},sort_keys=True,separators=(",",":"),default=str)
        self._hash=hashlib.sha256(body.encode()).hexdigest();entry={"body":body,"hash":self._hash};self.entries.append(entry)
        if self.repository is not None:self.repository.append_audit(len(self.entries)-1,body,self._hash)
    def load_from(self,repository):
        self.entries=list(repository.load_audit());self._hash=self.entries[-1]["hash"] if self.entries else "0"*64
    def export(self):return {"entries":self.entries,"chain_valid":self.verify(),"count":len(self.entries)}
    def for_vehicle(self,vehicle_id:int):
        out=[]
        for entry in self.entries:
            body=json.loads(entry["body"])
            if body["data"].get("vehicle_id")==vehicle_id or body["data"].get("vehicle")==vehicle_id:out.append(body)
        return out
    def verify(self):
        previous="0"*64
        for index,entry in enumerate(self.entries):
            body=json.loads(entry["body"])
            if body["index"]!=index or body["previous"]!=previous or hashlib.sha256(entry["body"].encode()).hexdigest()!=entry["hash"]:return False
            previous=entry["hash"]
        return True
class BuildingGraph:
    def __init__(self):self.edges={"HOME":["LOCKER_F1"],"LOCKER_F1":["HOME","STAIR_F1_F2"],"STAIR_F1_F2":["LOCKER_F1","ROBOTICS_LAB_F2"],"ROBOTICS_LAB_F2":["STAIR_F1_F2"]}
    def route(self,start,end):
        q=[(start,[start])];seen={start}
        while q:
            node,path=q.pop(0)
            if node==end:return path
            for nxt in sorted(self.edges.get(node,[])):
                if nxt not in seen:seen.add(nxt);q.append((nxt,path+[nxt]))
        raise ValueError("no route")
    def validate(self,route:list[str])->bool:
        if not route or route[0] not in self.edges:return False
        return all(route[i+1] in self.edges.get(route[i],[]) for i in range(len(route)-1))
# Mirrors schemas/state-machines.json:server_mission.
MISSION_TRANSITIONS={"PLANNED":{"AUTHORIZED","ABORT_REQUESTED"},"AUTHORIZED":{"ABORT_REQUESTED","COMPLETED"},"ABORT_REQUESTED":{"ABORTED"},"ABORTED":set(),"COMPLETED":set()}
@dataclass
class Mission:
    mission_id:str;group_id:str;epoch:int;revision:int;vehicles:list[int];route:list[str];state:str="PLANNED";authorized:bool=False
    def transition(self,target:str):
        if target not in MISSION_TRANSITIONS.get(self.state,set()):raise ValueError(f"illegal mission transition {self.state}->{target}")
        self.state=target
class FleetServer:
    def __init__(self,repository=None,ai_provider=None):
        # Serializes every state-mutating call below: SimulationHttpServer
        # is a ThreadingHTTPServer, so concurrent operator/node requests
        # (e.g. two simultaneous delivery requests) must not race on
        # allocate()+create_mission() and double-assign a vehicle.
        self._lock=threading.RLock()
        self.repository=repository;self.reconciliation_state="STOPPED"
        self.vehicles={i:Vehicle(i) for i in range(1,16)};self.audit=AuditLog(repository);self.graph=BuildingGraph();self.epoch=0;self.missions={};self.reservations={}
        self.ai=AdvisoryAiService(ai_provider or DeterministicFakeProvider(),self.audit);self.metrics=MetricsRegistry(self.audit)
        if repository is not None:self._reconcile()
        else:self.reconciliation_state="READY"
    def _persist_vehicle(self,v:Vehicle):
        if self.repository is not None:self.repository.save_vehicle(v.vehicle_id,asdict(v))
    def _persist_mission(self,m:Mission):
        if self.repository is not None:self.repository.save_mission(m.mission_id,asdict(m))
    def _reconcile(self):
        """Restore persisted state and force any in-flight mission to a
        non-executable state; a restarted server never resumes or replays
        an old mission epoch (AGENT.md "Server restart behavior")."""
        self.reconciliation_state="RECOVERING"
        for vehicle_id,data in self.repository.load_vehicles().items():
            v=self.vehicles[int(vehicle_id)]
            for key,value in data.items():setattr(v,key,FleetState(value) if key=="state" else value)
        self.audit.load_from(self.repository)
        self.epoch=int(self.repository.get_meta("epoch",0))
        self.reconciliation_state="RECONCILING"
        # Only an AUTHORIZED mission holds a live corridor/stairwell
        # reservation going forward (create_mission sets it, confirm_abort/
        # complete_mission clear it), so self.reservations is rebuilt from
        # nothing here — no prior session's mission is trusted to still be
        # executing. PLANNED/AUTHORIZED is force-transitioned to
        # ABORT_REQUESTED as before (an operator must still confirm_abort
        # explicitly). An ABORT_REQUESTED mission left over from a live,
        # never-confirmed operator abort-request is not re-transitioned
        # (that confirmation stays an explicit operator action), but its
        # vehicles/reservation are still released on restart — no live
        # process remains to finish that abort, so holding the corridor
        # forever would be worse than freeing it.
        reconciled=[]
        for mission_id,data in self.repository.load_missions().items():
            m=Mission(**data);self.missions[mission_id]=m
            if m.state in ("PLANNED","AUTHORIZED"):
                previous=m.state;m.transition("ABORT_REQUESTED");self._persist_mission(m)
                self.audit.append("restart_reconciliation",{"mission":mission_id,"from":previous,"to":m.state});reconciled.append(mission_id)
            elif m.state=="ABORT_REQUESTED":
                self.audit.append("restart_reconciliation",{"mission":mission_id,"from":m.state,"to":m.state,"released_on_restart":True});reconciled.append(mission_id)
        for v in self.vehicles.values():
            if v.mission_id in reconciled:v.state=FleetState.AVAILABLE if v.healthy else FleetState.OFFLINE;v.mission_id=None;self._persist_vehicle(v)
        self.reconciliation_state="READY"
        self.audit.append("server_ready",{"epoch":self.epoch,"reconciled_missions":reconciled})
    def ingest(self,vehicle_id:int,healthy:bool,battery:int,now_ms:int):
        with self._lock:
            v=self.vehicles[vehicle_id]
            if v.state==FleetState.MAINTENANCE:self.audit.append("telemetry",{"vehicle":vehicle_id,"healthy":healthy,"ignored":"maintenance"});return
            v.healthy=healthy;v.battery_pct=battery;v.last_seen_ms=now_ms
            v.state=(FleetState.ASSIGNED if healthy else FleetState.DEGRADED) if v.mission_id is not None else (FleetState.AVAILABLE if healthy and battery>=30 else FleetState.DEGRADED)
            self._persist_vehicle(v);self.audit.append("telemetry",{"vehicle":vehicle_id,"healthy":healthy})
    def set_maintenance(self,vehicle_id:int,operator:str,note:str=""):
        if not operator:raise PermissionError("operator identity required")
        with self._lock:
            v=self.vehicles[vehicle_id]
            if v.mission_id is not None:raise ValueError("vehicle is assigned to an active mission")
            v.state=FleetState.MAINTENANCE;self._persist_vehicle(v);self.audit.append("maintenance_set",{"vehicle":vehicle_id,"operator":operator,"note":note})
    def clear_maintenance(self,vehicle_id:int,operator:str):
        if not operator:raise PermissionError("operator identity required")
        with self._lock:
            v=self.vehicles[vehicle_id];v.state=FleetState.OFFLINE;self._persist_vehicle(v);self.audit.append("maintenance_cleared",{"vehicle":vehicle_id,"operator":operator})
    def allocate(self,count:int)->list[int]:
        with self._lock:
            eligible=[v.vehicle_id for v in self.vehicles.values() if v.state==FleetState.AVAILABLE and v.healthy]
            if not 1<=count<=15 or len(eligible)<count:raise ValueError("insufficient healthy vehicles")
            return sorted(eligible)[:count]
    def create_mission(self,count:int)->Mission:
        with self._lock:
            selected=self.allocate(count)
            route=self.graph.route("HOME","LOCKER_F1")+self.graph.route("LOCKER_F1","ROBOTICS_LAB_F2")[1:]+self.graph.route("ROBOTICS_LAB_F2","HOME")[1:]
            if not self.graph.validate(route):raise ValueError("invalid route")
            conflicts={self.reservations[n] for n in route if n in self.reservations}
            if conflicts:raise ValueError(f"corridor/stairwell conflict with mission(s) {sorted(conflicts)}")
            self.epoch+=1
            if self.repository is not None:self.repository.set_meta("epoch",self.epoch)
            mid=f"mission-{self.epoch}";gid=f"group-{self.epoch}"
            m=Mission(mid,gid,self.epoch,1,selected,route);self.missions[mid]=m
            for node in route:self.reservations[node]=mid
            for i in selected:self.vehicles[i].state=FleetState.ASSIGNED;self.vehicles[i].mission_id=mid;self._persist_vehicle(self.vehicles[i])
            self._persist_mission(m);self.audit.append("mission_created",asdict(m));return m
    def _release(self,m:Mission):
        for node in list(self.reservations):
            if self.reservations[node]==m.mission_id:del self.reservations[node]
        for i in m.vehicles:
            v=self.vehicles[i]
            # A vehicle only belongs to m if it still points back to m: a
            # restart can force-release m's vehicles early (see
            # _reconcile), after which one may be reassigned to a newer
            # mission before an operator confirms this abort on the old,
            # now-stale mission id. Without this check, confirming that
            # stale abort would silently rip the vehicle away from its
            # current mission while that mission's own record still lists
            # it as assigned.
            if v.mission_id==m.mission_id:v.mission_id=None;v.state=FleetState.AVAILABLE if v.healthy else FleetState.OFFLINE;self._persist_vehicle(v)
    def authorize(self,mission_id:str,operator:str):
        if not operator:raise PermissionError("operator identity required")
        with self._lock:
            m=self.missions[mission_id];m.transition("AUTHORIZED");m.authorized=True;self._persist_mission(m);self.audit.append("operator_authorize",{"mission":mission_id,"operator":operator})
    def request_abort(self,mission_id:str,operator:str):
        if not operator:raise PermissionError("operator identity required")
        with self._lock:
            m=self.missions[mission_id];m.transition("ABORT_REQUESTED");self._persist_mission(m);self.audit.append("operator_abort_request",{"mission":mission_id,"operator":operator})
    def confirm_abort(self,mission_id:str,operator:str):
        if not operator:raise PermissionError("operator identity required")
        with self._lock:
            m=self.missions[mission_id];m.transition("ABORTED");self._release(m);self._persist_mission(m);self.audit.append("operator_abort_confirm",{"mission":mission_id,"operator":operator})
    def complete_mission(self,mission_id:str):
        with self._lock:
            m=self.missions[mission_id];m.transition("COMPLETED");self._release(m);self._persist_mission(m);self.audit.append("mission_completed",{"mission":mission_id})
    def update_sim_node(self,data:dict):
        with self._lock:
            vehicle_id=int(data["vehicle_id"]);v=self.vehicles[vehicle_id]
            if v.state==FleetState.MAINTENANCE:self.audit.append("sim_node",{**data,"ignored":"maintenance"});return
            v.session=int(data["session"]);v.packet_age_ms=float(data.get("packet_age_ms",0));v.faults=list(data.get("faults",[]));v.latency_ms=float(data.get("latency_ms",0));v.healthy=data.get("health")=="online"
            v.state=(FleetState.ASSIGNED if v.healthy else FleetState.DEGRADED) if v.mission_id is not None else (FleetState.AVAILABLE if v.healthy else FleetState.OFFLINE)
            self.metrics.record_node_update(v.latency_ms,v.packet_age_ms)
            self._persist_vehicle(v);self.audit.append("sim_node",data)
    def advise_fleet_size(self,estimated_kg:float):
        """Advisory only: never allocates or creates a mission. The caller
        must still pass the returned count through allocate()/create_mission(),
        which independently re-validates it."""
        return self.ai.request(AiTask.FLEET_SIZE,{"estimated_kg":estimated_kg},max_fleet=15)
    def advise_mission_summary(self,mission_id:str):
        m=self.missions[mission_id]
        return self.ai.request(AiTask.MISSION_SUMMARY,{"mission_id":mission_id,"route":m.route},known_missions=set(self.missions))
    def advise_anomaly_summary(self):
        faults={v.vehicle_id:v.faults for v in self.vehicles.values() if v.faults}
        return self.ai.request(AiTask.ANOMALY_SUMMARY,{"faults":faults})
    def node_detail(self,vehicle_id:int)->dict:
        return {"vehicle":asdict(self.vehicles[vehicle_id]),"events":self.audit.for_vehicle(vehicle_id)}
    def mission_history(self)->list[dict]:return [asdict(m) for m in self.missions.values()]
    def health_timeline(self)->list[dict]:
        return [json.loads(e["body"]) for e in self.audit.entries if json.loads(e["body"])["kind"] in ("telemetry","sim_node") and not json.loads(e["body"])["data"].get("healthy",True)]
    def dashboard(self):
        return {"vehicles":[asdict(v) for v in self.vehicles.values()],"missions":[asdict(m) for m in self.missions.values()],"audit_entries":len(self.audit.entries),"reconciliation_state":self.reconciliation_state,"epoch":self.epoch}
