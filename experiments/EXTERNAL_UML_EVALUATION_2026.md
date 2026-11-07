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

## Verified external benchmark results (8 November 2026)

Evidence: [GitHub Actions run 42412055688](https://github.com/Shubha-fm/FormiPy/actions/runs/42412055688) on source commit `c2b7c41df32383ed44b0a82acd5ff86609328feb`.

| Measure | Observed |
|---|---:|
| Independently curated source diagrams | 45 |
| Input diagrams with recognized classes | 45 |
| Class declarations mapped into FormiPy JSON | 458/458 |
| Candidate association/relationship lines | 475 |
| Binary relationship lines mapped | 373/475 (78.5%) |
| Unsupported or unresolved relationship lines | 102/475 (21.5%) |
| Structural HTTP conversion successes | 45/45 |
| Exported Python pytest suite passes | 45/45 |
| Full UML semantic fidelity established | No |
| Class-diagram TLC verification performed | No |
| Independently sourced industrial deployed systems | 0 |

The results are from a **conservative, purpose-built PlantUML adapter**. A conversion success only means that FormiPy accepted the adapted class/relationship subset and generated executable Python code that passed the exported smoke tests. It does not mean that the original UML diagram was fully transformed, and the percentage of relationship lines mapped is a syntactic coverage measurement, **not** a semantic correctness measurement. The aggregate class declarations and candidate relationships are parsing observations and have not been independently audited against source diagrams.

The downloaded public Zenodo ZIP had SHA256:
`9e4f30bad172f06ecb510dc2b0b405a7d38ea4cbf4336cdca562638e7dbec3c9`.

### Suggested SoftwareX manuscript paragraph

We conducted an additional evaluation using the independently curated Golden UML ModelSet (Verbruggen et al., 2025; DOI: 10.5281/zenodo.16985873). The 45 externally sourced class-diagram models were adapted into FormiPy's input schema using a conservative parser for named classes and binary relationships. The adapter mapped 458 recognized class declarations and 373 of 475 candidate relationship lines (78.5%). All 45 adapted models completed structural conversion, and their exported Python smoke-test suites passed. The remaining 102 relationship candidates were unsupported or unresolved, and multiplicities, n-ary associations, and richer UML semantics were not preserved. These observations demonstrate compatibility with adapted external inputs rather than full UML fidelity, formal verification of class diagrams, or validation in deployed industrial systems.

## Second external source: MoDeS3 railway research demonstrator

We evaluated two externally authored Yakindu SCT models from the [MoDeS3 engineering demonstrator](https://github.com/ftsrg/BME-MODES3), pinned at upstream commit `46a494ed16a11984175022239f8a48beee4b6461`. The study is in [GitHub Actions run 42412269801](https://github.com/Shubha-fm/FormiPy/actions/runs/42412269801) and uses `scripts/run_external_modes3_2026.py`.

| MoDeS3 model | Original vertices | Root states retained | Original outgoing transitions | Root-to-root transitions retained | Structural conversion | Exported pytest |
|---|---:|---:|---:|---:|---|---|
| Section | 9 | 5 | 24 | 16 | PASS | PASS |
| Turnout | 21 | 2 | 25 | 2 | PASS | PASS |
| **Total** | **30** | **7** | **49** | **18** | **2/2** | **2/2** |

**Critical interpretation:** These inputs were simplified drastically. Yakindu guards, events, actions and nested/orthogonal region semantics were not preserved. The source Turnout statechart retained only two of 25 transitions in the adapted skeleton. The result is a reproducible **compatibility and expressiveness-gap experiment**, **not** a validated industrial railway case study. No TLC safety checking is claimed for these adapted cases.

### Editorial recommendation

Present the externally curated 45-model class study under “External-input compatibility evaluation”, with its mapping-loss statistics. Mention the MoDeS3 adaptation as a limitation/exploratory external engineering case, not as evidence of safety property preservation. Keep “independent industrial validation” as unfinished until a source model from an industrial organization has been independently checked for semantic fidelity and allowed to be described in the manuscript.
