#!/usr/bin/env python3
"""SoftwareX Phase 5: evaluate built-in exported use-case permission contracts.

Six diverse permission graphs from Phase 4 are each tested as a reference
and with one forbidden pair added. TLC and the unmodified exported pytest
suite run independently. Expected pytest failures are *detections*.
"""
import ast
import csv
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile
from fastapi.testclient import TestClient
from main import app

REPO = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("FORMIPY_PHASE5_RESULTS", "results/softwarex_phase5"))
OUT.mkdir(parents=True, exist_ok=True)
CLIENT = TestClient(app)
# Read the literal fixture definitions from the earlier benchmark protocol;
# never execute that experiment module as an import side effect.
tree = ast.parse((REPO / "scripts/run_softwarex_phase4_2026.py").read_text())
fixture_node = next(
    n.value for n in tree.body if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "PERMISSIONS" for t in n.targets)
)
permissions = ast.literal_eval(fixture_node)
rows = []
for label, (actors, usecases, allowed, forbidden) in permissions.items():
    for mutant in (False, True):
        name = "Permission_" + label + ("_Mutant" if mutant else "_Reference")
        associations = allowed + ([forbidden] if mutant else [])
        payload = {
            "name": name, "diagram_type": "use_case",
            "actors": [{"id": x, "name": x} for x in actors],
            "use_cases": [{"id": x, "name": x} for x in usecases],
            "associations": [
                {"id": "association" + str(i), "source": a, "target": u}
                for i, (a, u) in enumerate(associations)
            ],
            "forbidden_requests": [{"source": forbidden[0], "target": forbidden[1]}]
        }
        folder = OUT / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "input.json").write_text(json.dumps(payload, indent=2))
        formal_response = CLIENT.post("/api/verify", json=payload)
        if formal_response.status_code != 200:
            raise AssertionError(f"{name}: verify HTTP {formal_response.status_code}")
        formal = formal_response.json()
        (folder / "tlc_result.json").write_text(json.dumps(formal, indent=2))
        (folder / "tlc_output.log").write_text(formal.get("tlc_output", ""))
        tlc_verdict = formal["statistics"]["result"]
        exported = CLIENT.post("/api/export", json=payload)
        if exported.status_code != 200:
            raise AssertionError(f"{name}: export HTTP {exported.status_code}")
        with tempfile.TemporaryDirectory(prefix="formipy_phase5_") as temp:
            root = Path(temp)
            with ZipFile(io.BytesIO(exported.content)) as zipfile:
                for path in ("pytest.ini", "tests/test_generated.py", name + ".py"):
                    destination = root / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(zipfile.read(path))
            test_file = (root / "tests/test_generated.py").read_text()
            if "test_forbidden_permissions_are_not_granted" not in test_file:
                raise AssertionError(f"{name}: missing built-in property-aware test")
            run = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                cwd=root, capture_output=True, text=True, timeout=45
            )
            (folder / "pytest_output.log").write_text(run.stdout + "\n" + run.stderr)
        pytest_verdict = "PASS" if run.returncode == 0 else "FAIL"
        row = {
            "name": name, "topology": label, "mutant": int(mutant),
            "tlc": tlc_verdict, "exported_pytest": pytest_verdict,
            "tlc_detects_mutant": int(mutant and tlc_verdict == "VIOLATED"),
            "pytest_detects_mutant": int(mutant and pytest_verdict == "FAIL"),
            "expected": "VIOLATED/FAIL" if mutant else "PASSED/PASS"
        }
        rows.append(row)
        print("PHASE5_CASE=" + json.dumps(row), flush=True)
        expected_tlc = "VIOLATED" if mutant else "PASSED"
        expected_pytest = "FAIL" if mutant else "PASS"
        if tlc_verdict != expected_tlc or pytest_verdict != expected_pytest:
            raise AssertionError(f"{name}: unexpected verdict {row}")
with (OUT / "results.csv").open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
summary = {
    "source_commit": os.getenv("GITHUB_SHA", "local"),
    "platform": platform.platform(), "python": sys.version,
    "distinct_permission_structures": len(permissions),
    "references": sum(not row["mutant"] for row in rows),
    "mutants": sum(row["mutant"] for row in rows),
    "tlc_detected_mutants": sum(row["tlc_detects_mutant"] for row in rows),
    "built_in_pytest_detected_mutants": sum(row["pytest_detects_mutant"] for row in rows),
    "limitations": [
        "Six hand-designed synthetic permission structures from Phase 4, not industrial inputs.",
        "One forbidden association injected per structure.",
        "Exported pytest checks explicit forbidden permission pairs, not full temporal logic.",
        "State machine guards/updates and temporal properties remain outside the supported Python contract.",
        "Expected pytest failures on intentionally faulty models represent defect detection, not CI failure."
    ]
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2))
(OUT / "README.md").write_text(
    "Phase 5 evaluates FormiPy's built-in permission-aware exported pytest tests "
    "against six reference/mutant pairs from the Phase 4 synthetic permission suite. "
    "TLC outcomes and Python test outcomes are retained independently.\n")
print("FORMIPY_PHASE5_SUMMARY=" + json.dumps(summary), flush=True)
print("FORMIPY_PHASE5_COMPLETE", flush=True)
