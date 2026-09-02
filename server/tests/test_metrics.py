from pathlib import Path
import sys,unittest
ROOT=Path(__file__).parents[2];sys.path[:0]=[str(ROOT/"server/src"),str(ROOT/"raspberry-pi/src")]
from aerolink_server.ai import AiTask
from aerolink_server.core import FleetServer
from aerolink_server.metrics import histogram

class MetricsTest(unittest.TestCase):
    def test_histogram_bounds_and_empty(self):
        self.assertEqual(histogram([])["count"], 0)
        h=histogram([1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual((h["count"], h["min"], h["max"]), (5, 1.0, 5.0));self.assertEqual(h["mean"], 3.0);self.assertEqual(h["p50"], 3.0)

    def test_snapshot_tracks_missions_ai_maintenance_and_latency(self):
        s=FleetServer()
        for i in (1, 2, 3): s.ingest(i, True, 90, 0)
        m=s.create_mission(3);s.authorize(m.mission_id, "operator")
        s.update_sim_node({"vehicle_id": 1, "session": 5, "health": "online", "latency_ms": 12.5, "packet_age_ms": 3.0})
        s.set_maintenance(2 if 2 not in m.vehicles else 4, "operator")
        s.advise_fleet_size(2.0)
        snap=s.metrics.snapshot()
        self.assertEqual(snap["mission_transition_counts"].get("mission_created"), 1)
        self.assertEqual(snap["mission_transition_counts"].get("operator_authorize"), 1)
        self.assertEqual(snap["ai_validation_outcomes"]["valid"], 1)
        self.assertEqual(snap["maintenance_events"], 1)
        self.assertEqual(snap["packet_latency_ms"]["count"], 1);self.assertEqual(snap["packet_latency_ms"]["max"], 12.5)
        self.assertEqual(snap["audit_entry_counts"]["telemetry"], 3)

    def test_snapshot_never_diverges_from_audit_export(self):
        s=FleetServer();s.ingest(1, True, 90, 0)
        self.assertEqual(sum(s.metrics.snapshot()["audit_entry_counts"].values()), s.audit.export()["count"])

if __name__ == "__main__": unittest.main()
