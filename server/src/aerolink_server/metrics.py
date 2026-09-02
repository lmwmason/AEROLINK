"""Deterministic, dependency-free metrics derived from the audit log plus
a small bounded rolling history of packet latency/age samples. Nothing
here holds independent state that could drift from the audit trail:
counters are recomputed from `AuditLog.entries` on every snapshot, so a
metrics snapshot and an audit export can never disagree.
"""
from __future__ import annotations
import json,math

MISSION_AUDIT_KINDS=("mission_created","operator_authorize","operator_abort_request","operator_abort_confirm","mission_completed","restart_reconciliation")

def _percentile(sorted_values:list[float],pct:float)->float:
    if not sorted_values:return 0.0
    k=(len(sorted_values)-1)*pct;f=math.floor(k);c=math.ceil(k)
    if f==c:return sorted_values[int(k)]
    return sorted_values[f]+(sorted_values[c]-sorted_values[f])*(k-f)

def histogram(values:list[float])->dict:
    if not values:return {"count":0,"min":0.0,"max":0.0,"mean":0.0,"p50":0.0,"p95":0.0,"p99":0.0}
    s=sorted(values)
    return {"count":len(s),"min":s[0],"max":s[-1],"mean":sum(s)/len(s),"p50":_percentile(s,.5),"p95":_percentile(s,.95),"p99":_percentile(s,.99)}

class MetricsRegistry:
    def __init__(self,audit,max_samples=2000):
        self.audit=audit;self.max_samples=max_samples;self.latency_samples_ms=[];self.packet_age_samples_ms=[]
    def record_node_update(self,latency_ms:float,packet_age_ms:float):
        self.latency_samples_ms.append(latency_ms);self.packet_age_samples_ms.append(packet_age_ms)
        self.latency_samples_ms=self.latency_samples_ms[-self.max_samples:];self.packet_age_samples_ms=self.packet_age_samples_ms[-self.max_samples:]
    def snapshot(self)->dict:
        kinds={};ai_outcomes={"valid":0,"invalid":0};mission_transitions={}
        for entry in self.audit.entries:
            body=json.loads(entry["body"]);kind=body["kind"];kinds[kind]=kinds.get(kind,0)+1
            if kind=="ai_proposal":ai_outcomes["valid" if body["data"]["valid"] else "invalid"]+=1
            if kind in MISSION_AUDIT_KINDS:mission_transitions[kind]=mission_transitions.get(kind,0)+1
        return {
            "audit_entry_counts":kinds,
            "ai_validation_outcomes":ai_outcomes,
            "mission_transition_counts":mission_transitions,
            "server_restart_reconciliations":kinds.get("restart_reconciliation",0),
            "maintenance_events":kinds.get("maintenance_set",0)+kinds.get("maintenance_cleared",0),
            "packet_latency_ms":histogram(self.latency_samples_ms),
            "packet_age_ms":histogram(self.packet_age_samples_ms),
        }
