"""Regression tests for the precisely bounded operational preservation profile.

This does not claim the legacy prototype, PlantUML imports or UML semantics
outside the explicit finite Boolean state-machine subset are preserved.
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

CLIENT = TestClient(app)
ROOT = Path(__file__).resolve().parents[2]


class SemanticExportTests(unittest.TestCase):
    def inspect_export(self, model):
        response = CLIENT.post("/api/export", json=model)
        self.assertEqual(response.status_code, 200, response.text)
        with ZipFile(io.BytesIO(response.content)) as archive:
            payload = json.loads(archive.read("semantic_profile.json"))
            content = {n: archive.read(n) for n in archive.namelist()
                       if n.endswith(".py") or n.endswith(".ini")}
        return payload, content

    def run_exported(self, files, mutate=False):
        with tempfile.TemporaryDirectory(prefix="formipy_semantic_") as temp:
            root = Path(temp)
            for filename, content in files.items():
                dest = root / filename
                dest.parent.mkdir(parents=True, exist_ok=True)
                if mutate and filename.endswith("_finite_semantics.py"):
                    text = content.decode("utf-8")
                    self.assertIn("'target': 'stop'", text)
                    text = text.replace("'target': 'stop'", "'target': 'idle'", 1)
                    content = text.encode("utf-8")
                dest.write_bytes(content)
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 "tests/test_semantic_preservation.py"],
                cwd=root, capture_output=True, text=True, timeout=35
            )
            return result.returncode, result.stdout + "\n" + result.stderr

    def test_all_state_space_checked_for_safe_and_unsafe_models(self):
        for name in ("tlc_safe", "tlc_unsafe"):
            with self.subTest(name=name):
                model = json.loads((ROOT / "examples" / (name + ".json")).read_text())
                model["weak_fairness"] = False
                model["response_condition"] = ""
                model["response_target"] = ""
                profile, files = self.inspect_export(model)
                self.assertEqual(profile["status"], "bounded_finite_semantic_check_available")
                self.assertIn("tests/test_semantic_preservation.py", files)
                code, output = self.run_exported(files)
                self.assertEqual(code, 0, output)

    def test_simple_mutation_is_detected(self):
        model = json.loads((ROOT / "examples/tlc_safe.json").read_text())
        model["weak_fairness"] = False
        model["response_condition"] = ""
        model["response_target"] = ""
        _, files = self.inspect_export(model)
        code, output = self.run_exported(files, mutate=True)
        self.assertNotEqual(code, 0, output)
        self.assertIn("AssertionError", output)

    def test_multiple_guards_and_boolean_updates(self):
        model = {
            "name": "MultipleGuards",
            "diagram_type": "state_machine",
            "states": [{"id": "s0", "name": "First"},
                       {"id": "s1", "name": "Second"},
                       {"id": "s2", "name": "Third"}],
            "verification_variables": {"hazard": False, "ready": True},
            "verification_safety": 'not hazard or pc != "s2"',
            "transitions": [
                {"id": "a", "source": "s0", "target": "s1", "guard": "ready and not hazard",
                 "updates": {"hazard": True}},
                {"id": "b", "source": "s0", "target": "s2", "guard": "not ready or hazard",
                 "updates": {"ready": False}},
                {"id": "c", "source": "s1", "target": "s2", "guard": 'pc == "s1" and hazard',
                 "updates": {"hazard": False}},
            ]
        }
        profile, files = self.inspect_export(model)
        self.assertEqual(profile["status"], "bounded_finite_semantic_check_available")
        code, output = self.run_exported(files)
        self.assertEqual(code, 0, output)

    def test_unsupported_classes_and_temporal_properties_fail_closed(self):
        for model in (
            {"name": "ClassTest", "diagram_type": "class",
             "classes": [{"id": "a", "name": "Account"}]},
            {**json.loads((ROOT / "examples/tlc_safe.json").read_text()),
             "weak_fairness": True},
            {**json.loads((ROOT / "examples/tlc_safe.json").read_text()),
             "response_condition": 'pc == "idle"', "response_target": "stop"}
        ):
            with self.subTest(kind=model["diagram_type"]):
                profile, files = self.inspect_export(model)
                self.assertEqual(profile["status"], "not_supported")
                self.assertNotIn("tests/test_semantic_preservation.py", files)


if __name__ == "__main__":
    unittest.main()
