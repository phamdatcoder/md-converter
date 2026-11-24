"""Recreate the reported native crash in an isolated child interpreter."""

import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path


class RuntimeRegressionTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows DLL regression")
    def test_shell_extension_runtime_does_not_crash_threaded_converter(self):
        conflicting = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "TortoiseGit/bin/MSVCP140.dll"
        if not conflicting.is_file() or importlib.util.find_spec("onnxruntime") is None:
            self.skipTest("Requires installed document dependencies and the conflicting shell runtime")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", str(root / "tools/reproduce_runtime_crash.py"), "--fixed"],
            cwd=root, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Conversion succeeded", result.stdout)
