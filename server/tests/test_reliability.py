"""Non-actuating reliability/scale tests (PRD "Reliability and scale
testing"). These exercise FleetServer/SimulationHttpServer directly at
server scale; the expensive real Betaflight-process restart/fault gates
already covered by server/tools/run_real_sitl.py are not duplicated here
(see docs/scale-test-report.md)."""
from __future__ import annotations
from pathlib import Path
import json,os,sqlite3,sys,tempfile,threading,time,unittest,urllib.error,urllib.request
ROOT=Path(__file__).parents[2];sys.path[:0]=[str(ROOT/"server/src"),str(ROOT/"raspberry-pi/src")]
from aerolink_server.core import FleetServer
from aerolink_server.http_api import SimulationHttpServer
from aerolink_server.security import SecurityContext
from aerolink_server.storage import SqliteRepository

class ConcurrencyTest(unittest.TestCase):
    def test_concurrent_delivery_requests_never_double_assign_a_vehicle(self):
        s=FleetServer()
        for i in range(1,16):s.ingest(i,True,90,0)
        results=[];errors=[]
        def worker():
            try:results.append(s.create_mission(5))
            except ValueError as exc:errors.append(str(exc))
        threads=[threading.Thread(target=worker) for _ in range(6)]
        for t in threads:t.start()
        for t in threads:t.join()
        assigned=[i for m in results for i in m.vehicles]
        self.assertEqual(len(assigned),len(set(assigned)),"the same vehicle must never be assigned to two concurrent missions")
        self.assertEqual(len(results)*5,len(assigned))
        self.assertGreaterEqual(len(errors),0)  # some concurrent requests may legitimately be rejected once the fleet is exhausted

    def test_duplicate_mission_submission_cannot_reuse_assigned_vehicles(self):
        s=FleetServer()
        for i in (1,2,3):s.ingest(i,True,90,0)
        first=s.create_mission(3)
        with self.assertRaises(ValueError):s.create_mission(3)  # the "double click" case: everyone is already ASSIGNED
        s.authorize(first.mission_id,"operator");s.complete_mission(first.mission_id)
        second=s.create_mission(3);self.assertNotEqual(first.mission_id,second.mission_id)

class StaleMissionReferenceTest(unittest.TestCase):
    def test_confirming_a_stale_reconciled_abort_does_not_steal_a_reassigned_vehicle(self):
        """A restart force-releases an in-flight mission's vehicles (see
        _reconcile) without deleting the mission record itself. If an
        operator later confirms that abort on the now-stale mission id
        after one of its vehicles has already been reassigned to a newer
        mission, _release must not rip the vehicle away from its current
        (newer) mission."""
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"fleet.sqlite3";repo=SqliteRepository(path);s=FleetServer(repo)
            for i in (1,2,3):s.ingest(i,True,90,0)
            old=s.create_mission(3);repo.close()
            repo=SqliteRepository(path);s=FleetServer(repo)  # restart: old -> ABORT_REQUESTED, vehicles released
            self.assertEqual(s.missions[old.mission_id].state,"ABORT_REQUESTED")
            self.assertIsNone(s.vehicles[1].mission_id)
            new=s.create_mission(3);self.assertIn(1,new.vehicles);self.assertEqual(s.vehicles[1].mission_id,new.mission_id)
            s.confirm_abort(old.mission_id,"operator")
            self.assertEqual(s.vehicles[1].mission_id,new.mission_id,"a stale confirm_abort must not steal a vehicle from a newer mission")
            self.assertEqual(s.vehicles[1].state.value,"assigned")
            repo.close()

class SoakTest(unittest.TestCase):
    def test_repeated_15_node_registration_cycles_bounded_state(self):
        s=FleetServer()
        for cycle in range(30):
            for i in range(1,16):s.ingest(i,True,70+ (i%20),cycle)
        self.assertEqual(len(s.vehicles),15)
        self.assertEqual(sum(1 for e in s.audit.entries if json.loads(e["body"])["kind"]=="telemetry"),30*15)
        self.assertTrue(s.audit.verify())

    def test_metrics_sample_window_stays_bounded_under_long_telemetry_soak(self):
        s=FleetServer()
        for i in range(3000):
            s.update_sim_node({"vehicle_id":1,"session":i,"health":"online","latency_ms":float(i%50),"packet_age_ms":1.0})
        self.assertLessEqual(len(s.metrics.latency_samples_ms),2000)
        self.assertEqual(s.metrics.snapshot()["packet_latency_ms"]["count"],2000)

    def test_repeated_restart_reconciliation_cycles(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"fleet.sqlite3"
            for cycle in range(10):
                repo=SqliteRepository(path);s=FleetServer(repo)
                self.assertEqual(s.reconciliation_state,"READY")
                for i in (1,2,3):s.ingest(i,True,90,cycle)
                m=s.create_mission(3);s.authorize(m.mission_id,"operator")
                repo.close()
            repo=SqliteRepository(path);final=FleetServer(repo)
            self.assertEqual(final.reconciliation_state,"READY");self.assertTrue(final.audit.verify())
            repo.close()

class MixedFleetHealthTest(unittest.TestCase):
    def test_mixed_healthy_degraded_maintenance_only_healthy_available_allocated(self):
        s=FleetServer()
        s.ingest(1,True,90,0);s.ingest(2,False,90,0);s.ingest(3,True,90,0)
        s.ingest(4,True,90,0);s.set_maintenance(4,"operator")
        selected=s.create_mission(2).vehicles
        self.assertEqual(selected,[1,3])  # 2 is degraded (unhealthy), 4 is in maintenance

    def test_insufficient_available_fleet_is_rejected(self):
        s=FleetServer();s.ingest(1,True,90,0)
        with self.assertRaises(ValueError):s.create_mission(2)

class DatabaseUnavailableTest(unittest.TestCase):
    def test_write_after_repository_closed_raises_instead_of_silently_dropping(self):
        with tempfile.TemporaryDirectory() as d:
            repo=SqliteRepository(Path(d)/"fleet.sqlite3");s=FleetServer(repo);repo.close()
            with self.assertRaises(sqlite3.ProgrammingError):s.ingest(1,True,90,0)

class HttpReliabilityTest(unittest.TestCase):
    def setUp(self):
        self.fleet=FleetServer();self.security=SecurityContext({});self.token=self.security.create_operator_session("admin")
        self.server=SimulationHttpServer(self.fleet,self.security,self.token);self.server.start();self.url=f"http://127.0.0.1:{self.server.port}"
    def tearDown(self):
        if self.server is not None:self.server.stop()

    def test_slow_sse_client_does_not_block_a_concurrent_fast_client(self):
        def slow_stream():
            req=urllib.request.Request(self.url+f"/api/stream?token={self.token}")
            with urllib.request.urlopen(req,timeout=10) as resp:resp.read(1)
        t=threading.Thread(target=slow_stream,daemon=True);t.start();time.sleep(.05)
        started=time.monotonic()
        req=urllib.request.Request(self.url+"/api/fleet",headers={"Authorization":f"Bearer {self.token}"})
        json.loads(urllib.request.urlopen(req,timeout=5).read())
        self.assertLess(time.monotonic()-started,1.0,"a slow streaming client must not block a concurrent fast request")

    def test_graceful_shutdown_frees_the_port_for_a_new_server(self):
        port=self.server.port;self.server.stop();self.server=None  # avoid a double-stop in tearDown
        reopened=SimulationHttpServer(self.fleet,self.security,self.token,port);reopened.start()
        try:
            req=urllib.request.Request(f"http://127.0.0.1:{port}/api/fleet",headers={"Authorization":f"Bearer {self.token}"})
            self.assertEqual(urllib.request.urlopen(req,timeout=5).status,200)
        finally:reopened.stop()

if __name__=="__main__":unittest.main()
