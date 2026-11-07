"""Regression test for FormiPy permission-aware exported pytest contracts.

A positive permission model must pass the exported tests; adding a forbidden
actor/use-case association must make the exported pytest suite fail. This does
not imply equivalent coverage of TLC's temporal properties.
"""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from main import app

ROOT = Path(__file__).resolve().parents[2]
CLIENT = TestClient(app)


class PermissionContractExportTests(unittest.TestCase):
    def test_safe_and_forbidden_permission_mutant(self):
        for name, should_pass in [
            ("tlc_usecase_safe", True),
            ("tlc_usecase_unsafe", False),
        ]:
            with self.subTest(model=name):
                model = json.loads((ROOT / "examples" / (name + ".json")).read_text())
                exported = CLIENT.post("/api/export", json=model)
                self.assertEqual(exported.status_code, 200, exported.text)
                with tempfile.TemporaryDirectory(prefix="formipy_contract_") as d:
                    folder = Path(d)
                    with ZipFile(io.BytesIO(exported.content)) as archive:
                        self.assertIn("tests/test_generated.py", archive.namelist())
                        self.assertIn("pytest.ini", archive.namelist())
                        self.assertIn(model["name"] + ".py", archive.namelist())
                        for filename in (
                            "tests/test_generated.py", "pytest.ini", model["name"] + ".py"
                        ):
                            location = folder / filename
                            location.parent.mkdir(parents=True, exist_ok=True)
                            location.write_bytes(archive.read(filename))
                    self.assertIn(
                        "test_forbidden_permissions_are_not_granted",
                        (folder / "tests/test_generated.py").read_text(),
                    )
                    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
                    result = subprocess.run(
                        command, cwd=folder, capture_output=True, text=True, timeout=35
                    )
                    self.assertEqual(
                        result.returncode == 0, should_pass,
                        result.stdout + result.stderr,
                    )
                    if not should_pass:
                        self.assertIn("Forbidden permission granted", result.stdout)


if __name__ == "__main__":
    unittest.main()
