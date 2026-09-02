#!/usr/bin/env python3
"""Bounded, deterministic server-side reliability soak with measured
resource evidence. Not a real-SITL/UART soak (see server/tools/run_real_sitl.py
for that, expensive-to-run gate); this exercises FleetServer + a real
SQLite repository + SimulationHttpServer at server scale: repeated
15-node registration cycles, mission create/authorize/complete cycles,
restart-reconciliation cycles, and a burst of concurrent HTTP requests
against a running server. Reports CPU, RSS, open file descriptors,
mission-queue depth, event-loop (request) latency, database write
latency, and dropped/rejected message counts.
"""
from __future__ import annotations
import argparse,json,os,resource,sys,tempfile,threading,time,urllib.error,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"server/src"),str(ROOT/"raspberry-pi/src")]
from aerolink_server.core import FleetServer
from aerolink_server.http_api import SimulationHttpServer
from aerolink_server.security import SecurityContext
from aerolink_server.storage import SqliteRepository

def fd_count():
    try:return len(os.listdir(f"/proc/{os.getpid()}/fd"))
    except OSError:return -1  # not on Linux; not fatal

def rss_kb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registration-cycles",type=int,default=200)
    p.add_argument("--mission-cycles",type=int,default=50)
    p.add_argument("--restart-cycles",type=int,default=20)
    p.add_argument("--http-requests",type=int,default=100)
    p.add_argument("--http-concurrency",type=int,default=10)
    p.add_argument("--artifacts",type=Path,default=Path(os.environ.get("AEROLINK_ARTIFACTS",ROOT/"artifacts")))
    a=p.parse_args()
    a.artifacts.mkdir(parents=True,exist_ok=True)
    started_rss=rss_kb();started_fd=fd_count();dropped=0

    # 1) Repeated 15-node registration + mixed-health telemetry cycles.
    s=FleetServer()
    for cycle in range(a.registration_cycles):
        for i in range(1,16):s.ingest(i,i%7!=0,90-(i%40),cycle)
    registration_rss=rss_kb()

    # 2) Repeated mission create/authorize/complete cycles (queue depth = pending missions).
    max_queue_depth=0
    for _ in range(a.mission_cycles):
        for i in range(1,16):
            if s.vehicles[i].state.value not in ("available","assigned"):s.ingest(i,True,90,0)
        try:
            m=s.create_mission(3);s.authorize(m.mission_id,"soak-operator")
            max_queue_depth=max(max_queue_depth,sum(1 for mm in s.missions.values() if mm.state in ("PLANNED","AUTHORIZED")))
            s.complete_mission(m.mission_id)
        except ValueError:dropped+=1
    mission_rss=rss_kb()

    # 3) Repeated server-restart-reconciliation cycles against a real SQLite file.
    db_write_latencies_ms=[]
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/"soak.sqlite3"
        for cycle in range(a.restart_cycles):
            repo=SqliteRepository(path);server=FleetServer(repo)
            for i in (1,2,3):server.ingest(i,True,90,cycle)
            started=time.monotonic();m=server.create_mission(3);db_write_latencies_ms.append((time.monotonic()-started)*1000)
            server.authorize(m.mission_id,"soak-operator");repo.close()
        repo=SqliteRepository(path);final=FleetServer(repo)
        reconciliation_ok=final.reconciliation_state=="READY" and final.audit.verify()
        repo.close()
    restart_rss=rss_kb()

    # 4) Concurrent HTTP burst against a live server (event-loop/request latency).
    fleet=FleetServer();security=SecurityContext({});token=security.create_operator_session("admin")
    http=SimulationHttpServer(fleet,security,token);http.start();url=f"http://127.0.0.1:{http.port}/api/fleet"
    latencies_ms=[];http_errors=0;lock=threading.Lock()
    def request():
        nonlocal http_errors
        started=time.monotonic()
        try:
            req=urllib.request.Request(url,headers={"Authorization":f"Bearer {token}"});urllib.request.urlopen(req,timeout=5).read()
            with lock:latencies_ms.append((time.monotonic()-started)*1000)
        except urllib.error.URLError:
            with lock:http_errors+=1
    remaining=a.http_requests
    while remaining>0:
        batch=min(a.http_concurrency,remaining);threads=[threading.Thread(target=request) for _ in range(batch)]
        for t in threads:t.start()
        for t in threads:t.join()
        remaining-=batch
    http.stop();final_fd=fd_count();final_rss=rss_kb()

    def histogram(values):
        if not values:return {"count":0,"min":0,"max":0,"mean":0}
        s=sorted(values);return {"count":len(s),"min":s[0],"max":s[-1],"mean":sum(s)/len(s)}

    result={
        "schema_version":1,"software_only":True,"control_path_connected":False,
        "registration_cycles":a.registration_cycles,"mission_cycles":a.mission_cycles,"restart_cycles":a.restart_cycles,
        "resource":{
            "rss_kb_start":started_rss,"rss_kb_after_registration":registration_rss,"rss_kb_after_missions":mission_rss,
            "rss_kb_after_restarts":restart_rss,"rss_kb_end":final_rss,"rss_kb_growth":final_rss-started_rss,
            "fd_count_start":started_fd,"fd_count_end":final_fd,"fd_growth":(final_fd-started_fd) if started_fd>=0 and final_fd>=0 else "unavailable",
        },
        "max_mission_queue_depth":max_queue_depth,
        "dropped_or_rejected_missions":dropped,
        "db_write_latency_ms":histogram(db_write_latencies_ms),
        "reconciliation_ok_after_restart_cycles":reconciliation_ok,
        "http_request_latency_ms":histogram(latencies_ms),
        "http_errors":http_errors,
    }
    out=a.artifacts/"reliability-soak.json";out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,sort_keys=True))
    return 0 if reconciliation_ok and http_errors==0 else 1

if __name__=="__main__":raise SystemExit(main())
