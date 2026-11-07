#!/usr/bin/env python3
"""SoftwareX phase-1 empirical study for the current FormiPy commit.

This study separates structural conversion and generated Python pytest outcomes.
No conversion success is described as formal model verification.
"""
import ast
import csv
import io
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from main import app

SEED = 20261108
RNG = random.Random(SEED)
OUT = Path(os.environ.get("FORMIPY_RESULTS", "results/softwarex_phase1"))
OUT.mkdir(parents=True, exist_ok=True)
CLIENT = TestClient(app)
KINDS = ("state_machine", "activity", "class", "sequence", "use_case")
RELEASE_SHA = os.environ.get("GITHUB_SHA", "local-unknown")
rows = []
tests = []
timings = []
invalid_rows = []

def write_csv(name, records, columns):
    with (OUT/name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)

def model(kind, idx, size=None):
    n = size or (2 + idx % 7)
    ids = [f"n{i}" for i in range(n)]
    p = {"name": f"Study_{kind}_{idx:03d}", "diagram_type": kind}
    if kind == "state_machine":
        p["states"] = [{"id": i, "name": f"S{k}"} for k, i in enumerate(ids)]
        p["transitions"] = [{"id": f"e{k}", "source": ids[k], "target": ids[k+1],
                             "label": ""} for k in range(n-1)]
    elif kind == "activity":
        p["actions"] = [{"id": i, "name": f"Action{k}"} for k, i in enumerate(ids)]
        p["flows"] = [{"id": f"e{k}", "source": ids[k], "target": ids[k+1]} for k in range(n-1)]
    elif kind == "class":
        p["classes"] = [{"id": i, "name": f"Class{k}", "attributes": [], "methods": []}
                        for k, i in enumerate(ids)]
        p["relationships"] = [{"id": f"e{k}", "source": ids[k], "target": ids[k+1]}
                              for k in range(n-1)]
    elif kind == "sequence":
        p["lifelines"] = [{"id": i, "name": f"Actor{k}"} for k, i in enumerate(ids)]
        p["messages"] = [{"id": f"e{k}", "source": ids[k], "target": ids[k+1],
                          "order": k+1, "label": f"message{k}"} for k in range(n-1)]
    else:
        p["actors"] = [{"id": "user", "name": "User"}]
        p["use_cases"] = [{"id": i, "name": f"Case{k}"} for k, i in enumerate(ids)]
        p["associations"] = [{"id": f"e{k}", "source": "user", "target": i}
                              for k, i in enumerate(ids)]
    return p

def run_exported_pytest(zip_bytes, label):
    with tempfile.TemporaryDirectory(prefix="formipy_study_") as temp:
        root = Path(temp)
        with ZipFile(io.BytesIO(zip_bytes)) as archive:
            names = archive.namelist()
            for name in names:
                if name == "pytest.ini" or name == "tests/test_generated.py" or name == label + ".py":
                    dest = root/name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(archive.read(name))
        if not (root/"tests/test_generated.py").exists():
            return {"result": "MISSING_TEST_FILE", "exit_code": -1, "output": "Generated test missing"}
        try:
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                                    cwd=root, text=True, capture_output=True, timeout=35)
            return {"result": "PASS" if result.returncode == 0 else "FAIL",
                    "exit_code": result.returncode,
                    "output": (result.stdout + "\n" + result.stderr)[-3000:]}
        except subprocess.TimeoutExpired:
            return {"result": "TIMEOUT", "exit_code": -2, "output": "35-second timeout"}

# 250 unique named models, balanced across the five supported diagram categories.
for kind in KINDS:
    for i in range(50):
        payload = model(kind, i)
        resp = CLIENT.post("/api/convert", json=payload)
        data = resp.json()
        ok = resp.status_code == 200 and data.get("verification_kind") == "structural"
        if ok:
            try:
                ast.parse(data["python_code"])
            except (SyntaxError, KeyError):
                ok = False
        rows.append({"diagram": kind, "case": i, "elements": 2 + i%7,
                     "http_code": resp.status_code, "valid_conversion": int(ok),
                     "verification_kind": data.get("verification_kind", "")})
        export = CLIENT.post("/api/export", json=payload)
        test = run_exported_pytest(export.content, payload["name"]) if export.status_code == 200 else {
            "result": "EXPORT_ERROR", "exit_code": export.status_code, "output": export.text[-1000:]}
        tests.append({"diagram": kind, "case": i, "result": test["result"],
                      "exit_code": test["exit_code"]})
        if test["result"] != "PASS":
            log = OUT/"failed_pytests"
            log.mkdir(exist_ok=True)
            (log/f"{kind}_{i:03d}.txt").write_text(test["output"], encoding="utf-8")

# Repeat input-validation tests against 100 distinct malformed payloads.
for i in range(100):
    kind = KINDS[i%5]
    payload = model(kind, i)
    if kind == "state_machine":
        payload["transitions"][0]["target"] = "missing"
    elif kind == "activity":
        payload["flows"][0]["target"] = "missing"
    elif kind == "class":
        payload["classes"][1]["id"] = payload["classes"][0]["id"]
    elif kind == "sequence":
        payload["messages"][0]["source"] = "missing"
    else:
        payload["associations"][0]["target"] = "missing"
    resp = CLIENT.post("/api/convert", json=payload)
    invalid_rows.append({"diagram": kind, "case": i, "http_code": resp.status_code,
                         "rejected": int(resp.status_code == 422)})

# Five sizes, 30 measurements per size; explicit FastAPI in-process timings.
for size in (5, 10, 20, 40, 80):
    payload = model("state_machine", 999, size=size)
    for repetition in range(30):
        start = time.perf_counter_ns()
        resp = CLIENT.post("/api/convert", json=payload)
        ms = (time.perf_counter_ns() - start) / 1e6
        data = resp.json()
        timings.append({"nodes": size, "edges": size-1, "repetition": repetition,
                        "milliseconds": round(ms, 6), "http_code": resp.status_code,
                        "states_explored": data.get("statistics", {}).get("states_explored")})

write_csv("conversion_cases.csv", rows,
          ["diagram","case","elements","http_code","valid_conversion","verification_kind"])
write_csv("pytest_cases.csv", tests, ["diagram","case","result","exit_code"])
write_csv("invalid_cases.csv", invalid_rows, ["diagram","case","http_code","rejected"])
write_csv("latency_raw.csv", timings,
          ["nodes","edges","repetition","milliseconds","http_code","states_explored"])

def bootstrap_median_ci(values):
    medians = [statistics.median(RNG.choices(values, k=len(values))) for _ in range(1000)]
    medians.sort()
    return round(medians[25], 6), round(medians[974], 6)

latency_summary = []
for size in (5, 10, 20, 40, 80):
    vals = [r["milliseconds"] for r in timings if r["nodes"] == size and r["http_code"] == 200]
    low, high = bootstrap_median_ci(vals)
    latency_summary.append({"nodes": size, "samples": len(vals),
                            "median_ms": round(statistics.median(vals), 6),
                            "mean_ms": round(statistics.mean(vals), 6),
                            "sample_sd_ms": round(statistics.stdev(vals), 6),
                            "bootstrap_median_ci95_ms": [low, high]})
summary = {
    "source_commit": RELEASE_SHA, "seed": SEED, "python": sys.version,
    "platform": platform.platform(), "experiment": "softwarex-phase1-current",
    "valid_conversion_cases": sum(x["valid_conversion"] for x in rows),
    "total_conversion_cases": len(rows),
    "pytest_passes": sum(t["result"] == "PASS" for t in tests),
    "pytest_failures": sum(t["result"] != "PASS" for t in tests),
    "total_pytest_exports": len(tests),
    "invalid_rejected": sum(x["rejected"] for x in invalid_rows),
    "total_invalid": len(invalid_rows),
    "latency_summary": latency_summary,
    "limitations": [
        "Generated, structurally simple, connected synthetic UML models, not independent real-world case studies.",
        "Generated pytest suites are smoke/contract tests, not full behavioral equivalence checks.",
        "No TLC results in this phase; TLC model checking is a separate experiment.",
        "Performance measures in-process FastAPI structural conversion, not browser or deployed network latency.",
        "Bootstrap confidence intervals are conditional on this machine and request workload.",
    ],
}
(OUT/"summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
(OUT/"README.md").write_text(
    "# FormiPy SoftwareX Phase 1\n\n"
    "This archive contains **new measurements** from the commit in summary.json.\n"
    "CSV files preserve individual observations; failed_pytests retains failure output.\n"
    "Conversion, Python pytest, invalid-input and structural latency are different outcomes.\n"
    "No TLC safety result or implementation-equivalence claim is made by this phase.\n",
    encoding="utf-8")
print("FORMIPY_PHASE1_SUMMARY=" + json.dumps(summary))
if len(rows) != 250 or len(tests) != 250 or len(invalid_rows) != 100 or len(timings) != 150:
    raise AssertionError("Unexpected sample count")
print("FORMIPY_PHASE1_COMPLETE")
