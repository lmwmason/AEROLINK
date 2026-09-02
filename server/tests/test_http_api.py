import json
from pathlib import Path
import sys
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "server/src"))

from aerolink_server.core import FleetServer
from aerolink_server.http_api import SimulationHttpServer
from aerolink_server.security import SecurityContext,node_headers


class SimulationHttpApiTest(unittest.TestCase):
    def setUp(self):
        self.fleet = FleetServer()
        self.key=b"node-04-test-key-0000000000000000";self.security=SecurityContext({4:self.key})
        self.admin_token=self.security.create_operator_session("admin");self.viewer_token=self.security.create_operator_session("viewer")
        self.server = SimulationHttpServer(self.fleet,self.security,self.admin_token)
        self.server.start()
        self.url = f"http://127.0.0.1:{self.server.port}"

    def tearDown(self):
        self.server.stop()

    def post(self, path, body, key=None):
        data=json.dumps(body,separators=(",",":"),sort_keys=True).encode();headers={"Content-Type":"application/json",**node_headers(body["vehicle_id"],key or self.key,"POST",path,data)}
        request = urllib.request.Request(self.url + path, data=data, headers=headers)
        return urllib.request.urlopen(request).read()

    def get(self, path, token=None):
        request=urllib.request.Request(self.url+path,headers={"Authorization":f"Bearer {token or self.admin_token}"})
        return json.loads(urllib.request.urlopen(request).read())

    def call(self, path, body, token=None):
        data=json.dumps(body).encode();request=urllib.request.Request(self.url+path,data=data,headers={"Authorization":f"Bearer {token or self.admin_token}","Content-Type":"application/json"})
        return json.loads(urllib.request.urlopen(request).read())

    def test_dashboard_lists_all_nodes_and_transport_fields(self):
        self.post("/api/register", {"vehicle_id": 4, "session": 99, "health": "online", "packet_age_ms": 7, "faults": ["test"]})
        result=self.get("/api/fleet")
        self.assertEqual(len(result["vehicles"]), 15)
        node = result["vehicles"][3]
        self.assertEqual((node["vehicle_id"], node["session"], node["packet_age_ms"]), (4, 99, 7.0))
        request=urllib.request.Request(self.url+"/",headers={"Authorization":f"Bearer {self.admin_token}"});page=urllib.request.urlopen(request).read().decode()
        self.assertIn("non-actuating transport validation dashboard", page)
        # Every node state must map to a distinct badge CSS class, and the
        # page's JS must actually apply it (regression: an earlier version
        # defined the CSS classes and a STATE_LABEL map but never wired
        # either into the rendered badge, so every node looked identical).
        from aerolink_server.http_api import STATE_LABEL
        classes={cls for _,cls in STATE_LABEL.values()}
        self.assertEqual(classes,{"ok","assigned","degraded","maintenance","offline"})
        for cls in classes:self.assertIn(f".{cls}{{background:", page)
        self.assertIn("STATE_LABEL[v.state]", page)
        self.assertIn(json.dumps(STATE_LABEL), page)

    def test_mutating_ingest_requires_configured_server_token(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("/api/telemetry", {"vehicle_id": 4, "session": 1, "health": "online"}, b"wrong-key-00000000000000000000000")
        self.assertEqual(error.exception.code, 400)
        error.exception.close()

    def test_mission_authorize_abort_workflow_and_node_detail(self):
        self.post("/api/register", {"vehicle_id": 4, "session": 1, "health": "online"})
        for i in (1, 2, 3): self.fleet.ingest(i, True, 90, 0)
        created=self.call("/api/missions", {"count": 3});mission_id=created["mission_id"];self.assertEqual(created["state"], "PLANNED")
        authorized=self.call(f"/api/missions/{mission_id}/authorize", {"operator": "alice"});self.assertEqual(authorized["state"], "AUTHORIZED")
        with self.assertRaises(urllib.error.HTTPError) as error:self.call(f"/api/missions/{mission_id}/authorize", {"operator": "alice"}, token=self.viewer_token)
        self.assertEqual(error.exception.code, 403); error.exception.close()
        requested=self.call(f"/api/missions/{mission_id}/abort-request", {"operator": "alice"});self.assertEqual(requested["state"], "ABORT_REQUESTED")
        confirmed=self.call(f"/api/missions/{mission_id}/abort-confirm", {"operator": "alice"});self.assertEqual(confirmed["state"], "ABORTED")
        detail=self.get("/api/vehicles/1");self.assertEqual(detail["vehicle"]["vehicle_id"], 1);self.assertIsNone(detail["vehicle"]["mission_id"])
        self.assertGreater(len(detail["events"]), 0)
        history=self.get("/api/missions");self.assertEqual(len(history["missions"]), 1)
        export=self.get("/api/audit/export");self.assertTrue(export["chain_valid"])

    def test_maintenance_requires_admin_role_and_blocks_allocation(self):
        self.fleet.ingest(5, True, 90, 0)
        with self.assertRaises(urllib.error.HTTPError) as error:self.call("/api/vehicles/5/maintenance", {"operator": "alice"}, token=self.viewer_token)
        self.assertEqual(error.exception.code, 403); error.exception.close()
        result=self.call("/api/vehicles/5/maintenance", {"operator": "alice", "note": "battery swap"});self.assertEqual(result["state"], "maintenance")
        with self.assertRaises(urllib.error.HTTPError) as error:self.call("/api/missions", {"count": 15})
        self.assertEqual(error.exception.code, 400); error.exception.close()
        cleared=self.call("/api/vehicles/5/maintenance", {"operator": "alice", "action": "clear"});self.assertEqual(cleared["state"], "offline")

    def test_ai_fleet_size_endpoint_is_advisory_only(self):
        result=self.call("/api/ai/fleet-size", {"estimated_kg": 2.0})
        self.assertTrue(result["valid"]);self.assertEqual(result["model"], "deterministic-fake")
        self.assertEqual(self.fleet.dashboard()["missions"], [], "an advisory call must never create a mission")

    def test_metrics_endpoint_reflects_ai_and_node_activity(self):
        self.post("/api/register", {"vehicle_id": 4, "session": 1, "health": "online", "latency_ms": 9.0, "packet_age_ms": 1.0})
        self.call("/api/ai/fleet-size", {"estimated_kg": 1.0})
        snap=self.get("/api/metrics")
        self.assertEqual(snap["ai_validation_outcomes"]["valid"], 1)
        self.assertEqual(snap["packet_latency_ms"]["count"], 1)

    def test_sse_stream_emits_json_dashboard_events(self):
        request=urllib.request.Request(self.url+f"/api/stream?token={self.admin_token}")
        with urllib.request.urlopen(request, timeout=5) as response:
            line=response.readline().decode()
        self.assertTrue(line.startswith("data: "))
        payload=json.loads(line[len("data: "):]);self.assertIn("vehicles", payload)


if __name__ == "__main__":
    unittest.main()
