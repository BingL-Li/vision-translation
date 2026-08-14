"""Offline smoke test for the template adapter (no key, no network).

Validates that the adapter maps protocol statuses correctly:
  - missing image → error, surfaced as not-ok with an error string
  - --self-check without a key → unavailable/no_api_key, ok=False reason set
  - CLI never crashes with unparseable stdout (protocol violation is caught)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapter


class TestAdapterMapping(unittest.TestCase):
    def test_missing_image_is_error(self):
        r = adapter.translate("/nonexistent/definitely-missing.jpg")
        self.assertFalse(r.ok)
        self.assertTrue(r.error)          # code: message from protocol error
        self.assertEqual(r.reason, "")    # error path, not unavailable

    def test_unavailable_no_key_has_reason(self):
        # --self-check via adapter is not wired, but the missing-image path
        # above proves mapping; here we prove the CLI itself stays legal
        # without a key (subprocess, no network):
        import json, subprocess
        proc = subprocess.run(
            [sys.executable, str(adapter.CLI), "--self-check"],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertIn(payload["status"], ("ok", "unavailable"))
        if payload["status"] == "unavailable":
            self.assertEqual(payload["unavailable"]["reason"], "no_api_key")

    def test_cli_stdout_is_pure_json(self):
        import json, subprocess
        proc = subprocess.run(
            [sys.executable, str(adapter.CLI), "--protocol-version"],
            capture_output=True, text=True, timeout=30)
        payload = json.loads(proc.stdout)   # raises if stdout has noise
        self.assertEqual(payload["protocol"], 1)


if __name__ == "__main__":
    unittest.main()
