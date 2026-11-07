from pathlib import Path
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import json
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from models import UMLModel, ConversionResponse
from converter import generate_tla, generate_python
from pytest_export import generate_pytest
from semantic_export import generate_semantic_export, supported_semantic_profile
from analysis import analyze, validate_model, graph_tla
from tlc import verify, available, build_spec

app = FastAPI(title="FormiPy Backend", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
ASSETS_DIR = FRONTEND_DIST / "assets"


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "FormiPy backend", "version": app.version, "analysis": "structural", "tlc_available": available(), "tlc_diagrams": ["state_machine", "use_case"]}


@app.post("/api/convert", response_model=ConversionResponse)
def convert(model: UMLModel):
    nodes, edges = validate_model(model)
    tla = generate_tla(model)
    cfg, mapping, module = "", [], ""
    if model.diagram_type in ("state_machine", "activity"):
        tla, cfg, mapping, module = graph_tla(model, nodes, edges)
    if model.diagram_type == "use_case":
        tla, cfg, mapping, module, _ = build_spec(model)
    python_code = generate_python(model)
    trace, statistics, properties, safety, warnings = analyze(model)
    return ConversionResponse(
        diagram_type=model.diagram_type,
        tla=tla,
        python_code=python_code,
        trace=trace,
        statistics=statistics,
        properties=properties,
        safety_satisfied=safety,
        result="Structural analysis completed. Temporal safety has not been checked.",
        verification_kind="structural", cfg=cfg, module_name=module, traceability=mapping,
        warnings=warnings,
    )


@app.post("/api/verify")
def verify_endpoint(model: UMLModel):
    return verify(model)


@app.post("/api/export")
def export_project(model: UMLModel):
    result = convert(model)
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", model.name).strip("_")[:80] or "Model"
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("project.json", json.dumps({"schema_version": 2, "model": model.model_dump()}, indent=2))
        archive.writestr((result.module_name or stem) + ".tla", result.tla)
        archive.writestr(stem + ".py", result.python_code)
        archive.writestr("tests/test_generated.py", generate_pytest(model, stem))
        archive.writestr("pytest.ini", "[pytest]\ntestpaths = tests\n")
        semantic_reason = supported_semantic_profile(model)
        if semantic_reason is None:
            semantic_name, semantic_python, semantic_tests = generate_semantic_export(model, stem)
            archive.writestr(semantic_name, semantic_python)
            archive.writestr("tests/test_semantic_preservation.py", semantic_tests)
            archive.writestr("semantic_profile.json", json.dumps({
                "status": "bounded_finite_semantic_check_available",
                "scope": "Flat finite Boolean state machines, explicit guards/updates, stuttering and safety",
                "not_supported": ["General UML semantics", "hierarchical/concurrent state machines",
                                  "weak fairness", "temporal response properties", "UML class/activity/sequence/use-case semantics"],
                "check": "Exhaustive finite one-step reference-oracle comparison; not a proof of arbitrary generated Python equivalence"
            }, indent=2))
        else:
            archive.writestr("semantic_profile.json", json.dumps({
                "status": "not_supported", "reason": semantic_reason,
                "notice": "The default generated Python prototype is not proved equivalent to the TLA+ model."
            }, indent=2))
        archive.writestr("analysis.json", result.model_dump_json(indent=2))
        archive.writestr("traceability.json", json.dumps(result.traceability, indent=2))
        if result.cfg:
            archive.writestr(result.module_name + ".cfg", result.cfg)
        if model.diagram_type == "state_machine" and (model.verification_safety.strip() or model.response_condition.strip()):
            behavior, behavior_cfg, behavior_mapping, behavior_module, _ = build_spec(model)
            archive.writestr(behavior_module + ".tla", behavior)
            archive.writestr(behavior_module + ".cfg", behavior_cfg)
            archive.writestr("behavior_traceability.json", json.dumps(behavior_mapping, indent=2))
        archive.writestr("README.txt", "FormiPy project export\n\nRun: python -m pip install pytest; python -m pytest -q\nGenerated smoke tests exercise the Python prototype. For supported flat state machines, an additional finite-semantics executable and exhaustive one-step oracle are included; see semantic_profile.json. These checks do not establish unrestricted UML equivalence.\n\nAnalysis is structural only. This export does not run TLC. Behavior files can be checked with TLC.\nRead analysis.json for warnings and scope.\nGraph modules ignore guard labels and concurrency.\nPython is a prototype, not proved equivalent to TLA+.\nOther diagram TLA+ outputs are draft skeletons.\n")
    return Response(buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{stem}_project.zip"'})


if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    index_file = FRONTEND_DIST / "index.html"
    requested_file = (FRONTEND_DIST / full_path).resolve()
    if not requested_file.is_relative_to(FRONTEND_DIST.resolve()) or full_path.startswith("api/"):
        raise HTTPException(404, "File not found")

    if full_path and requested_file.exists() and requested_file.is_file():
        return FileResponse(requested_file)

    if index_file.exists():
        return FileResponse(index_file)

    return {
        "status": "ok",
        "service": "FormiPy backend",
        "message": "Frontend build not found. Run: cd frontend && npm install && npm run build",
    }
