#!/usr/bin/env python3
"""Reproduce the bounded finite semantic preservation experiment.

Uses two existing source state-machine fixtures; removes only weak fairness
and response liveness conditions, which are beyond the stated profile.
The finite transition checker and TLC safety verification are independent
checks, not a proof of general UML preservation.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile
from fastapi.testclient import TestClient
from main import app

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("FORMIPY_SEMANTICS_EVIDENCE", "results/bounded_semantic_preservation"))
OUT.mkdir(parents=True, exist_ok=True)
client = TestClient(app)
records = []

for label, expected_tlc in (("tlc_safe","PASSED"),("tlc_unsafe","VIOLATED")):
    model = json.loads((ROOT/"examples"/(label+".json")).read_text())
    model["weak_fairness"] = False
    model["response_condition"] = ""
    model["response_target"] = ""
    folder = OUT/label
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"source_model.json").write_text(json.dumps(model,indent=2))
    formal = client.post("/api/verify",json=model)
    if formal.status_code != 200:
        raise AssertionError(f"{label}: TLC verification HTTP {formal.status_code}: {formal.text[:500]}")
    verified = formal.json()
    (folder/"tlc.log").write_text(verified.get("tlc_output",""))
    actual_tlc = verified["statistics"]["result"]
    exported = client.post("/api/export",json=model)
    if exported.status_code != 200:
        raise AssertionError(f"{label}: project export HTTP {exported.status_code}")
    with tempfile.TemporaryDirectory(prefix="formipy_semantics_") as t:
        project = Path(t)
        with ZipFile(io.BytesIO(exported.content)) as z:
            meta = json.loads(z.read("semantic_profile.json"))
            if meta.get("status") != "bounded_finite_semantic_check_available":
                raise AssertionError(meta)
            names = [n for n in z.namelist() if n.endswith(".py") or n == "pytest.ini"]
            for name in names:
                path = project/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(z.read(name))
        command = [sys.executable,"-m","pytest","-q","-p","no:cacheprovider","tests/test_semantic_preservation.py"]
        p = subprocess.run(command,cwd=project,capture_output=True,text=True,timeout=45)
        (folder/"finite_oracle_pytest.log").write_text(p.stdout+"\n"+p.stderr)
        finite_pass = p.returncode == 0
        # An intentional implementation target mutation must be caught.
        filename = model["name"] + "_finite_semantics.py"
        destination = project/filename
        code = destination.read_text()
        original_target = model["transitions"][0]["target"]
        alternative_target = "idle" if original_target != "idle" else "stop"
        fragment = "'target': " + repr(original_target)
        replacement = "'target': " + repr(alternative_target)
        if fragment not in code:
            raise AssertionError(f"{label}: expected transition target is absent")
        destination.write_text(code.replace(fragment,replacement,1) + '\n# injected_mutation_to_invalidate_bytecode_cache\n')
        for cache in project.rglob('__pycache__'):
            shutil.rmtree(cache)
        q = subprocess.run(command,cwd=project,capture_output=True,text=True,timeout=45)
        (folder/"mutated_oracle_pytest.log").write_text(q.stdout+"\n"+q.stderr)
        mutant_detected = q.returncode != 0
    variable_count=len(model["verification_variables"])
    states=len(model["states"])
    record={
        "case":label,"tlc_expected":expected_tlc,"tlc_actual":actual_tlc,
        "finite_oracle_pass":finite_pass,"implementation_mutation_detected":mutant_detected,
        "all_domain_states_checked":states*(2**variable_count),
        "explicit_edges":len(model["transitions"]),
    }
    records.append(record)
    print("SEMANTIC_EVIDENCE_CASE="+json.dumps(record),flush=True)
    if actual_tlc != expected_tlc or not finite_pass or not mutant_detected:
        raise AssertionError("Unexpected formal or operational preservation outcome")

result={
    "source_commit":os.environ.get("GITHUB_SHA","local"),
    "profile":"flat Boolean state machines; safety and finite one-step transition relation",
    "cases":records,
    "limits":[
        "Two adapted canonical fixtures, not an independent external UML validation dataset.",
        "Exhaustive comparison includes all control-location × Boolean valuations within each model.",
        "Weak fairness and temporal response conditions removed from this experiment.",
        "TLC checks bounded TLA+ model safety separately; no formal refinement proof has been performed.",
        "Neither the legacy Python prototype nor any other UML diagram category has established semantic preservation."
    ]
}
(OUT/"summary.json").write_text(json.dumps(result,indent=2))
print("FORMIPY_FINITE_SEMANTICS_SUMMARY="+json.dumps(result),flush=True)
print("FORMIPY_FINITE_SEMANTICS_COMPLETE",flush=True)
