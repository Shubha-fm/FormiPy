#!/usr/bin/env python3
"""Synthesize fresh, same-commit FormiPy SoftwareX Phase 1–5 runs.

Do not run on previously published summary numbers alone. Require raw per-case
CSV files, verify counts, calculate descriptive aggregates and preserve
provenance. Structured synthetic observations are not independent field cases.
"""
import csv
import json
import math
import os
import platform
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(os.environ.get("FORMIPY_STUDY_ROOT", "results"))
OUT = ROOT / "softwarex_synthesis"
OUT.mkdir(parents=True, exist_ok=True)
SEED = 20261108
RNG = random.Random(SEED)

def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

files = {
    "phase1_cases": ROOT / "softwarex_phase1/conversion_cases.csv",
    "phase1_pytest": ROOT / "softwarex_phase1/pytest_cases.csv",
    "phase1_invalid": ROOT / "softwarex_phase1/invalid_cases.csv",
    "phase1_latency": ROOT / "softwarex_phase1/latency_raw.csv",
    "phase2": ROOT / "softwarex_phase2/paired_results.csv",
    "phase3": ROOT / "softwarex_phase3/pairs.csv",
    "phase4": ROOT / "softwarex_phase4/results.csv",
    "phase5": ROOT / "softwarex_phase5/results.csv",
}
for label, path in files.items():
    if not path.is_file():
        raise FileNotFoundError(f"Cannot synthesize missing raw evidence: {label}: {path}")
data = {label: read_csv(path) for label, path in files.items()}
n_expected = {
    "phase1_cases": 250, "phase1_pytest": 250, "phase1_invalid": 100,
    "phase1_latency": 150, "phase2": 4, "phase3": 40,
    "phase4": 24, "phase5": 12,
}
for label, count in n_expected.items():
    if len(data[label]) != count:
        raise AssertionError(f"{label}: expected {count} observations, found {len(data[label])}")

# Compare all phase manifests to this exact source commit. A fresh all-phase run
# guarantees that source changes, test generator and checker are held constant.
sha = os.getenv("GITHUB_SHA", "").strip()
manifests = {}
for number in range(1, 6):
    manifest = read_json(ROOT / f"softwarex_phase{number}/summary.json")
    manifests[f"phase{number}"] = manifest
    observed = manifest.get("source_commit")
    if len(sha) != 40 or observed != sha:
        raise AssertionError(f"Phase {number} source SHA mismatch: {observed!r} vs {sha!r}")

p1 = data["phase1_cases"]
p1_tests = data["phase1_pytest"]
p1_invalid = data["phase1_invalid"]
p1_latency = data["phase1_latency"]
p2 = data["phase2"]
p3 = data["phase3"]
p4 = data["phase4"]
p5 = data["phase5"]

def cnt(records, field, expected):
    return sum(str(row[field]) == str(expected) for row in records)

conversion = cnt(p1, "valid_conversion", 1)
pytest_pass = cnt(p1_tests, "result", "PASS")
invalid = cnt(p1_invalid, "rejected", 1)
if any(row["verification_kind"] != "structural" for row in p1):
    raise AssertionError("Phase 1 wrongly labeled a structural conversion as TLC.")

def variants(records, field, value):
    return [r for r in records if r[field] == value]

p3_mut = variants(p3, "variant", "mutant")
p3_ref = variants(p3, "variant", "reference")
p4_mut = variants(p4, "variant", "mutant")
p4_ref = variants(p4, "variant", "reference")
p5_mut = variants(p5, "mutant", "1")
p5_ref = variants(p5, "mutant", "0")

def explicit_pair_counts(records, tlc_key, pytest_key, tlc_safe, pytest_safe):
    return {
        "both_safe_or_pass": sum(r[tlc_key] == tlc_safe and r[pytest_key] == pytest_safe for r in records),
        "tlc_violation_pytest_pass": sum(r[tlc_key] == "VIOLATED" and r[pytest_key] == pytest_safe for r in records),
        "tlc_pass_pytest_failure": sum(r[tlc_key] == tlc_safe and r[pytest_key] == "FAIL" for r in records),
        "tlc_violation_pytest_failure": sum(r[tlc_key] == "VIOLATED" and r[pytest_key] == "FAIL" for r in records)
    }

paired = {
    "phase2": explicit_pair_counts(p2, "tlc_observed", "python_pytest", "PASSED", "PASS"),
    "phase3": explicit_pair_counts(p3, "tlc", "pytest_aligned", "PASSED", "PASS"),
    "phase4": explicit_pair_counts(p4, "tlc", "default_pytest", "PASSED", "PASS"),
    "phase5": explicit_pair_counts(p5, "tlc", "exported_pytest", "PASSED", "PASS"),
}

# Descriptive repeated-measure latency. Percentile bootstrap CI (1,000 draws)
# captures variability under this exact runner/workload, not field generalization.
latency = []
for n in (5, 10, 20, 40, 80):
    values = [float(x["milliseconds"]) for x in p1_latency if int(x["nodes"]) == n]
    if len(values) != 30:
        raise AssertionError(f"Latency size {n}: expected 30 repeats")
    boot = sorted(statistics.median(RNG.choices(values, k=30)) for _ in range(1000))
    latency.append({
        "nodes": n, "n": 30,
        "median_ms": round(statistics.median(values), 6),
        "mean_ms": round(statistics.mean(values), 6),
        "sd_ms": round(statistics.stdev(values), 6),
        "bootstrap_median_ci95_ms": [round(boot[25], 6), round(boot[974], 6)],
    })
all_pairs = {
    "phase2": (len(p2), sum(r["tlc_observed"] == "VIOLATED" for r in p2), sum(r["python_pytest"] == "FAIL" for r in p2)),
    "phase3": (len(p3), sum(r["tlc"] == "VIOLATED" for r in p3), sum(r["pytest_aligned"] == "FAIL" for r in p3)),
    "phase4": (len(p4), sum(r["tlc"] == "VIOLATED" for r in p4), sum(r["default_pytest"] == "FAIL" for r in p4)),
    "phase5": (len(p5), sum(r["tlc"] == "VIOLATED" for r in p5), sum(r["exported_pytest"] == "FAIL" for r in p5)),
}
summary = {
    "source_commit": sha, "analysis_seed": SEED,
    "python": sys.version, "platform": platform.platform(),
    "phase1": {
        "structural_conversions_pass": conversion, "structural_conversion_total": len(p1),
        "default_pytest_pass": pytest_pass, "default_pytest_total": len(p1_tests),
        "invalid_input_rejections": invalid, "invalid_input_total": len(p1_invalid),
        "latency": latency,
    },
    "paired_outcomes": paired,
    "pair_counts": all_pairs,
    "controls": {
        "phase3_reference_cases": len(p3_ref), "phase3_mutants": len(p3_mut),
        "phase4_reference_cases": len(p4_ref), "phase4_mutants": len(p4_mut),
        "phase5_reference_cases": len(p5_ref), "phase5_mutants": len(p5_mut),
    },
    "study_design": {
        "phase1": "balanced 250 synthetic structural models and 250 exported smoke suites, 100 malformed models",
        "phase2": "four canonical TLC reference/fault controls, current exported Python tests",
        "phase3": "20 reference and 20 mutant template repetitions, purpose-built property-aligned tests",
        "phase4": "12 distinct hand-designed synthetic structures, reference and mutant each, current exported Python tests",
        "phase5": "six Phase-4 use-case structures retested after built-in forbidden-permission contract addition",
    },
    "validity_limits": [
        "The Phase 1 model population is synthetic; not a random sample of real UML projects.",
        "Phase 3 repeats two templates, so observations are not independent benchmarks.",
        "Phase 5 reuses Phase 4 permission models; do not combine counts as unique models.",
        "Phase 3 custom test oracles are different from the default generated pytest tests.",
        "All phases are rerun here on the same current revision; earlier historical Phase 4 used an older pytest generator.",
        "TLC checks bounded model semantics; Python checks the generated prototype.",
        "The reported bootstrap confidence intervals describe repeated runtime sampling on this CI runner.",
        "No independent industrial case-study validation is included.",
    ]
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

lines = [
    "# FormiPy SoftwareX evaluation: reproducible synthesis",
    "",
    f"**Code revision (all phases freshly run):** \`{sha}\`",
    "",
    "## Structural conversion and input checks",
    "",
    f"- {conversion}/{len(p1)} structurally valid conversion results across five UML categories.",
    f"- {pytest_pass}/{len(p1_tests)} exported smoke suites passed on the synthetically generated models.",
    f"- {invalid}/{len(p1_invalid)} deliberately invalid model inputs rejected.",
    "",
    "These are structural and executable checks, **not TLC equivalence**.",
    "",
    "## Repeated structural API latency (30 requests per size)",
    "",
    "| State nodes | Median (ms) | Mean (ms) | SD (ms) | 95% bootstrap median interval (ms) |",
    "|---:|---:|---:|---:|---:|",
]
for row in latency:
    low, high = row["bootstrap_median_ci95_ms"]
    lines.append(f'| {row["nodes"]} | {row["median_ms"]:.3f} | {row["mean_ms"]:.3f} | {row["sd_ms"]:.3f} | [{low:.3f}, {high:.3f}] |')
lines += [
    "",
    "## TLC outcomes versus Python tests",
    "",
    "| Phase | Cases | TLC violations | Python failures | TLC violation + pytest pass | TLC violation + pytest failure |",
    "|---|---:|---:|---:|---:|---:|",
]
for label, (num, tlc, py) in all_pairs.items():
    q = paired[label]
    lines.append(f'| {label.replace("phase", "Phase ")} | {num} | {tlc} | {py} | {q["tlc_violation_pytest_pass"]} | {q["tlc_violation_pytest_failure"]} |')
lines += [
    "",
    "These studies are all rerun on the same updated FormiPy commit. Current exported tests now include use-case forbidden-permission checks, so results may differ from the historical original Phase 2 and Phase 4 runs. Phase 3 uses purpose-built aligned tests. Phase 5 reuses six Phase 4 permission structures.",
    "",
    "## Reproducibility and limitations",
    "",
    "Every phase was rerun from one GitHub commit. All case-level CSVs, raw TLC output, pytest logs and manifests are retained in the GitHub Actions artifact. Numeric claims above were recalculated from raw CSVs by this script.",
    "",
    "**No independent industrial or externally sourced benchmark evaluation has been completed.** These synthetic cases were selected to exercise documented features and known faults. They cannot support an unrestricted statistical generalization or a formal correctness claim for generated Python.",
    "",
    "Bootstrap intervals quantify variability across repeated in-process conversion calls on a single runner. They do not measure browser, Render network, or TLC model-checking latency.",
    "",
    "Phase 4 and Phase 5 contain the same six permission structures in this same-commit re-execution; they are NOT a before/after comparison. Historical before/after claims require the original run logs on different commits. The data do not establish an unbiased population-level improvement.",
    "",
    "## Manuscript wording",
    "",
    "Present the tool as a web application for diagram modeling, TLA+ artifact generation, structural analysis, selected bounded TLC checking and Python prototype generation. State clearly which properties are checked by TLC and which are checked by generated pytest. Do not describe 250 structurally valid examples as 250 verified implementations.",
]
(OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("FORMIPY_SYNTHESIS=" + json.dumps({"source_commit":sha,"phase1":summary["phase1"],"paired_outcomes":paired,"pair_counts":all_pairs}), flush=True)
print("FORMIPY_SYNTHESIS_COMPLETE", flush=True)
