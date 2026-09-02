from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).parents[1]/"src"))
from aerolink_pi.fleet import FleetPacket
from aerolink_pi.service import FakeFc,MissionState,VehicleService

class VehicleServiceTest(unittest.TestCase):
 def setUp(self):self.key=b"key";self.fc=FakeFc(4);self.node=VehicleService(4,"server",self.key,self.fc);self.node.connect_fc(0)
 def p(self,seq,kind,payload,issued=10,epoch=1,ttl=100):return FleetPacket("server",4,epoch,seq,issued,ttl,kind,payload).sign(self.key)
 def test_fake_server_assignment_and_bounded_forward(self):
  self.node.receive_server(self.p(1,"ASSIGN",{"mission_id":"m1"}),10);self.node.tick(10);self.assertEqual(self.node.state,MissionState.AUTHORIZED)
  self.node.receive_server(self.p(2,"TRANSITION",{"state":"LAUNCH"}),10);self.node.tick(10)
  self.node.receive_server(self.p(3,"SETPOINT",{"roll_cd":10,"pitch_cd":-10,"yaw_rate_cds":20,"vertical_rate_cms":2}),10);self.node.tick(10)
  self.assertEqual(self.fc.frames[-1].message_type.name,"SET_STABILIZED_SETPOINT")
 def test_wrong_server_stale_replay_and_bad_bounds(self):
  bad=FleetPacket("attacker",4,1,1,10,100,"PING",{}).sign(self.key)
  with self.assertRaises(ValueError):self.node.receive_server(bad,10)
  with self.assertRaises(ValueError):self.node.receive_server(self.p(1,"PING",{},issued=0),1000)
  self.node.receive_server(self.p(1,"ASSIGN",{"mission_id":"m"}),10)
  with self.assertRaises(ValueError):self.node.receive_server(self.p(1,"PING",{}),10)
 def test_reconnect_new_session_drops_queue(self):
  self.node.receive_server(self.p(1,"ASSIGN",{"mission_id":"m"}),10);old=self.node.session;self.node.connect_fc(11)
  self.assertNotEqual(old,self.node.session);self.assertEqual(len(self.node.queue),0);self.assertEqual(self.fc.state,"STANDBY")
 def test_uart_timeout_aborts(self):
  self.node.tick(301);self.assertEqual(self.node.state,MissionState.ABORT)
