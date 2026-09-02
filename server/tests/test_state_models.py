import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).parents[2];sys.path[:0]=[str(ROOT/"server/src"),str(ROOT/"raspberry-pi/src")]
from aerolink_pi.service import MissionState,TRANSITIONS
from aerolink_server.core import MISSION_TRANSITIONS

class StateModelTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.spec=json.loads((ROOT/"schemas/state-machines.json").read_text())["machines"]
 def test_all_transition_tables_are_total_and_targets_exist(self):
  for name,machine in self.spec.items():
   states=set(machine["states"]);self.assertEqual(states,set(machine["transitions"]),name);self.assertIn(machine["initial"],states)
   for source,targets in machine["transitions"].items():self.assertTrue(set(targets)<=states,(name,source))
 def test_forbidden_edges_unreachable_in_one_event(self):
  for source,target in self.spec["fc"]["direct_forbidden"]:self.assertNotIn(target,self.spec["fc"]["transitions"][source])
 def test_pi_implementation_matches_model(self):
  expected={state.value:{target.value for target in targets} for state,targets in TRANSITIONS.items()}
  actual={state:set(targets) for state,targets in self.spec["pi_mission"]["transitions"].items()}
  self.assertEqual(expected,actual)
 def test_server_mission_implementation_matches_model(self):
  actual={state:set(targets) for state,targets in self.spec["server_mission"]["transitions"].items()}
  self.assertEqual(MISSION_TRANSITIONS,actual)
 def test_restart_requires_reconciliation_and_no_resume_edge(self):
  restart=self.spec["server_reconciliation"]["transitions"]
  self.assertEqual(restart["RECOVERING"],["RECONCILING"]);self.assertNotIn("READY",restart["STOPPED"])
 def test_ai_is_absent_from_executable_machine_events(self):
  encoded=json.dumps(self.spec)
  for forbidden in ("AI_COMMAND","ARM","MOTOR","THROTTLE","PAYLOAD_ACTIVATE"):self.assertNotIn(forbidden,encoded)

if __name__=="__main__":unittest.main()
