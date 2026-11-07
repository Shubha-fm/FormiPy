#!/usr/bin/env python3
"""Phase 3: matched, explicit finite safety checks on two controlled model families.

These are purpose-built property checks, NOT the default generated pytest suite.
The state-machine example uses a restricted subset of model semantics shared by
the Python prototype and TLC. Use-case permission checks compare the allowed
actor/case relation with an explicit forbidden pair.
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

OUT = Path(os.environ.get("FORMIPY_PHASE3_RESULTS", "results/softwarex_phase3"))
OUT.mkdir(parents=True, exist_ok=True)
CLIENT = TestClient(app)
PAIRS = int(os.environ.get("FORMIPY_PHASE3_PAIRS_PER_FAMILY", "10"))
if not 1 <= PAIRS <= 25:
    raise ValueError("Pairs per family must be between 1 and 25.")
rows = []

def model_state(i, mutant):
    # Names intentionally align with the Python prototype's hardcoded Cruise
    # safety check, while TLA+ uses the ID "cruise".
    return {
        "name": f"SafetyControl{i}_{'mut' if mutant else 'ref'}",
        "diagram_type": "state_machine",
        "verification_variables": {"hazard": False},
        "verification_safety": 'not hazard or pc != "cruise"',
        "states": [
            {"id": "idle", "name": "Idle"},
            {"id": "stop", "name": "Stop"},
            {"id": "cruise", "name": "Cruise"},
        ],
        "transitions": [
            {"id": "detect", "source": "idle",
             "target": "cruise" if mutant else "stop",
             "label": "hazard detected", "guard": "True",
             "updates": {"hazard": True}},
            {"id": "stable_stop", "source": "stop", "target": "stop",
             "guard": "True", "updates": {}},
            {"id": "stable_cruise", "source": "cruise", "target": "cruise",
             "guard": "True", "updates": {}},
        ]
    }

def model_usecase(i, mutant):
    associations = [
        {"id": "login_a", "source": "user", "target": "login"},
        {"id": "manage_a", "source": "admin", "target": "manage"},
    ]
    if mutant:
        associations.append({"id": "bad_permission", "source": "user", "target": "manage"})
    return {
        "name": f"PermissionControl{i}_{'mut' if mutant else 'ref'}",
        "diagram_type": "use_case",
        "actors": [{"id": "user", "name": "User"}, {"id": "admin", "name": "Admin"}],
        "use_cases": [{"id": "login", "name": "Login"}, {"id": "manage", "name": "Manage"}],
        "associations": associations,
        "forbidden_requests": [{"source": "user", "target": "manage"}],
    }

def write_aligned_test(folder, kind, model, python_file):
    source = folder / python_file
    # All generated files are located in an isolated temporary folder. Load only
    # the code produced from the predefined, trusted fixtures in this study.
    if kind == "state_machine":
        assertions = """
def test_matched_safety_contract():
    instance = GeneratedModel()
    instance.step(hazard=True)
    assert instance.check_safety(), instance.state()
"""
        classname = model["name"]
    else:
        classname = model["name"] + "UseCase"
        assertions = """
def test_explicit_forbidden_association_contract():
    instance = GeneratedModel()
    assert ("User", "Manage") not in instance.allowed
"""
    content = f'''import importlib.util
from pathlib import Path

path = Path(__file__).parent / {python_file!r}
spec = importlib.util.spec_from_file_location("generated_under_test", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
GeneratedModel = getattr(module, {classname!r})
''' + assertions
    (folder / "test_aligned_contract.py").write_text(content, encoding="utf-8")

for family, constructor in (("state_machine", model_state), ("use_case", model_usecase)):
    for i in range(PAIRS):
        for mutant in (False, True):
            label = f"{family}_{i:02d}_{'mutant' if mutant else 'reference'}"
            model = constructor(i, mutant)
            case_dir = OUT / label
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "input.json").write_text(json.dumps(model, indent=2))
            formal = CLIENT.post("/api/verify", json=model)
            if formal.status_code != 200:
                raise RuntimeError(f"{label}: TLC HTTP {formal.status_code}: {formal.text[:600]}")
            result = formal.json()
            (case_dir / "tlc_result.json").write_text(json.dumps(result, indent=2))
            (case_dir / "tlc_output.log").write_text(result.get("tlc_output", ""))
            verdict = result.get("statistics", {}).get("result")
            expected = "VIOLATED" if mutant else "PASSED"
            if verdict != expected:
                raise AssertionError(f"{label}: TLC {verdict} instead of {expected}")

            exported = CLIENT.post("/api/export", json=model)
            if exported.status_code != 200:
                raise RuntimeError(f"{label}: export HTTP {exported.status_code}")
            with tempfile.TemporaryDirectory(prefix="formipy_phase3_") as temp:
                folder = Path(temp)
                filename = model["name"] + ".py"
                with ZipFile(io.BytesIO(exported.content)) as z:
                    folder.joinpath(filename).write_bytes(z.read(filename))
                write_aligned_test(folder, family, model, filename)
                completed = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                     "test_aligned_contract.py"],
                    cwd=folder, capture_output=True, text=True, timeout=45,
                )
                (case_dir / "pytest_output.log").write_text(
                    completed.stdout + "\n" + completed.stderr)
            py = "PASS" if completed.returncode == 0 else "FAIL"
            expected_py = "FAIL" if mutant else "PASS"
            rows.append({
                "case": label, "family": family, "variant": "mutant" if mutant else "reference",
                "tlc": verdict, "pytest_aligned": py,
                "expected_tlc": expected, "expected_pytest": expected_py,
                "tlc_detects_mutant": int(mutant and verdict == "VIOLATED"),
                "pytest_detects_mutant": int(mutant and py == "FAIL"),
                "same_outcome": int((verdict == "PASSED") == (py == "PASS")),
                "distinct_states": result.get("statistics", {}).get("distinct_states"),
            })
            print(f"PAIR {label}: TLC={verdict}, aligned_pytest={py}", flush=True)
            if py != expected_py:
                raise AssertionError(f"{label}: pytest outcome {py}; expected {expected_py}")

with (OUT / "pairs.csv").open("w", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
summary = {
    "source_commit": os.environ.get("GITHUB_SHA", "local"),
    "python": sys.version,
    "platform": platform.platform(),
    "pairs_per_family": PAIRS,
    "total_cases": len(rows),
    "reference_cases": sum(x["variant"] == "reference" for x in rows),
    "mutants": sum(x["variant"] == "mutant" for x in rows),
    "tlc_mutants_detected": sum(x["tlc_detects_mutant"] for x in rows),
    "aligned_pytest_mutants_detected": sum(x["pytest_detects_mutant"] for x in rows),
    "matched_binary_outcomes": sum(x["same_outcome"] for x in rows),
    "scope": [
        "Purpose-built explicit property assertions, not FormiPy default generated smoke tests.",
        "Two template families with parameterized names. Variants are not independent real-world benchmarks.",
        "State-machine property alignment is restricted to a single hazard transition and the hardcoded Python Cruise predicate.",
        "Use-case oracle checks the forbidden relation against generated Python allowed pairs.",
        "Formal TLC and Python test execution are separate; success does not prove global UML-to-Python semantic equivalence.",
    ],
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2))
print("FORMIPY_PHASE3_SUMMARY=" + json.dumps(summary), flush=True)
print("FORMIPY_PHASE3_COMPLETE", flush=True)
