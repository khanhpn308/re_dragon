"""Standalone oracle for synthetic pilot fixture; not imported by CI.

The pilot Agent runs this against its isolated copy before/after reviewer-driven
repair. The committed canary is intentionally buggy, so do NOT include this
test in the always-green production CI pipeline.
"""
from pathlib import Path
import importlib.util
import unittest

path = Path(__file__).with_name("buggy_decoder.py")
spec = importlib.util.spec_from_file_location("pilot_buggy_decoder", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class FixtureOracle(unittest.TestCase):
    def test_endianness(self):
        self.assertEqual(module.decode_frame(bytes.fromhex("0003616263")),b"abc")

    def test_empty(self):
        self.assertEqual(module.decode_frame(bytes.fromhex("0000")),b"")

    def test_single(self):
        self.assertEqual(module.decode_frame(bytes.fromhex("0001ff")),bytes.fromhex("ff"))

    def test_extra_bytes_rejected(self):
        with self.assertRaises(ValueError):
            module.decode_frame(bytes.fromhex("0000ff"))

    def test_truncated(self):
        with self.assertRaises(ValueError):
            module.decode_frame(bytes.fromhex("0002aa"))

if __name__=="__main__":
    unittest.main()
