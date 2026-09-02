"""Provider-neutral advisory AI boundary (PRD SV-4, AGENT.md AI-advisory rule).

AI proposes; it never executes. Every proposal is validated against a
strict per-task schema plus deterministic domain rules before it can
reach `FleetServer`; missing, malformed, timed-out, or rule-violating
output falls back to a deterministic non-AI proposal, and if that also
fails to validate, nothing changes. No AI output is a directly
executable command: schema fields never carry an arm/motor/throttle/
setpoint/payload-activation instruction, and any hidden instruction
smuggled into free-text input (a parcel name, say) that echoes into
output is rejected by the same forbidden-token check.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re,time,uuid
from .security import redact

class AiTask(str,Enum):
    DELIVERY_INTERPRETATION="delivery_interpretation"
    FLEET_SIZE="fleet_size"
    ROUTE_RANKING="route_ranking"
    ANOMALY_SUMMARY="anomaly_summary"
    MAINTENANCE_EXPLANATION="maintenance_explanation"
    MISSION_SUMMARY="mission_summary"

# Forbidden in any AI output regardless of task: naming direct control
# authority is enough to reject the proposal, even inside a summary string.
FORBIDDEN_TOKENS=("arm","disarm","motor","throttle","payload_activate","setpoint","override_safety","bypass_validation")

SCHEMAS={
    AiTask.DELIVERY_INTERPRETATION:{"parcel_name":str,"destination":str,"estimated_kg":(int,float)},
    AiTask.FLEET_SIZE:{"count":int},
    AiTask.ROUTE_RANKING:{"ranked_routes":list},
    AiTask.ANOMALY_SUMMARY:{"summary":str,"vehicle_ids":list},
    AiTask.MAINTENANCE_EXPLANATION:{"vehicle_id":int,"explanation":str},
    AiTask.MISSION_SUMMARY:{"mission_id":str,"summary":str},
}

class AiValidationError(ValueError):pass

def _collect_strings(value,out:list):
    if isinstance(value,str):out.append(value)
    elif isinstance(value,dict):
        for v in value.values():_collect_strings(v,out)
    elif isinstance(value,list):
        for v in value:_collect_strings(v,out)

def validate_schema(task:AiTask,output:dict)->None:
    schema=SCHEMAS.get(task)
    if schema is None:raise AiValidationError(f"unsupported task {task}")
    if not isinstance(output,dict):raise AiValidationError("output must be an object")
    for key,types in schema.items():
        if key not in output:raise AiValidationError(f"missing field {key}")
        if isinstance(output[key],bool) or not isinstance(output[key],types):raise AiValidationError(f"field {key} has wrong type")
    strings=[];_collect_strings(output,strings);blob=" ".join(strings).lower()
    for token in FORBIDDEN_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b",blob):raise AiValidationError(f"forbidden control token in AI output: {token}")

@dataclass(frozen=True)
class AdvisoryProposal:
    request_id:str;task:AiTask;model:str;version:str;prompt_version:str;output:dict;confidence:float;created_ms:int;timed_out:bool=False;error:str|None=None

class AiProvider:
    """Interface every provider (fake or a future real one) must implement."""
    name="base"
    def propose(self,task:AiTask,context:dict,timeout_s:float)->AdvisoryProposal:raise NotImplementedError

class DeterministicFakeProvider(AiProvider):
    """No network calls; same input always yields the same output."""
    name="deterministic-fake"
    def __init__(self,version="1",prompt_version="v1",latency_s=0.0):
        self.version=version;self.prompt_version=prompt_version;self.latency_s=latency_s
    def propose(self,task,context,timeout_s):
        request_id=str(uuid.uuid4());started_ms=int(time.time()*1000)
        if self.latency_s>timeout_s:return AdvisoryProposal(request_id,task,self.name,self.version,self.prompt_version,{},0.0,started_ms,timed_out=True,error="timeout")
        try:output=self._compute(task,context)
        except Exception as exc:return AdvisoryProposal(request_id,task,self.name,self.version,self.prompt_version,{},0.0,started_ms,error=str(exc))
        return AdvisoryProposal(request_id,task,self.name,self.version,self.prompt_version,output,1.0,started_ms)
    def _compute(self,task,context):
        if task==AiTask.DELIVERY_INTERPRETATION:
            return {"parcel_name":str(context.get("parcel_name",""))[:200],"destination":str(context.get("destination","ROBOTICS_LAB_F2")),"estimated_kg":float(context.get("estimated_kg",1.0))}
        if task==AiTask.FLEET_SIZE:
            kg=float(context.get("estimated_kg",1.0));return {"count":max(1,min(15,int(kg)+1))}
        if task==AiTask.ROUTE_RANKING:
            return {"ranked_routes":sorted(context.get("routes",[]),key=len)}
        if task==AiTask.ANOMALY_SUMMARY:
            faults=context.get("faults",{});return {"summary":f"{len(faults)} node(s) reporting faults","vehicle_ids":sorted(faults)}
        if task==AiTask.MAINTENANCE_EXPLANATION:
            vehicle_id=int(context["vehicle_id"]);return {"vehicle_id":vehicle_id,"explanation":f"vehicle {vehicle_id} flagged: {context.get('reason','unspecified')}"}
        if task==AiTask.MISSION_SUMMARY:
            return {"mission_id":str(context.get("mission_id","")),"summary":f"mission {context.get('mission_id','')} covering {len(context.get('route',[]))} waypoints"}
        raise ValueError(f"unsupported task {task}")

class AdvisoryValidator:
    """Deterministic, rule-based gate. This is the only path an AI
    proposal can take to reach FleetServer state."""
    def validate(self,proposal:AdvisoryProposal,*,valid_vehicle_ids=None,max_fleet=15,known_missions=None,known_locations=None)->bool:
        if proposal.error or proposal.timed_out:return False
        if not 0<=proposal.confidence<=1:return False
        try:validate_schema(proposal.task,proposal.output)
        except AiValidationError:return False
        if proposal.task==AiTask.FLEET_SIZE and not 1<=proposal.output["count"]<=max_fleet:return False
        if proposal.task==AiTask.MAINTENANCE_EXPLANATION and valid_vehicle_ids is not None and proposal.output["vehicle_id"] not in valid_vehicle_ids:return False
        if proposal.task==AiTask.MISSION_SUMMARY and known_missions is not None and proposal.output["mission_id"] not in known_missions:return False
        if proposal.task==AiTask.ROUTE_RANKING and known_locations is not None:
            for route in proposal.output["ranked_routes"]:
                if not isinstance(route,list) or any(node not in known_locations for node in route):return False
        return True

class AdvisoryAiService:
    """Runs a provider, validates its proposal, falls back to a
    deterministic provider on any failure, and writes a complete,
    redacted audit record either way. Returns (proposal, valid)."""
    def __init__(self,provider:AiProvider,audit,fallback:AiProvider|None=None,timeout_s=2.0):
        self.provider=provider;self.audit=audit;self.fallback=fallback or DeterministicFakeProvider();self.timeout_s=timeout_s;self.validator=AdvisoryValidator()
    def request(self,task:AiTask,context:dict,**validate_kwargs)->tuple[AdvisoryProposal,bool]:
        proposal=self.provider.propose(task,context,self.timeout_s);valid=self.validator.validate(proposal,**validate_kwargs);source="primary"
        if not valid:
            fallback_proposal=self.fallback.propose(task,context,self.timeout_s)
            if self.validator.validate(fallback_proposal,**validate_kwargs):proposal=fallback_proposal;valid=True;source="fallback"
            else:source="rejected"
        self.audit.append("ai_proposal",{"request_id":proposal.request_id,"task":task.value,"model":proposal.model,"version":proposal.version,"prompt_version":proposal.prompt_version,"confidence":proposal.confidence,"valid":valid,"source":source,"context":redact(context),"output":redact(proposal.output)})
        return proposal,valid
