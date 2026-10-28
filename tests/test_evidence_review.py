import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from tools.e2e_runner.evidence_review import verify,write_gallery

# Test-only PNG has valid header; semantic inspection is expressly not automated.
PNG=b"\x89PNG\r\n\x1a\n"+struct.pack(">I",13)+b"IHDR"+struct.pack(">II",2,3)+b"\x08\x06\x00\x00\x00"
class EvidenceGateTests(unittest.TestCase):
 def test_manifest_validation_fails_closed(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   path=root/"screen.png"
   path.write_bytes(PNG)
   entry={"path":"screen.png","size":len(PNG),"sha256":hashlib.sha256(PNG).hexdigest()}
   r=verify(root,{"artifacts":{"screen.png":entry}})
   self.assertEqual(r[0]["resolution"],(2,3))
   self.assertEqual(r[0]["visual_verdict"],"NOT_REVIEWED")
   write_gallery(root,r,root/"index.html")
   self.assertIn("NOT REVIEWED",(root/"index.html").read_text())
   entry["size"]=0
   with self.assertRaisesRegex(ValueError,"mismatch"):
    verify(root,{"artifacts":{"screen.png":entry}})
 def test_no_escape_or_reused_screens(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   p=root/"s.png";p.write_bytes(PNG)
   entry={"path":"s.png","size":len(PNG),"sha256":hashlib.sha256(PNG).hexdigest()}
   with self.assertRaisesRegex(ValueError,"reused"):
    verify(root,{"artifacts":{"one.png":entry,"two.png":entry}})
   entry["path"]="../../etc/hosts"
   with self.assertRaises(ValueError):
    verify(root,{"artifacts":{"one.png":entry}})
