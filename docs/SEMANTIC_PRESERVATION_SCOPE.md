# Semantic preservation: precise scope and validation

**FormiPy does not currently provide full UML semantic preservation.** General UML includes class invariants and object lifecycles, interaction semantics, action token flow, hierarchical and orthogonal statecharts, events, time, concurrency, nondeterministic scheduling and domain-specific profiles. Those behaviors are outside the legacy FormiPy-generated Python prototypes and cannot be established by successful smoke tests alone.

## Implemented bounded operational profile

This update adds an **additional executable** `<project>_finite_semantics.py` and **independent test oracle** `tests/test_semantic_preservation.py` to export ZIPs that meet all requirements:

- The input is a flat state-machine diagram represented as explicit state IDs and directed edges, with at most 32 states and 100 edges.
- There are at most four Boolean data variables with explicit initial values and Boolean constant assignments in transitions.
- Guards and the safety predicate use the same restricted typed grammar as the FormiPy TLC translation: `True`, `False`, Boolean variables, `pc == "state_id"`, `not`, `and`, `or`, `==` and `!=`.
- Every explicit transition's source, target, guard and assignments are represented in the separate generated finite-semantic interpreter. The TLA+ `[Next]_vars` stutter is exposed separately.
- Weak fairness and temporal response conditions are explicitly excluded.
- The tests enumerate **all** `state-id × Boolean-valuation` combinations (at most 512), checking enabled transition labels, target states and updates against the original diagram's independent reference interpretation. Initial state, Boolean safety truth value and stuttering are tested as well.

This is a **finite exhaustive operational relation consistency check**, not proof of general UML-to-TLA+ or UML-to-Python equivalence. The oracle and generated runtime both implement a restricted grammar, so they could still share a semantic interpretation mistake; formal TLC model checking remains a separate validation activity.

## Export behavior

The original `<project>.py` prototype and its smoke tests are **unchanged** for compatibility. For supported models the export also contains:
- `<project>_finite_semantics.py`
- `tests/test_semantic_preservation.py`
- `semantic_profile.json` with a clear scope statement

For unsupported models, the export includes `semantic_profile.json` with `status: "not_supported"` and an explicit reason, and **no semantic-preservation test files**.

The strong checks are performed with `python -m pytest -q` after extracting the export ZIP. This tests the separate finite interpreter, **not** the original prototype's implementation fidelity or full UML semantics. Never label any unsupported model as verified.

## External case-study gaps

- Golden UML ModelSet: the conservative class adapter maps 373/475 candidate relationship lines; multiplicities, typed operations, n-ary relations, inheritance behavior and constraints remain unsupported.
- MoDeS3 Section and Turnout: the adapter retained 18/49 transitions and omitted nested/orthogonal regions, guards, triggers and actions. It cannot be used to claim faithful railway behavior or safety.
- To establish strong external semantic preservation, a project must first define the exact source language and target semantics, implement a semantics-preserving transformation for that language, and validate it with an independent oracle, mutation tests and representative externally sourced models.

## Test command

```sh
python -m pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python -m unittest backend.tests.test_semantic_export -v
```

The regression suite includes a mutation that intentionally changes a generated target: the exhaustive test must fail. The archive does not contain any fabricated TLC results.
