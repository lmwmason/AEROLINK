from pathlib import Path
import sys,tempfile,unittest
ROOT=Path(__file__).parents[2];sys.path[:0]=[str(ROOT/"server/src"),str(ROOT/"raspberry-pi/src")]
from aerolink_server.core import FleetServer
from aerolink_server.storage import SqliteRepository

class StorageTest(unittest.TestCase):
 def test_migration_is_idempotent_and_versioned(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"fleet.sqlite3"
   repo=SqliteRepository(path);self.assertEqual(repo.schema_version(),5);repo.close()
   reopened=SqliteRepository(path);self.assertEqual(reopened.schema_version(),5);reopened.close()
 def test_restart_reconciliation_cannot_resume_old_mission_or_epoch(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"fleet.sqlite3";repo=SqliteRepository(path)
   s=FleetServer(repo);self.assertEqual(s.reconciliation_state,"READY")
   for i in (1,2,3):s.ingest(i,True,90,0)
   m=s.create_mission(3);s.authorize(m.mission_id,"operator");old_epoch=s.epoch;repo.close()
   repo2=SqliteRepository(path);recovered=FleetServer(repo2)
   self.assertEqual(recovered.reconciliation_state,"READY")
   self.assertEqual(recovered.epoch,old_epoch,"restart must not replay/reuse the old epoch on the next mission")
   self.assertEqual(recovered.missions[m.mission_id].state,"ABORT_REQUESTED","an in-flight mission cannot resume after restart")
   self.assertIsNone(recovered.vehicles[1].mission_id)
   self.assertEqual(recovered.vehicles[1].state.value,"available")
   kinds={e["kind"] for e in [__import__("json").loads(x["body"]) for x in recovered.audit.entries]}
   self.assertIn("restart_reconciliation",kinds);self.assertIn("server_ready",kinds)
   self.assertTrue(recovered.audit.verify())
   recovered.ingest(4,True,90,0);next_mission=recovered.create_mission(1)
   self.assertEqual(next_mission.epoch,old_epoch+1,"the next mission must use a fresh epoch, never the recovered one")
   repo2.close()
 def test_completed_mission_frees_corridor_for_new_mission(self):
  with tempfile.TemporaryDirectory() as d:
   repo=SqliteRepository(Path(d)/"fleet.sqlite3");s=FleetServer(repo)
   for i in (1,2,3,4,5,6):s.ingest(i,True,90,0)
   m1=s.create_mission(3)
   with self.assertRaises(ValueError):s.create_mission(3)
   s.authorize(m1.mission_id,"operator");s.complete_mission(m1.mission_id)
   m2=s.create_mission(3);self.assertNotEqual(m1.mission_id,m2.mission_id);repo.close()
 def test_maintenance_blocks_allocation_and_rejects_assigned_vehicle(self):
  s=FleetServer();s.ingest(1,True,90,0);s.set_maintenance(1,"operator")
  self.assertEqual(s.vehicles[1].state.value,"maintenance")
  with self.assertRaises(ValueError):s.create_mission(1)
  s.clear_maintenance(1,"operator");s.ingest(1,True,90,0);s.create_mission(1)
  m=list(s.missions.values())[0]
  with self.assertRaises(ValueError):s.set_maintenance(m.vehicles[0],"operator")

if __name__=="__main__":unittest.main()
