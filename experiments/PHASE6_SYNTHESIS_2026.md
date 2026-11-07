# FormiPy SoftwareX: same-commit statistical synthesis

This study reruns Phases 1–5 on a **single source commit** instead of combining historical measurements from different software revisions.

## Evidence and protocol

The workflow `.github/workflows/softwarex-synthesis-2026.yml` reinstalls Python 3.12, Java 17 and TLC, runs all five experiment scripts and saves one GitHub Actions artifact containing raw CSVs, case inputs, TLC stdout, pytest output, machine manifests and an automatically generated `softwarex_synthesis/REPORT.md`.

The synthesis script `scripts/summarize_softwarex_2026.py` refuses missing inputs, unexpected sample counts, or inconsistent source commits. Its figures are recalculated from per-case CSV files, not transcribed from prior manuscript tables. Model-checking and Python tests are not considered interchangeable. The response to Reviewer 1 should report the latency distribution and bootstrap median intervals *as repeated measurements on a particular GitHub Actions runner*, not general population confidence.

## A critical historical version distinction

The original Phase 4 experiment preceded FormiPy's built-in forbidden-permission pytest tests. Phase 5 added those tests, so a fresh Phase 4 run on the current application is expected to have different Python-test coverage from its historical result. A same-commit rerun is valuable for internal consistency, but it is not a historical before/after experiment. The initial Phase 4 run and later Phase 5 run can be cited separately with their GitHub commit identifiers.

## Limits relevant to SoftwareX

- Phase 1 uses structurally simple synthetic models, not independent UML projects.
- Phase 3 reuses two template families with numbered variants, so effective independent sample size is much smaller than the number of observations.
- Phases 4 and 5 share six synthetic permission structures, so the case counts cannot be pooled as independently sampled evidence.
- Phases 2 and 4 use FormiPy-generated tests; Phase 3 uses purpose-built matched assertions.
- TLC checks bounded state-machine and use-case formal models. Generated Python prototypes are not proved behaviorally equivalent.
- No external industrial case study, independently sourced UML dataset, or broad generalization claim is supported yet.

## Next task after successful synthesis

Update the manuscript's evaluation, reproducibility, discussion and conclusion sections with phase-specific counts and limitations. Cite the exact checked commit and archive. For Reviewer 2, use the explicit difference between default smoke tests and permission-aware tests. Before final manuscript submission, inspect independent benchmark case studies and compare related work against verified publications, rather than claiming an unsupported superiority over other UML-to-formal tools.
