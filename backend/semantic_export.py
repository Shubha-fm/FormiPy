"""A verified, bounded operational subset for FormiPy state-machine exports.

This generator does not claim general UML semantic preservation. It emits an
independent Python state-transition interpreter alongside the legacy
human-readable prototype. The test oracle exhaustively checks the declared
finite Boolean state space against the source transition relation.
"""
import ast
import itertools
import re
from fastapi import HTTPException
from tlc import build_spec


def supported_semantic_profile(model):
    if model.diagram_type != "state_machine":
        return "Only finite, flat UML state-machine diagrams are supported."
    if model.weak_fairness or model.response_condition.strip():
        return "Weak fairness and temporal response properties are unsupported."
    if len(model.verification_variables) > 4 or len(model.states) > 32 or len(model.transitions) > 100:
        return "Semantic comparison limit: four Boolean variables, 32 states, 100 transitions."
    if not model.verification_safety.strip():
        return "An explicit Boolean safety contract is required."
    try:
        build_spec(model)  # validates the same restricted expression grammar as TLC
    except (HTTPException, ValueError, SyntaxError, RecursionError):
        return "The model is outside FormiPy's finite Boolean TLC grammar."
    return None


_RUNTIME = '''"""Finite Boolean operational model for one bounded FormiPy UML state machine.

This interpreter preserves explicit control locations, Boolean guards and
updates within the documented profile. It is distinct from the default
FormiPy human-readable Python prototype and not full UML code generation.
"""
import ast

MODEL = __FORMIPY_MODEL__
VARIABLES = tuple(MODEL["verification_variables"])
STATE_IDS = tuple(node["id"] for node in MODEL["states"])
EDGES = tuple(MODEL["transitions"])


def _value(node, env):
    if isinstance(node, ast.Constant):
        if type(node.value) in (bool, str):
            return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        operand = _value(node.operand, env)
        if type(operand) is bool:
            return not operand
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        items = [_value(part, env) for part in node.values]
        if all(type(item) is bool for item in items):
            return all(items) if isinstance(node.op, ast.And) else any(items)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        if isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
            left, right = _value(node.left, env), _value(node.comparators[0], env)
            if type(left) is type(right):
                if isinstance(node.ops[0], ast.Eq):
                    return left == right
                return left != right
    raise ValueError("Unsupported guard or safety expression")


def condition(expression, state):
    env = dict(zip(("pc",) + VARIABLES, state))
    value = _value(ast.parse(expression or "True", mode="eval").body, env)
    if type(value) is not bool:
        raise ValueError("Condition must evaluate to Boolean")
    return value


def initial_state():
    root = next((node for node in MODEL["states"] if node["type"] == "initial"), MODEL["states"][0])
    return (root["id"],) + tuple(MODEL["verification_variables"].values())


def safety(state):
    return condition(MODEL["verification_safety"], state)


def successors(state):
    """Return (UML edge ID, successor state) for each enabled explicit edge.

    The TLA+ [Next]_vars stuttering step is always available separately.
    """
    if len(state) != len(VARIABLES) + 1 or state[0] not in STATE_IDS or any(type(v) is not bool for v in state[1:]):
        raise ValueError("State is outside declared finite Boolean domain")
    output = []
    for edge in EDGES:
        if edge["source"] != state[0] or not condition(edge["guard"], state):
            continue
        values = dict(zip(VARIABLES, state[1:]))
        values.update(edge["updates"])
        output.append((edge["id"], (edge["target"],) + tuple(values[key] for key in VARIABLES)))
    return output


def stutter(state):
    """Explicitly expose [Next]_vars' always-available no-op step."""
    return state


def step(state, edge_id):
    matches = [value for label, value in successors(state) if label == edge_id]
    if not matches:
        raise ValueError("Unknown or disabled transition")
    return matches[0]
'''

_TEST = '''"""Exhaustive finite operational checks against independent source oracle.

The tested property is equality of explicit one-step transitions, the initial
state, the Boolean safety truth value and the stuttering step over *all*
declared pc/Boolean valuations. TLC remains the separate formal engine.
"""
import ast
import importlib.util
import itertools
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / __FORMIPY_SEMANTIC_FILENAME__
spec = importlib.util.spec_from_file_location("formipy_finite_semantics", SOURCE)
implementation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(implementation)

MODEL = __FORMIPY_MODEL__
VARS = tuple(MODEL["verification_variables"])
IDS = tuple(node["id"] for node in MODEL["states"])


def reference_value(node, state):
    env = {"pc": state[0], **dict(zip(VARS, state[1:]))}
    if isinstance(node, ast.Constant) and type(node.value) in (bool, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        result = reference_value(node.operand, state)
        if type(result) is bool:
            return not result
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.Or, ast.And)):
        seq = [reference_value(v, state) for v in node.values]
        assert all(type(v) is bool for v in seq)
        return any(seq) if isinstance(node.op, ast.Or) else all(seq)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        a = reference_value(node.left, state)
        b = reference_value(node.comparators[0], state)
        if type(a) is type(b):
            if isinstance(node.ops[0], ast.Eq):
                return a == b
            if isinstance(node.ops[0], ast.NotEq):
                return a != b
    raise ValueError("Expression not in restricted source language")


def source_bool(text, state):
    val = reference_value(ast.parse(text or "True", mode="eval").body, state)
    if type(val) is not bool:
        raise ValueError("Expected Boolean property")
    return val


def source_edges(state):
    result = []
    for edge in MODEL["transitions"]:
        if edge["source"] != state[0] or not source_bool(edge["guard"], state):
            continue
        variable_map = dict(zip(VARS, state[1:]))
        for key, val in edge["updates"].items():
            variable_map[key] = val
        result.append((edge["id"], (edge["target"],) + tuple(variable_map[x] for x in VARS)))
    return result


def test_full_finite_one_step_semantics_and_safety():
    states_checked = 0
    for pc in IDS:
        for valuation in itertools.product((False, True), repeat=len(VARS)):
            state = (pc,) + valuation
            expected = source_edges(state)
            observed = implementation.successors(state)
            assert observed == expected, (state, expected, observed)
            assert implementation.safety(state) == source_bool(MODEL["verification_safety"], state)
            assert implementation.stutter(state) == state
            for edge_id, successor in expected:
                assert implementation.step(state, edge_id) == successor
            states_checked += 1
    assert states_checked == len(IDS) * 2 ** len(VARS)


def test_initial_state_matches_source():
    initial = next((n for n in MODEL["states"] if n["type"] == "initial"), MODEL["states"][0])
    expected = (initial["id"],) + tuple(MODEL["verification_variables"].values())
    assert implementation.initial_state() == expected


def test_disabled_edges_rejected():
    sample = implementation.initial_state()
    valid = {edge_id for edge_id, _ in source_edges(sample)}
    for edge in MODEL["transitions"]:
        if edge["id"] not in valid:
            try:
                implementation.step(sample, edge["id"])
            except ValueError:
                pass
            else:
                raise AssertionError("Disabled edge executed: " + edge["id"])
'''


def generate_semantic_export(model, stem):
    """Return runnable semantic implementation and independent finite checks.

    Raises HTTP 422 for profiles whose semantics cannot be supported.
    """
    reason = supported_semantic_profile(model)
    if reason:
        raise HTTPException(status_code=422, detail=reason)
    payload = model.model_dump()
    file_name = stem + "_finite_semantics.py"
    implementation = _RUNTIME.replace("__FORMIPY_MODEL__", repr(payload))
    tests = (_TEST.replace("__FORMIPY_MODEL__", repr(payload))
             .replace("__FORMIPY_SEMANTIC_FILENAME__", repr(file_name)))
    ast.parse(implementation)
    ast.parse(tests)
    return file_name, implementation, tests
