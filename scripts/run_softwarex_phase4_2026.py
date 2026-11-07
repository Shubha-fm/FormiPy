#!/usr/bin/env python3
"""FormiPy SoftwareX Phase 4: heterogeneous bounded TLC benchmarks.

Six distinct state-machine topologies and six distinct permission graphs;
each has a reference and a deliberately faulty variant. Exact TLC outputs
and generated Python pytest results are preserved separately. Unlike Phase 3,
this phase uses the *default exported* pytest tests, not purpose-built oracles.
No claim of independently sourced industrial models.
"""
import csv, io, json, os, platform, subprocess, sys, tempfile
from pathlib import Path
from zipfile import ZipFile
from fastapi.testclient import TestClient
from main import app

OUT = Path(os.environ.get("FORMIPY_PHASE4_RESULTS", "results/softwarex_phase4"))
OUT.mkdir(parents=True, exist_ok=True)
client = TestClient(app)

# Names capture distinct graph structures, not trivially renamed identical graphs.
TOPOLOGIES = {
    "chain": (["idle","check","safe","unsafe"], [("idle","check"),("check","safe")]),
    "fork": (["idle","left","right","safe","unsafe"], [("idle","left"),("idle","right"),("left","safe"),("right","safe")]),
    "retry": (["idle","check","retry","safe","unsafe"], [("idle","check"),("check","retry"),("retry","check"),("check","safe")]),
    "fallback": (["idle","fast","slow","safe","unsafe"], [("idle","fast"),("fast","safe"),("fast","slow"),("slow","safe")]),
    "pipeline": (["idle","stage1","stage2","stage3","safe","unsafe"], [("idle","stage1"),("stage1","stage2"),("stage2","stage3"),("stage3","safe")]),
    "cyclic": (["idle","run","pause","safe","unsafe"], [("idle","run"),("run","pause"),("pause","run"),("pause","safe")]),
}

# Six intentionally different actor/use-case association shapes.
PERMISSIONS = {
    "single_owner": (["worker","guest"],["execute","view"],[("worker","execute"),("guest","view")],("guest","execute")),
    "role_hierarchy": (["admin","editor","reader"],["read","write","delete"],[("admin","read"),("admin","write"),("admin","delete"),("editor","read"),("editor","write"),("reader","read")],("reader","delete")),
    "separation_of_duties": (["maker","checker"],["submit","approve"],[("maker","submit"),("checker","approve")],("maker","approve")),
    "department": (["clinical","finance","audit"],["diagnose","pay","inspect"],[("clinical","diagnose"),("finance","pay"),("audit","inspect")],("finance","diagnose")),
    "maintenance": (["operator","maintainer","observer"],["operate","repair","monitor"],[("operator","operate"),("maintainer","repair"),("observer","monitor")],("observer","repair")),
    "multi_tenant": (["tenantA","tenantB","support"],["dataA","dataB"],[("tenantA","dataA"),("tenantB","dataB"),("support","dataA"),("support","dataB")],("tenantA","dataB")),
}

def state_model(name, faulty):
    nodes, skeleton = TOPOLOGIES[name]
    # The added alert action is common to both variants: in the reference,
    # it moves to safe; in the mutant it moves directly to unsafe.
    # All states have stuttering via self-loop; TLC's nonterminal deadlock check
    # is therefore not responsible for pass/fail classification.
    edges = []
    for i, (source, target) in enumerate(skeleton):
        edges.append({"id":f"route{i}","source":source,"target":target,
                      "guard":"not hazard", "updates":{}})
    edges.append({"id":"raise_alert","source":"idle",
                  "target":"unsafe" if faulty else "safe",
                  "guard":"True","updates":{"hazard":True}})
    for node in nodes:
        edges.append({"id":"hold_"+node,"source":node,"target":node,"guard":"True","updates":{}})
    return {
        "name": "Topology_"+name+("_Mutant" if faulty else "_Reference"),
        "diagram_type":"state_machine",
        "verification_variables":{"hazard":False},
        "verification_safety":'not hazard or pc != "unsafe"',
        "states":[{"id":n,"name":n.title()} for n in nodes],
        "transitions":edges,
    }

def usecase_model(name, faulty):
    actor_names, cases, allowed, forbidden = PERMISSIONS[name]
    pairs = allowed + ([forbidden] if faulty else [])
    return {
        "name":"Permission_"+name+("_Mutant" if faulty else "_Reference"),
        "diagram_type":"use_case",
        "actors":[{"id":a,"name":a} for a in actor_names],
        "use_cases":[{"id":u,"name":u} for u in cases],
        "associations":[{"id":f"assoc{i}","source":a,"target":u}
                        for i,(a,u) in enumerate(pairs)],
        "forbidden_requests":[{"source":forbidden[0],"target":forbidden[1]}],
    }

rows=[]
for family, names, factory in [
    ("state_machine", list(TOPOLOGIES),state_model),
    ("use_case",list(PERMISSIONS),usecase_model),
]:
    for name in names:
        for faulty in (False,True):
            case_id=family+"_"+name+("_mutant" if faulty else "_reference")
            payload=factory(name,faulty)
            directory=OUT/case_id
            directory.mkdir(parents=True,exist_ok=True)
            (directory/"input.json").write_text(json.dumps(payload,indent=2))
            verify=client.post("/api/verify",json=payload)
            if verify.status_code!=200:
                raise AssertionError(f"{case_id}: TLC HTTP {verify.status_code}: {verify.text[:800]}")
            data=verify.json()
            (directory/"tlc_result.json").write_text(json.dumps(data,indent=2))
            (directory/"tlc.log").write_text(data.get("tlc_output",""))
            verdict=data.get("statistics",{}).get("result")
            expected="VIOLATED" if faulty else "PASSED"
            if verdict!=expected:
                raise AssertionError(f"{case_id}: expected {expected}, TLC said {verdict}")
            exported=client.post("/api/export",json=payload)
            if exported.status_code!=200:
                raise AssertionError(f"{case_id}: export HTTP {exported.status_code}")
            with tempfile.TemporaryDirectory(prefix="formipy_phase4_") as directory_name:
                root=Path(directory_name)
                with ZipFile(io.BytesIO(exported.content)) as z:
                    for item in z.namelist():
                        if item in ("pytest.ini","tests/test_generated.py",payload["name"]+".py"):
                            dest=root/item
                            dest.parent.mkdir(parents=True,exist_ok=True)
                            dest.write_bytes(z.read(item))
                proc=subprocess.run([sys.executable,"-m","pytest","-q","-p","no:cacheprovider"],
                                    cwd=root,capture_output=True,text=True,timeout=60)
                python_verdict="PASS" if proc.returncode==0 else "FAIL"
                (directory/"pytest.log").write_text(proc.stdout+"\n"+proc.stderr)
            row={
                "case_id":case_id,"family":family,"structure":name,
                "variant":"mutant" if faulty else "reference",
                "nodes":len(payload["states"]) if family=="state_machine" else len(payload["actors"])+len(payload["use_cases"]),
                "edges":len(payload["transitions"]) if family=="state_machine" else len(payload["associations"]),
                "tlc":verdict,"default_pytest":python_verdict,
                "tlc_detected_fault":int(faulty and verdict=="VIOLATED"),
                "pytest_detected_fault":int(faulty and python_verdict=="FAIL"),
                "states_generated":data.get("statistics",{}).get("states_generated"),
                "distinct_states":data.get("statistics",{}).get("distinct_states"),
            }
            rows.append(row)
            print("CASE_RESULT "+json.dumps(row),flush=True)

with (OUT/"results.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
summary={
    "source_commit":os.getenv("GITHUB_SHA","local-unrecorded"),
    "python":sys.version,"platform":platform.platform(),
    "number_of_distinct_structural_families":len(TOPOLOGIES)+len(PERMISSIONS),
    "cases":len(rows),
    "reference_cases":sum(r["variant"]=="reference" for r in rows),
    "mutant_cases":sum(r["variant"]=="mutant" for r in rows),
    "tlc_detected_mutants":sum(r["tlc_detected_fault"] for r in rows),
    "default_pytest_detected_mutants":sum(r["pytest_detected_fault"] for r in rows),
    "tlc_verdicts":[{"case":r["case_id"],"verdict":r["tlc"]} for r in rows],
    "limitations":[
        "Twelve hand-designed synthetic topology/permission structures, not independent industrial models.",
        "Exactly one controlled injected fault per structure; additional defect families are needed.",
        "Python tests are default generated smoke tests; they do not encode each TLC property.",
        "This study measures bounded TLC checking, not unrestricted formal proof or Python/TLA+ equivalence.",
        "Do not pool template-derived cases with independent external case studies.",
    ],
}
(OUT/"summary.json").write_text(json.dumps(summary,indent=2))
(OUT/"README.md").write_text(
    "# FormiPy Phase 4 benchmark evidence\n\n12 varied hand-designed synthetic structures, "
    "24 reference/mutant cases. Independent TLC checking and generated default Python pytest "
    "results. No claims of general UML-to-Python equivalence or industrial generalization.\n")
print("FORMIPY_PHASE4_SUMMARY="+json.dumps(summary),flush=True)
print("FORMIPY_PHASE4_COMPLETE",flush=True)
