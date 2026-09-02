import json,random,sys,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).parents[2];sys.path.insert(0,str(ROOT/"raspberry-pi/src"))
from aerolink_pi.generated_protocol import UART_MAX_FRAME,UART_MAX_PAYLOAD,UART_MESSAGE_TYPES
from aerolink_pi.protocol import *
from aerolink_pi.fleet import FleetPacket,FleetValidator
from aerolink_pi.service import FakeFc,VehicleService

class ProtocolPropertyTest(unittest.TestCase):
 def test_seeded_roundtrip_endian_and_boundaries(self):
  rng=random.Random(0xA3E011);bounds=[-3000,3000,-18000,18000,-300,300]
  for sequence in [0,1,0x7fffffff,0xfffffffe,0xffffffff]+[rng.randrange(2**32) for _ in range(500)]:
   vehicle=rng.randint(1,15);payload=rng.randbytes(rng.randint(0,64));frame=Frame(MessageType.HEALTH,vehicle,0,sequence,rng.randrange(2**32),payload)
   wire=frame.encode();self.assertEqual(Frame.decode(wire),frame);self.assertEqual(int.from_bytes(wire[9:13],"little"),sequence);self.assertLessEqual(len(wire),UART_MAX_FRAME)
  for value in bounds:self.assertIsInstance(value,int)
  encode_setpoint(1,-3000,3000,-18000,300,1);encode_setpoint(1,3000,-3000,18000,-300,100)
 def test_seeded_mutations_and_stream_resource_bound(self):
  rng=random.Random(7);base=Frame(MessageType.HELLO,1,0,1,1,encode_hello(1,1)).encode()
  for _ in range(256):
   changed=bytearray(base);index=rng.randrange(len(changed));changed[index]^=1<<rng.randrange(8)
   with self.assertRaises(ProtocolError):Frame.decode(bytes(changed),expected_vehicle_id=1)
  decoder=StreamDecoder(expected_vehicle_id=1)
  for _ in range(32):decoder.feed(rng.randbytes(65536));self.assertLessEqual(decoder.buffered_bytes,UART_MAX_FRAME)
  stream=b"noise"+base+base
  frames=[]
  for byte in stream:frames.extend(decoder.feed(bytes([byte])))
  self.assertEqual(len(frames),2)
 def test_sequence_wrap_and_nonce_collision(self):
  tracker=SequenceTracker();tracker.accept(Frame(MessageType.HEARTBEAT,1,0,0xffffffff,0,b""));tracker.accept(Frame(MessageType.HEARTBEAT,1,0,0,0,b""))
  with self.assertRaises(ProtocolError) as error:tracker.accept(Frame(MessageType.HEARTBEAT,1,0,0,0,b""))
  self.assertEqual(error.exception.code,RejectCode.DUPLICATE)
  with patch("aerolink_pi.service.secrets.randbits",side_effect=[5,5,6]):
   service=VehicleService(1,"server",b"test",FakeFc(1));service.connect_fc(0);self.assertEqual(service.session,6)
 def test_fleet_version_epoch_rollback_and_size(self):
  key=b"test-only";validator=FleetValidator(1,"server",key)
  good=FleetPacket("server",1,2,1,100,100,"PING",{}).sign(key);validator.accept(good,100)
  with self.assertRaises(ValueError):validator.accept(FleetPacket("server",1,1,2,100,100,"PING",{}).sign(key),100)
  with self.assertRaises(ValueError):validator.accept(FleetPacket("server",1,3,1,100,100,"PING",{"x":"z"*5000}).sign(key),100)
  with self.assertRaises(ValueError):validator.accept(FleetPacket("server",1,3,1,100,100,"PING",{},version=2).sign(key),100)
 def test_generated_schema_has_no_actuator_command(self):
  schema=json.loads((ROOT/"schemas/uart-v1.json").read_text());self.assertEqual(schema["actuator_commands"],[])
  self.assertEqual(UART_MAX_PAYLOAD,512);self.assertNotIn("ARM",UART_MESSAGE_TYPES);self.assertNotIn("MOTOR",UART_MESSAGE_TYPES)

if __name__=="__main__":unittest.main()
