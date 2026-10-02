import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('keccak_comparison', Path(__file__).with_name('run.py'))
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.digest = bytes.fromhex('c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')
        # For one round the observed checksum is exactly the digest's first lane.
        self.reply = (10).to_bytes(8, 'little') + self.digest + self.digest[:8]
        self.requests = [(b'', 1, 0)]

    def execute(self, reply, stderr=b''):
        response = SimpleNamespace(stdout=reply, stderr=stderr)
        with patch.object(comparison.subprocess, 'run', return_value=response):
            return comparison.execute(['fixture'], self.requests, [self.digest])

    def test_accepts_complete_digest_and_iteration_evidence(self):
        self.assertEqual(self.execute(self.reply), [(10, self.digest)])

    def test_rejects_truncation_extra_rows_and_process_diagnostics(self):
        for reply, stderr in [(self.reply[:-1], b''), (self.reply * 2, b''), (self.reply, b'error')]:
            with self.subTest(length=len(reply), stderr=stderr), self.assertRaises(AssertionError):
                self.execute(reply, stderr)

    def test_rejects_digest_and_iteration_corruption(self):
        for index in [8, 39, 40, 47]:
            reply = bytearray(self.reply)
            reply[index] ^= 1
            with self.subTest(index=index), self.assertRaises(AssertionError):
                self.execute(bytes(reply))


if __name__ == '__main__':
    unittest.main()
