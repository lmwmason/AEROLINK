from pathlib import Path
import sys,unittest
ROOT=Path(__file__).parents[2];sys.path[:0]=[str(ROOT/"server/src"),str(ROOT/"raspberry-pi/src")]
from aerolink_server.core import *
from aerolink_server.simulation import run_fleet_simulation

class ServerTest(unittest.TestCase):
 def test_registry_allocator_route_authorization_and_audit(self):
  s=FleetServer();self.assertEqual(len(s.vehicles),15)
  for i in (1,2,3,4):s.ingest(i,True,80,10)
  m=s.create_mission(3);self.assertEqual(m.vehicles,[1,2,3]);self.assertEqual(m.route[0],"HOME");self.assertEqual(m.route[-1],"HOME")
  with self.assertRaises(PermissionError):s.authorize(m.mission_id,"")
  s.authorize(m.mission_id,"operator");s.request_abort(m.mission_id,"operator");self.assertEqual(m.state,"ABORT_REQUESTED")
  s.confirm_abort(m.mission_id,"operator");self.assertEqual(m.state,"ABORTED");self.assertGreater(len(s.audit.entries),0)
  self.assertIsNone(s.vehicles[1].mission_id);self.assertEqual(s.vehicles[1].state,FleetState.AVAILABLE)
  with self.assertRaises(ValueError):s.request_abort(m.mission_id,"operator")
 def test_ai_is_advisory_and_invalid_rejected(self):
  p=FakeAi().recommend_count(2.2);self.assertTrue(AiValidator().validate(p))
  self.assertFalse(AiValidator().validate(AiProposal("x","1","fleet_size",{"count":0},1,"x")))
  self.assertFalse(hasattr(FakeAi(),"arm"));self.assertFalse(hasattr(FakeAi(),"setpoint"))
 def test_insufficient_and_maintenance(self):
  s=FleetServer();s.ingest(1,True,90,0);s.vehicles[1].state=FleetState.MAINTENANCE
  with self.assertRaises(ValueError):s.create_mission(1)
 def test_dashboard_schema(self):
  d=FleetServer().dashboard();self.assertEqual(len(d["vehicles"]),15);self.assertIn("missions",d)

class SimulationTest(unittest.TestCase):
 def test_1_3_15(self):
  for count in (1,3,15):
   with self.subTest(count=count):
    r=run_fleet_simulation(count);self.assertEqual(r["registered"],count);self.assertEqual(len(r["selected"]),1 if count==1 else 3);self.assertNotIn("FAILED",r["failures"].values())

if __name__=="__main__":unittest.main()
