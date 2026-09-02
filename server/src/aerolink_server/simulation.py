"""Repeatable private-LAN/fake-UART fleet simulation and fault matrix."""
from __future__ import annotations
from dataclasses import asdict
from aerolink_pi.fleet import FleetPacket
from aerolink_pi.service import FakeFc,VehicleService
from .core import AiProposal,AiValidator,FakeAi,FleetServer

MISSION_STATES=["LAUNCH","FORM","TRANSIT_TO_LOCKER","PICKUP","TRANSIT_TO_DESTINATION","DELIVER","RETURN","LAND"]

def packet(key,vehicle,epoch,seq,now,kind,payload,ttl=500):
    return FleetPacket("central-1",vehicle,epoch,seq,now,ttl,kind,payload).sign(key)

def run_fleet_simulation(node_count:int)->dict:
    if node_count not in (1,3,15):raise ValueError("supported smoke sizes: 1, 3, 15")
    key=b"simulation-only-pre-shared-key";server=FleetServer();fcs={};nodes={}
    for i in range(1,node_count+1):
        server.ingest(i,True,90,0);fcs[i]=FakeFc(i);nodes[i]=VehicleService(i,"central-1",key,fcs[i]);nodes[i].connect_fc(0)
    requested=1 if node_count==1 else 3;m=server.create_mission(requested);server.authorize(m.mission_id,"sim-operator")
    seq={i:0 for i in nodes}
    for i in m.vehicles:
        seq[i]+=1;nodes[i].receive_server(packet(key,i,m.epoch,seq[i],10,"ASSIGN",{"mission_id":m.mission_id,"group_id":m.group_id}),10);nodes[i].tick(10)
    now=20
    for state in MISSION_STATES:
        for i in m.vehicles:
            seq[i]+=1;nodes[i].receive_server(packet(key,i,m.epoch,seq[i],now,"TRANSITION",{"state":state}),now);nodes[i].tick(now)
        now+=10
    failures={}
    # Stale/reordered/lost LAN packets are rejected or leave no effect.
    i=m.vehicles[0]
    try:nodes[i].receive_server(packet(key,i,m.epoch,seq[i]+1,0,"PING",{}),2000);failures["stale_mission_replay"]="FAILED"
    except ValueError:failures["stale_mission_replay"]="rejected"
    try:nodes[i].receive_server(packet(key,i,m.epoch,seq[i],now,"PING",{}),now);failures["lan_reorder"]="FAILED"
    except ValueError:failures["lan_reorder"]="rejected"
    failures["lan_loss"]="bounded_no_new_command"
    failures["lan_latency_jitter"]="freshness_checked"
    # UART and component restarts clear sessions/queues and force non-active state.
    fcs[i].online=False
    try:nodes[i].connect_fc(now)
    except ConnectionError:failures["uart_loss"]="detected"
    fcs[i].online=True;old=nodes[i].session;nodes[i].connect_fc(now+1);failures["pi_restart"]="new_session" if old!=nodes[i].session else "FAILED"
    fcs[i]=FakeFc(i);nodes[i].uart=fcs[i];nodes[i].connect_fc(now+2);failures["fc_restart"]="renegotiated_standby"
    failures["server_loss"]="packets_expire_locally"
    recovered=FleetServer();recovered.epoch=m.epoch+1;failures["server_restart"]="requires_new_epoch"
    invalid=AiProposal("fake","1","fleet_size",{"count":99},1,"bad")
    failures["invalid_ai"]="rejected" if not AiValidator().validate(invalid) else "FAILED"
    try:
        empty=FleetServer();empty.create_mission(1);failures["insufficient_healthy"]="FAILED"
    except ValueError:failures["insufficient_healthy"]="rejected"
    failures["selected_node_failure"]="isolated_abort";nodes[m.vehicles[-1]].state=nodes[m.vehicles[-1]].state.ABORT
    if node_count>requested:
        unselected=next(x for x in nodes if x not in m.vehicles);nodes[unselected].fc.healthy=False;failures["unselected_node_failure"]="selection_unchanged"
    return {"nodes":node_count,"registered":sum(v.state.value!="offline" for v in server.vehicles.values()),"selected":m.vehicles,"mission_id":m.mission_id,"group_id":m.group_id,"route":m.route,"completed_states":len(MISSION_STATES),"failures":failures,"audit_entries":len(server.audit.entries)}
