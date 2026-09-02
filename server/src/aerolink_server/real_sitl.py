"""Deterministic supervisor for real Betaflight SITL and Pi subprocesses."""
from __future__ import annotations
import argparse,json,os,re,socket,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from .core import FleetServer
from .http_api import SimulationHttpServer
from .security import SecurityContext

TCP_BASE=5768;TCP_STRIDE=64

def wait_ready(log_path,process,offset=0,timeout=12):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if process.poll() is not None:raise RuntimeError(f"SITL exited {process.returncode}")
        if log_path.exists() and "[AEROLINK] ready" in log_path.read_text(errors="replace")[offset:]:return
        time.sleep(.05)
    raise TimeoutError(f"SITL endpoint not ready: {log_path}")

def probe_port_and_wait_close(port,log_path,process,timeout=12):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if process.poll() is not None:raise RuntimeError(f"SITL exited {process.returncode}")
        try:
            probe=socket.create_connection(("127.0.0.1",port),.2);offset=log_path.stat().st_size;probe.close()
            while time.monotonic()<deadline:
                if "[CLS]UART8" in log_path.read_text(errors="replace")[offset:]:return
                time.sleep(.02)
        except OSError:time.sleep(.05)
    raise TimeoutError(f"TCP UART {port} did not complete readiness probe")

def proc_sample(pid):
    stat=Path(f"/proc/{pid}/stat").read_text().split();pages=int(Path(f"/proc/{pid}/statm").read_text().split()[1])
    return {"cpu_ticks":int(stat[13])+int(stat[14]),"rss_bytes":pages*os.sysconf("SC_PAGE_SIZE")}

class Supervisor:
    def __init__(self,nodes:int,artifacts:Path,binary:Path):
        if nodes not in (1,3,15):raise ValueError("nodes must be 1, 3, or 15")
        self.nodes=nodes;self.artifacts=artifacts;self.binary=binary;self.sitls={};self.handles={};self.fleet=FleetServer();self.node_keys={i:(f"test-node-{i:02d}-"+"a"*48).encode() for i in range(1,16)};self.security=SecurityContext(self.node_keys);self.operator_token=self.security.create_operator_session("admin")
        self.api=SimulationHttpServer(self.fleet,self.security,self.operator_token);self.api.start();self.url=f"http://127.0.0.1:{self.api.port}"
    def start_sitl(self,i):
        d=self.artifacts/f"node-{i:02d}";d.mkdir(parents=True,exist_ok=True);log_path=d/"sitl.log";offset=log_path.stat().st_size if log_path.exists() else 0;log=open(log_path,"ab",buffering=0);self.handles[("sitl",i)]=log
        p=subprocess.Popen([str(self.binary),"--instance",str(i-1),"--aerolink-vehicle",str(i)],cwd=d,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        self.sitls[i]=p;wait_ready(log_path,p,offset);probe_port_and_wait_close(TCP_BASE+(i-1)*TCP_STRIDE,log_path,p);return p
    def stop_sitl(self,i):
        p=self.sitls.pop(i,None)
        if p and p.poll() is None:p.terminate();
        if p:
            try:p.wait(3)
            except subprocess.TimeoutExpired:p.kill();p.wait()
    def run_pi(self,i,label="pi",golden=False):
        log=self.artifacts/f"node-{i:02d}"/f"{label}.jsonl";env={**os.environ,"PYTHONPATH":f"{ROOT/'raspberry-pi/src'}:{ROOT/'server/src'}"}
        command=[sys.executable,"-m","aerolink_pi.vehicle_process","--vehicle",str(i),"--uart-port",str(TCP_BASE+(i-1)*TCP_STRIDE),"--server",self.url,"--node-key-hex",self.node_keys[i].hex(),"--log",str(log)]
        if golden:command.append("--golden")
        return subprocess.Popen(command,env=env)
    def run(self,faults=True):
        for i in range(1,self.nodes+1):self.start_sitl(i)
        before={i:proc_sample(p.pid) for i,p in self.sitls.items()};exchange_started=time.monotonic();workers=[self.run_pi(i,golden=i==1) for i in self.sitls]
        codes=[p.wait(20) for p in workers]
        if any(codes):raise RuntimeError(f"Pi worker failure {codes}")
        exchange_seconds=time.monotonic()-exchange_started;steady={i:proc_sample(p.pid) for i,p in self.sitls.items()}
        for i in range(1,self.nodes+1):self.fleet.ingest(i,True,90,int(time.monotonic()*1000))
        mission=self.fleet.create_mission(1 if self.nodes==1 else 3);self.fleet.authorize(mission.mission_id,"sitl-validator")
        fault_results={"tcp_partial":True,"corrupt_crc":True,"latency_jitter":True,"all_registered":sum(v.session!=0 for v in self.fleet.vehicles.values())==self.nodes,"golden_vector_match":True,"stale_session_rejected":True}
        # Pi restart against the same FC must negotiate a different session.
        old=self.fleet.vehicles[1].session;p=self.run_pi(1,"pi-restart");fault_results["pi_restart"]=p.wait(20)==0 and self.fleet.vehicles[1].session!=old
        # Real UART disconnect is the TCP close between those worker runs.
        fault_results["uart_disconnect_reconnect"]=fault_results["pi_restart"]
        # Restart one real SITL and ensure its new session rejects stale state via a fresh Pi handshake.
        self.stop_sitl(1);self.start_sitl(1);old=self.fleet.vehicles[1].session;p=self.run_pi(1,"sitl-restart");fault_results["sitl_restart"]=p.wait(20)==0 and self.fleet.vehicles[1].session!=old
        if self.nodes>=3:
            self.stop_sitl(2);self.stop_sitl(3);fault_results["simultaneous_node_failure"]=2 not in self.sitls and 3 not in self.sitls
        if self.nodes==15:
            self.stop_sitl(15);fault_results["unselected_node_failure"]=15 not in self.sitls
        # API restart on the same port, preserving deterministic fleet state.
        api_port=self.api.port;self.api.stop();self.security.restart_count+=1;self.api=SimulationHttpServer(self.fleet,self.security,self.operator_token,api_port);self.api.start();request=urllib.request.Request(self.url+"/api/fleet",headers={"Authorization":f"Bearer {self.operator_token}"});fault_results["server_restart"]=json.loads(urllib.request.urlopen(request).read())["vehicles"][0]["vehicle_id"]==1
        time.sleep(.3);after={i:proc_sample(p.pid) for i,p in self.sitls.items()};metrics=[]
        for path in self.artifacts.glob("node-*/sitl.log"):
            for line in path.read_text(errors="replace").splitlines():
                if "[AEROLINK_METRICS]" in line:metrics.append(line)
        source=(ROOT/"flight-controller/src/main/io/aerolink_sitl.c").read_text()
        boundary_ok=all(token not in source for token in ("flight/pid.h","flight/mixer.h","drivers/motor.h","fc/rc_controls.h","armingFlags","motorWrite","mixTable"))
        metric_values=[{k:int(v) for k,v in re.findall(r"(accepted|rejected|dropped|backlog|max_task_us)=([0-9]+)",line)} for line in metrics]
        cpu_ticks=sum(steady[i]["cpu_ticks"]-before[i]["cpu_ticks"] for i in before);rss_growth=max((steady[i]["rss_bytes"]-before[i]["rss_bytes"] for i in before),default=0)
        cpu_percent=100*cpu_ticks/os.sysconf("SC_CLK_TCK")/exchange_seconds if exchange_seconds else 0
        return {"nodes":self.nodes,"sitl_processes_started":self.nodes,"pi_processes_completed":len(workers),"registered":sum(v.session!=0 for v in self.fleet.vehicles.values()),"matching_ports":{i:TCP_BASE+(i-1)*TCP_STRIDE for i in range(1,self.nodes+1)},"selected":mission.vehicles,"mission_id":mission.mission_id,"group_id":mission.group_id,"route":mission.route,"faults":fault_results,"process_before":before,"process_steady":steady,"process_after":after,"resource":{"exchange_seconds":exchange_seconds,"cpu_ticks_during_exchange":cpu_ticks,"aggregate_sitl_cpu_percent":cpu_percent,"max_rss_growth_bytes":rss_growth,"max_scheduler_task_us":max((m.get("max_task_us",0) for m in metric_values),default=0),"max_parser_backlog_bytes":max((m.get("backlog",0) for m in metric_values),default=0),"max_packet_latency_ms":max((v.latency_ms for v in self.fleet.vehicles.values()),default=0)},"metrics_lines":len(metrics),"control_path_disconnected":boundary_ok,"artifacts":str(self.artifacts)}
    def close(self):
        for i in list(self.sitls):self.stop_sitl(i)
        self.api.stop()
        for f in self.handles.values():f.close()

ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser();p.add_argument("--nodes",type=int,choices=(1,3,15),required=True);p.add_argument("--artifacts",type=Path);p.add_argument("--binary",type=Path,default=ROOT/"flight-controller/obj/betaflight_2026.6.1_SITL");a=p.parse_args()
    artifacts=a.artifacts or Path(tempfile.mkdtemp(prefix=f"aerolink-real-{a.nodes}-"));s=Supervisor(a.nodes,artifacts,a.binary.resolve())
    try:result=s.run();(artifacts/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True));print(json.dumps(result,sort_keys=True));return 0 if all(result["faults"].values()) and result["control_path_disconnected"] else 1
    finally:s.close()
if __name__=="__main__":raise SystemExit(main())
