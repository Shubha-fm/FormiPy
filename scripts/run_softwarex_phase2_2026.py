#!/usr/bin/env python3
"""Paired TLC/pytest evidence for FormiPy SoftwareX review.

Canonical controls are the repository's published safe/unsafe JSON examples.
Compare measured checker verdicts against generated Python smoke test outcomes;
do not interpret pytest passing as formal equivalence.
"""
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

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("FORMIPY_PHASE2_RESULTS", "results/softwarex_phase2"))
OUT.mkdir(parents=True, exist_ok=True)
client = TestClient(app)
cases = [
    ("tlc_safe", "state_machine", "PASSED"),
    ("tlc_unsafe", "state_machine", "VIOLATED"),
    ("tlc_usecase_safe", "use_case", "PASSED"),
    ("tlc_usecase_unsafe", "use_case", "VIOLATED"),
]
records = []
for name, kind, expected in cases:
    model = json.loads((ROOT / "examples" / (name + ".json")).read_text())
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "input.json").write_text(json.dumps(model, indent=2))
    response = client.post("/api/verify", json=model)
    if response.status_code != 200:
        raise RuntimeError(f"{name}: TLC endpoint returned {response.status_code}: {response.text[:800]}")
    formal = response.json()
    (folder / "tlc_result.json").write_text(json.dumps(formal, indent=2))
    (folder / "tlc_output.log").write_text(formal.get("tlc_output", ""))
    for key, suffix in (("tla", ".tla"), ("cfg", ".cfg")):
        if formal.get(key):
            (folder / ((formal.get("module_name") or name) + suffix)).write_text(formal[key])
    verdict = formal.get("statistics", {}).get("result")
    if verdict != expected:
        raise AssertionError(f"{name}: expected {expected}, observed {verdict}")

    export = client.post("/api/export", json=model)
    if export.status_code != 200:
        raise RuntimeError(f"{name}: ZIP export returned {export.status_code}")
    with tempfile.TemporaryDirectory(prefix="formipy_phase2_") as tmp:
        temp = Path(tmp)
        with ZipFile(io.BytesIO(export.content)) as archive:
            for item in archive.namelist():
                if item == "tests/test_generated.py" or item == "pytest.ini" or item.endswith(".py"):
                    path = temp / item
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.read(item))
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                              cwd=temp, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=60)
        (folder / "pytest_output.log").write_text(proc.stdout)
    test_result = "PASS" if proc.returncode == 0 else "FAIL"
    formally_safe = verdict == "PASSED"
    python_checks_pass = test_result == "PASS"
    records.append({
        "case": name, "diagram": kind, "tlc_expected": expected,
        "tlc_observed": verdict, "python_pytest": test_result,
        "pytest_exit_code": proc.returncode,
        "property_violation_detected_by_tlc": int(verdict == "VIOLATED"),
        "failing_pytest_detected": int(not python_checks_pass),
        "agreement_binary": int(formally_safe == python_checks_pass),
        "states_generated": formal.get("statistics", {}).get("states_generated"),
        "distinct_states": formal.get("statistics", {}).get("distinct_states"),
    })

with (OUT / "paired_results.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)
summary = {
    "study": "FormiPy Phase 2: canonical paired controls",
    "source_commit": os.getenv("GITHUB_SHA", "local-unrecorded"),
    "python": sys.version,
    "platform": platform.platform(),
    "cases": len(records),
    "tlc_expected_outcomes_matched": sum(r["tlc_expected"] == r["tlc_observed"] for r in records),
    "tlc_violations": sum(r["property_violation_detected_by_tlc"] for r in records),
    "pytest_passes": sum(r["python_pytest"] == "PASS" for r in records),
    "pytest_failures": sum(r["python_pytest"] == "FAIL" for r in records),
    "binary_agreements": sum(r["agreement_binary"] for r in records),
    "pairs": records,
    "limitations": [
        "Only four canonical controls; not representative of all UML inputs.",
        "TLC checks finite abstractions; Python pytest suite checks smoke/contract behavior.",
        "Not all formal properties are translated into corresponding Python assertions.",
        "Agreement is descriptive only; no equivalence or sensitivity conclusion from four controls.",
        "A passing pytest suite can coexist with a TLC violation."
    ]
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2))
(OUT / "README.md").write_text(
    "# FormiPy TLC versus Python test study\n\nFour canonical cases pair TLC outcomes "
    "with generated pytest outcomes. The test results are not necessarily the same "
    "property, so a mismatch is expected evidence of different coverage, not a tool defect.\n")
print("FORMIPY_PHASE2_SUMMARY=" + json.dumps(summary))
if summary["tlc_expected_outcomes_matched"] != len(cases):
    raise AssertionError("TLC controls did not match their expected outcomes")
print("FORMIPY_PHASE2_COMPLETE")
