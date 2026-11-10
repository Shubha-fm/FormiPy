#!/usr/bin/env python3
"""Build the separately versioned FormiPy Zenodo *draft* upload archive.

This script includes a pinned, tracked Git snapshot, independent experiment
artifacts from successful CI workflows, metadata, licenses, citation guidance,
and checksums. It does NOT publish to Zenodo or mint a DOI.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

PINNED_SOURCE = "e1924eb98d90f5dc110d666f2189091bed0de8b7"
DATE = "2026-11-10"
VERSION = "2026.11.10-dev"
ARCHIVE_NAME = f"FormiPy_Zenodo_Development_Snapshot_{DATE}.zip"

EVIDENCE = {
    "same_commit_phases_1_to_5": ("42410768543", "3c1efa21a67ce2144c3ee1c2d567357ea29d42c0"),
    "external_goldenuml": ("42412269801", "829fe30cfafe73ff4f7ed9594b774aea3fdc01e1"),
    "external_modes3": ("42412269801", "829fe30cfafe73ff4f7ed9594b774aea3fdc01e1"),
    "bounded_semantics": ("42412983262", "8144ddc615bcca3def7d3353578a4280b42c1216"),
}

root = Path(os.environ.get("FORMIPY_ZENODO_WORKSPACE", ".")).resolve()
source = root / "snapshot"
evidence_root = root / "evidence"
outdir = root / "dist"
outdir.mkdir(parents=True, exist_ok=True)
assert source.is_dir(), "Pinned source checkout not found"
sha = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
if sha != PINNED_SOURCE:
    raise RuntimeError(f"Source mismatch: {sha} != {PINNED_SOURCE}")

tracked = subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"]).split(b"\0")
source_files = [os.fsdecode(x) for x in tracked if x]
if len(source_files) < 60:
    raise RuntimeError("Unexpectedly small or incomplete source snapshot")

# Fail rather than redistributing sensitive or generated local files.
skip_name = re.compile(
    r"(^|/)(\.env(?:\..*)?|\.git|node_modules|__pycache__|\.venv|\.tox|"
    r"\.pytest_cache|playwright-report|test-results|dist|build)(/|$)", re.I
)
secret_file = re.compile(r"\.(pem|key|p12|pfx|sqlite|db)$", re.I)
for path in source_files:
    if skip_name.search(path) or secret_file.search(path):
        raise RuntimeError(f"Unexpected sensitive/generated tracked file: {path}")

creators = [
    {"name": "Chakraborty, Shubha", "affiliation": "Department of Computer Science, The University of Burdwan, India", "orcid": "0009-0000-5015-0478"},
    {"name": "Karmakar, Rahul", "affiliation": "Department of Computer Science, The University of Burdwan, India", "orcid": "0000-0002-6607-2707"},
]
zenodo_json = {
    "title": "FormiPy: UML-to-TLA+ Web Application, Python Prototypes, and Reproducible Verification Evidence (Development Snapshot, November 2026)",
    "upload_type": "software",
    "description": (
        "<p>Version-pinned research software package containing the FormiPy web application "
        "(React/FastAPI), TLA+ generation, bounded TLC verification workflows, Python "
        "prototype exports, test infrastructure, and separately labeled experimental evidence. "
        "The snapshot is tied to Git commit " + PINNED_SOURCE + ".</p>"
        "<p>Scope: five UML diagram categories have structural conversion pathways. TLC "
        "is used for selected finite state-machine and use-case abstractions. A separate bounded "
        "finite interpreter is available for a limited flat Boolean state-machine profile. "
        "Full UML semantic preservation and independently validated industrial deployments "
        "have not been established. The external Golden UML and MoDeS3 evaluations are "
        "adaptation/compatibility studies and document information loss.</p>"
    ),
    "creators": creators,
    "version": VERSION,
    "license": "MIT",
    "keywords": [
        "FormiPy", "UML", "TLA+", "TLC", "model checking",
        "formal methods", "software verification", "Python", "reproducibility",
    ],
    "related_identifiers": [
        {
            "identifier": "https://github.com/Shubha-fm/FormiPy/tree/" + PINNED_SOURCE,
            "relation": "isSupplementTo",
            "scheme": "url",
        }
    ],
    "access_right": "open",
    "notes": "Draft metadata only. Do not cite a new Zenodo DOI until the upload is published.",
}
citation = f"""cff-version: 1.2.0
message: "If you use FormiPy, cite the Zenodo software snapshot after publication."
type: software
title: "FormiPy: UML-to-TLA+ web application"
authors:
  - family-names: Chakraborty
    given-names: Shubha
    orcid: "https://orcid.org/0009-0000-5015-0478"
    affiliation: "The University of Burdwan"
  - family-names: Karmakar
    given-names: Rahul
    orcid: "https://orcid.org/0000-0002-6607-2707"
    affiliation: "The University of Burdwan"
repository-code: https://github.com/Shubha-fm/FormiPy
url: https://uml2tla-app.onrender.com
license: MIT
version: "{VERSION}"
"""
readme = f"""# FormiPy Zenodo draft package: {DATE}

**Deposit status:** This package is prepared for a NEW Zenodo upload. It is not
a published Zenodo record and has **no assigned new DOI**.

**Resource type:** Software. **Version:** {VERSION} (development snapshot).
**Pinned source commit:** \`{PINNED_SOURCE}\`.
**Source repository:** https://github.com/Shubha-fm/FormiPy
**Public web app:** https://uml2tla-app.onrender.com (live uptime not part of this archive)
**License:** MIT (see source/LICENSE.txt).

## Package contents

- \`source/\`: exact tracked repository snapshot at the pinned Git commit,
  including source, tests, configurations, examples, documentation and CI.
- \`evidence/\`: raw evidence from completed, independently named GitHub
  Actions experiments. Each evidence group includes source-run provenance,
  does not necessarily correspond to the snapshot commit, and is **not** pooled.
- \`metadata/zenodo.json\`: upload metadata to enter or import into Zenodo.
- \`metadata/CITATION.cff\`: citation proposal; update after the DOI is minted.
- \`metadata/evidence_provenance.json\`: experiment runs, source revisions, scope.
- \`SHA256SUMS.txt\` and \`manifest.json\`: checksums of every payload file.

## Experimental scope

The same-commit synthetic experiment used source revision
\`3c1efa21a67ce2144c3ee1c2d567357ea29d42c0\`, not this snapshot
revision. It covers Phases 1-5 with 250 synthetic structural conversions,
250 exported smoke tests, and selected bounded TLC and mutation controls.
The external-input experiment evaluates 45 independently curated class UML
models using a lossy, conservative adapter. The MoDeS3 study extracts only
root-level statechart skeletons, omitting many transitions and source semantics.
The bounded interpreter experiment checks limited finite Boolean behavior
with separate TLA+/TLC and Python tests, not a general refinement theorem.

**Do not describe any of these experiments as full UML semantic
preservation, industrial deployment validation, or production reliability
measurements.** The latest manuscript is a separate writing artifact; the
software archive is intentionally structured around code and evidence.

## Reproduction

Install dependencies in \`source/backend/requirements-dev.txt\`. TLC runs also
require Java and the TLC JAR (use \`source/backend/install_tlc.py\`).
See \`source/experiments/\`, \`source/docs/\` and the CI configurations in
\`source/.github/workflows/\` for documented commands.

To cite this snapshot, first publish it in Zenodo, verify its actual DOI,
and replace the placeholder citation. Earlier historical Zenodo records
(e.g. v1.0.2) are **not** evidence of publication of this new snapshot.

## Upload steps

1. At https://zenodo.org/uploads choose **New upload**, or use **New version**
   only after checking the identity and ownership of the historical record.
2. Upload this ZIP as software, or unpack it and upload its component files.
3. Copy/check the fields in \`metadata/zenodo.json\`. Verify both creator
   attributions and the actual publication date.
4. Check license, README, and each evidence archive's provenance.
5. Save the draft, preview, and publish only after human review.
6. After publication, record the actual DOI in the paper's data/software
   availability section and README.

## Security and privacy

Only version-controlled repository files and designated experiment outputs
are present. The package builder rejects secret-like tracked filenames and
scans readable payloads for common credential patterns. This check is
best-effort and does not replace manual review before public deposit.
"""

meta = {
    "software_repository": "https://github.com/Shubha-fm/FormiPy",
    "software_commit": PINNED_SOURCE,
    "software_version": VERSION,
    "evidence": {
        key: {
            "github_actions_run": f"https://github.com/Shubha-fm/FormiPy/actions/runs/{run_id}",
            "source_commit": commit,
            "interpretation": (
                "separately executed study; do not imply same software revision as packaged source"
                if commit != PINNED_SOURCE else "same software version"
            ),
        } for key, (run_id, commit) in EVIDENCE.items()
    },
    "prior_release_reported_in_manuscript": "10.5281/zenodo.23387266 (verify manually before linking as related version)",
    "new_doi": None,
    "source_snapshot_verified_against_git": True,
}

files = {}
for p in source_files:
    fp = source / p
    if not fp.is_file() or fp.is_symlink():
        raise RuntimeError(f"Unexpected source file type: {p}")
    files["source/" + p] = fp.read_bytes()

for group in EVIDENCE:
    target = evidence_root / group
    if not target.is_dir():
        raise FileNotFoundError(f"Missing evidence group: {group}")
    evidence_files = sorted(x for x in target.rglob("*") if x.is_file())
    if not evidence_files:
        raise RuntimeError(f"Empty evidence group: {group}")
    for f in evidence_files:
        if f.is_symlink():
            raise RuntimeError("Evidence symlink rejected")
        relative = f.relative_to(target).as_posix()
        if skip_name.search(relative) or secret_file.search(relative):
            raise RuntimeError("Disallowed evidence file: " + relative)
        files["evidence/" + group + "/" + relative] = f.read_bytes()

files["metadata/zenodo.json"] = (json.dumps(zenodo_json, indent=2, ensure_ascii=False) + "\n").encode()
files["metadata/CITATION.cff"] = citation.encode()
files["metadata/evidence_provenance.json"] = (json.dumps(meta, indent=2) + "\n").encode()
files["README_ZENODO_UPLOAD.md"] = readme.encode()

# Scan probable credentials in all plaintext files, with benign exclusions for
# known test text such as access tokens as examples.
suspicious = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"(?i)(?:token|api[_-]?key|secret)\s*[=:]\s*['\"]?[A-Za-z0-9_-]{28,}"),
]
for name, data in files.items():
    if len(data) > 1_000_000:
        continue
    for pattern in suspicious:
        if pattern.search(data):
            raise RuntimeError("Possible credential found in " + name)

checksums = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
manifest = {
    "archive_label": ARCHIVE_NAME,
    "created_on": DATE,
    "publication_status": "unpublished_draft",
    "source_commit": PINNED_SOURCE,
    "source_tracked_file_count": len(source_files),
    "evidence_groups": sorted(EVIDENCE),
    "payload_file_count": len(files),
    "payload_checksums_sha256": checksums,
    "notes": "Checksums exclude SHA256SUMS.txt and manifest.json to avoid self-reference.",
}
files["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
files["SHA256SUMS.txt"] = ("".join(f"{value}  {name}\n" for name, value in checksums.items())).encode()

destination = outdir / ARCHIVE_NAME
with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
    for name, data in sorted(files.items()):
        zi = zipfile.ZipInfo(name, date_time=(2026, 11, 10, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = 0o644 << 16
        archive.writestr(zi, data)

with zipfile.ZipFile(destination) as archive:
    if archive.testzip() is not None:
        raise RuntimeError("Output ZIP integrity check failed")
    for name, digest in checksums.items():
        if hashlib.sha256(archive.read(name)).hexdigest() != digest:
            raise RuntimeError("Output payload mismatch: " + name)

print(json.dumps({
    "status": "PACKAGE_READY",
    "archive": destination.name,
    "size_bytes": destination.stat().st_size,
    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    "payload_files": len(files),
    "source_tracked_files": len(source_files),
    "evidence_groups": sorted(EVIDENCE),
    "source_commit": PINNED_SOURCE,
    "new_zenodo_doi": None,
}, indent=2))
