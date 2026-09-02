import tempfile,time,unittest
from pathlib import Path
from aerolink_server.core import AuditLog
from aerolink_server.security import *

class SecurityTest(unittest.TestCase):
 def test_mutual_signature_replay_identity_and_rotation(self):
  now=[100.0];wall=[1000.0];old=b"o"*32;new=b"n"*32;security=SecurityContext({1:old},clock=lambda:now[0],wall_clock=lambda:wall[0])
  body=b'{"vehicle_id":1}';headers=node_headers(1,old,"POST","/api/register",body,1000,"unique")
  nonce=security.verify_node(headers,"POST","/api/register",body,1);response=b'{"accepted":true}';signed=security.response_headers(1,"/api/register",response,nonce);verify_server_response(old,"/api/register",response,signed,nonce)
  with self.assertRaises(PermissionError):security.verify_node(headers,"POST","/api/register",body,1)
  security.rotate_node_key(1,new);headers=node_headers(1,new,"POST","/api/register",body,1000,"new-nonce");security.verify_node(headers,"POST","/api/register",body,1)
 def test_roles_expiry_rate_size_secret_and_redaction(self):
  now=[1.0];security=SecurityContext({1:b"k"*32},clock=lambda:now[0],wall_clock=lambda:100.0,rate=0,burst=1);viewer=security.create_operator_session("viewer",1);self.assertEqual(security.authorize_operator(viewer,"read"),"viewer")
  with self.assertRaises(PermissionError):security.authorize_operator(viewer,"abort")
  now[0]=2.0
  with self.assertRaises(PermissionError):security.authorize_operator(viewer,"read")
  body=b"{}";headers=node_headers(1,b"k"*32,"POST","/api/register",body,100,"first");security.verify_node(headers,"POST","/api/register",body,1)
  headers=node_headers(1,b"k"*32,"POST","/api/register",body,100,"second")
  with self.assertRaises(PermissionError):security.verify_node(headers,"POST","/api/register",body,1)
  with self.assertRaises(ValueError):SecurityContext({1:b"k"*32}).verify_node({},"POST","/",b"x"*(MAX_HTTP_BODY+1),1)
  self.assertEqual(redact({"token":"x","nested":{"secret":"y","ok":1}}),{"token":"[REDACTED]","nested":{"secret":"[REDACTED]","ok":1}})
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/"key";path.write_bytes(b"x"*32);path.chmod(0o600);self.assertEqual(load_secret("missing",path),b"x"*32);path.chmod(0o644)
   with self.assertRaises(PermissionError):load_secret("missing",path)
 def test_audit_chain_detects_tampering(self):
  audit=AuditLog();audit.append("one",{"safe":True});audit.append("two",{});self.assertTrue(audit.verify());audit.entries[0]["body"]+=" ";self.assertFalse(audit.verify())

if __name__=="__main__":unittest.main()
