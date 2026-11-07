# Externally sourced UML evaluation for SoftwareX

## External source and attribution

**Golden UML ModelSet** by Verbruggen et al. (2025), Zenodo DOI [10.5281/zenodo.16985873](https://doi.org/10.5281/zenodo.16985873). This source contains 45 curated human-authored UML **class diagrams** with corresponding metadata and requirements descriptions. Their authorship and provenance are separate from FormiPy's authors and its previous synthetic experiments.

The benchmark runner downloads the public ZIP itself from Zenodo, records the archive and per-diagram SHA256 hashes, and archives the extracted model-level results but **does not redistribute the original source diagrams**. The source archive is approximately 13 MB and includes `plantuml.txt` in each model directory.

## Conversion and analysis boundary

FormiPy does not have a general PlantUML/XMI importer. `scripts/run_external_goldenuml_2026.py` therefore uses a **purpose-built, conservative adapter** from a subset of PlantUML classes and binary relations to FormiPy's class-diagram JSON schema.

Each case audit records how many classes and binary relations were found and how many association-like expressions could not be mapped. Multiplicities, rich UML typing, n-ary associations, operation semantics, inherited behavior and packages are not preserved. Even a 200 HTTP response from the structural conversion endpoint is **not** evidence of full UML fidelity, correct semantic translation, TLC model checking, or formally verified generated Python.

For each convertible model the runner checks the `/api/convert` endpoint and executes the default exported Python pytest suite. It records invalid/adaptation failures as failures rather than silently omitting them. The run reports conversion coverage and mapping losses explicitly.

## Industrial-evidence limitation

This is an **independently curated external benchmark**, not a deployed industrial system or independent industrial model supplied by a company. It is more external than the internally constructed Phase 1–5 synthetic corpus, but does **not** satisfy a claim of industrial validation.

For a genuine industrial case study, obtain a dated, permissioned source design/model from a named industry partner, state the actual system, operating context, design ownership and source artifact/version, and agree on independent domain-expert review of translated properties and expected failure behavior. If confidentiality prevents publishing the source, publish an approved redacted artifact and complete traceability methodology.

## Additional externally available candidate

The [MoDeS3](https://github.com/ftsrg/BME-MODES3) smart-safe railway demonstrator is an externally developed, physically implemented cyber-physical research case with component statecharts and safety logic. It is **not an industrial railway deployment** and the published Yakindu/Gamma models are **not directly supported by FormiPy**. Any manually adapted finite model would have to be identified as an author-created abstraction and reviewed for fidelity before it can be reported as independent evidence.

## Run

```bash
python -m pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python scripts/run_external_goldenuml_2026.py
```

This is a repeatable external-input compatibility study, not a semantic-preservation benchmark. Always report how many of the 45 cases have class models, relationship loss, successful exports and passing pytest smoke suites. Do not use the success proportion as an estimate of industrial applicability.
