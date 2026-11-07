#!/usr/bin/env python3
"""Externally sourced Golden UML ModelSet: conservative FormiPy compatibility benchmark.

The 45 expert-curated class diagrams are downloaded from Zenodo at execution time.
This is NOT an industrial deployment study and is NOT fidelity verification:
only a subset of named classes and binary associations is adapted. Exact source
hashes, counts, skipped constructs, test outcomes and provenance are archived.
"""
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from zipfile import ZipFile
from fastapi.testclient import TestClient
from main import app

SOURCE = "https://zenodo.org/records/16985873/files/models.zip?download=1"
DOI = "10.5281/zenodo.16985873"
OUT = Path(os.getenv("FORMIPY_EXTERNAL_RESULTS", "results/softwarex_external_goldenuml"))
OUT.mkdir(parents=True, exist_ok=True)
CLIENT = TestClient(app)

def get_archive():
    with urllib.request.urlopen(
        urllib.request.Request(SOURCE, headers={"User-Agent":"FormiPy-SoftwareX-external-study/1.0"}),
        timeout=150,
    ) as response:
        blob = response.read(25_000_000)
    if not blob.startswith(b"PK"):
        raise ValueError("Zenodo did not return ZIP bytes")
    return blob

def parse_model(raw, name):
    # Deliberately conservative. No attempt to translate full UML semantics.
    text = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
    lines = [line.strip() for line in text.splitlines()]
    classnames = []
    attributes = {}
    aliases = {}
    current = None
    syntactic_declarations = 0
    for line in lines:
        if line.startswith("'") or not line:
            continue
        m = re.match(
            r'^(?:(?:abstract|static)\s+)?(class|interface|enum)\s+'
            r'(?:"([^"]+)"|([A-Za-z_][\w.]*))'
            r'(?:\s+as\s+([A-Za-z_]\w*))?', line, re.I
        )
        if m:
            syntactic_declarations += 1
            original = m.group(2) or m.group(3)
            alias = m.group(4) or original
            if original not in classnames:
                classnames.append(original)
                attributes[original] = []
            aliases[alias] = original
            if "{" in line and "}" not in line:
                current = original
            elif "{" in line and "}" in line:
                inside = line.split("{",1)[1].split("}",1)[0].strip()
                if inside:
                    attributes[original].append(inside[:100])
            else:
                current = None
            continue
        if current:
            if line.startswith("}"):
                current = None
            elif not line.startswith(("--", "..", "==", "'")):
                attributes[current].append(line[:100])
    # Case-insensitive regex for a top-level binary relation only.
    # Multiplicity is ignored, and ambiguous or n-ary lines are excluded.
    edges = []
    candidates = 0
    skipped = []
    operators = r'(?:<\|--|--\|>|<\|[.]|[.]\|>|o--|--o|\*--|--\*|--|[.][.]|[-]|[.])'
    endpoint = r'(?:"[^"]+"|[A-Za-z_][\w.]*)'
    mul = r'(?:\s+"[^"]*")?'
    relation = re.compile(r'^\s*('+endpoint+r')'+mul+r'\s*('+operators+r')\s*'+mul+r'\s*('+endpoint+r')(?:\s*:\s*.*)?$', re.I)
    for line in lines:
        if not line or line.startswith(("'", "@", "!", "#", "hide ", "skinparam ", "package ", "namespace ", "title ", "note ")):
            continue
        # Treat lines with an association operator as candidates, even if
        # syntax is unsupported or involves three classes.
        if ("--" in line or ".." in line or "<|" in line) and "{" not in line and not line.startswith("}"):
            if line.startswith(("class ", "interface ", "enum ")):
                continue
            candidates += 1
            match = relation.match(line)
            if not match:
                skipped.append(line[:180])
                continue
            a, op, b = match.groups()
            a, b = a.strip('"'), b.strip('"')
            a, b = aliases.get(a, a), aliases.get(b, b)
            if a not in classnames or b not in classnames:
                skipped.append(line[:180])
                continue
            edges.append({"id":f"rel_{len(edges)}","source":a,"target":b,
                          "type":"generalization" if "<|" in op or "|>" in op else
                                 "aggregation" if "o" in op else
                                 "composition" if "*" in op else "association"})
    project = {
        "name": "External_" + re.sub(r"\W+","_",name)[:50],
        "diagram_type": "class",
        "classes": [
            {"id":str(i), "name":cl[:160],
             "attributes":attributes[cl][:50], "methods":[]}
            for i, cl in enumerate(classnames)
        ],
        "relationships": [
            {"id":e["id"],"source":str(classnames.index(e["source"])),
             "target":str(classnames.index(e["target"])),"type":e["type"]}
            for e in edges
        ]
    }
    audit = {
        "class_declarations_seen":syntactic_declarations,
        "classes_mapped":len(classnames),
        "association_candidate_lines":candidates,
        "binary_relationships_mapped":len(edges),
        "unsupported_or_unresolved_relationship_lines":len(skipped),
        "skipped_examples":skipped[:12],
        "known_losses":["multiplicity and role constraints","visibility, inheritance semantics",
                        "UML behavioral semantics","n-ary relations and association classes",
                        "rich typed attributes and operations"],
    }
    return project,audit

def evaluate():
    blob=get_archive()
    sha=hashlib.sha256(blob).hexdigest()
    (OUT/"source_manifest.json").write_text(json.dumps({
        "dataset":"Golden UML ModelSet", "doi":DOI,"source_url":SOURCE,
        "archive_sha256":sha,"size_bytes":len(blob),
        "source_type":"externally curated UML teaching/research class models",
        "not_industrial_deployment_evidence":True,
        "source_code_redistributed":False
    },indent=2))
    records=[]
    with ZipFile(io.BytesIO(blob)) as z:
        files=sorted(n for n in z.namelist() if n.endswith("/plantuml.txt"))
        if len(files)!=45:
            raise AssertionError(f"Expected 45 independently curated models, received {len(files)}")
        for filename in files:
            name=filename.split("/")[0]
            raw=z.read(filename).decode("utf-8",errors="replace")
            project,audit=parse_model(raw,name)
            metadata=next((z.read(n).decode("utf-8",errors="replace")
                           for n in (name+"/metadata.txt",) if n in z.namelist()),"")
            domain=re.search(r"(?m)^domain:\s*(.*)$",metadata)
            source=re.search(r"(?m)^source:\s*(.*)$",metadata)
            t0=time.perf_counter()
            response=CLIENT.post("/api/convert",json=project)
            ms=round((time.perf_counter()-t0)*1000,4)
            valid=response.status_code==200
            parsed=response.json()
            if valid and parsed.get("verification_kind")!="structural":
                raise AssertionError("Class conversion incorrectly reported TLC verification")
            exported=CLIENT.post("/api/export",json=project) if valid else None
            py_status="NOT_RUN"
            if valid and exported and exported.status_code==200:
                with tempfile.TemporaryDirectory(prefix="formipy_external_") as temp:
                    folder=Path(temp)
                    with ZipFile(io.BytesIO(exported.content)) as pkg:
                        for item in ("pytest.ini","tests/test_generated.py",project["name"]+".py"):
                            path=folder/item
                            path.parent.mkdir(parents=True,exist_ok=True)
                            path.write_bytes(pkg.read(item))
                    cmd=subprocess.run([sys.executable,"-m","pytest","-q",
                                        "-p","no:cacheprovider"],cwd=folder,
                                       capture_output=True,text=True,timeout=45)
                    py_status="PASS" if cmd.returncode==0 else "FAIL"
                    if py_status!="PASS":
                        (OUT/(name+"_pytest.log")).write_text(cmd.stdout+"\n"+cmd.stderr)
            item={
                "case":name,"domain":domain.group(1) if domain else "",
                "source":source.group(1) if source else "",
                "source_file_sha256":hashlib.sha256(z.read(filename)).hexdigest(),
                "class_declarations":audit["class_declarations_seen"],
                "classes_mapped":audit["classes_mapped"],
                "relation_candidates":audit["association_candidate_lines"],
                "relations_mapped":audit["binary_relationships_mapped"],
                "unsupported_relations":audit["unsupported_or_unresolved_relationship_lines"],
                "http_code":response.status_code,
                "structural_conversion_pass":int(valid),
                "exported_pytest":py_status,
                "latency_ms":ms
            }
            records.append(item)
            (OUT/(name+"_audit.json")).write_text(json.dumps(audit,indent=2))
            if not valid:
                (OUT/(name+"_error.json")).write_text(json.dumps(parsed,indent=2))
            print("EXTERNAL_CASE="+json.dumps(item),flush=True)
    with (OUT/"case_results.csv").open("w",newline="") as fh:
        writer=csv.DictWriter(fh,fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    summary={
        "source_commit":os.getenv("GITHUB_SHA","local"),
        "dataset_doi":DOI,
        "archive_sha256":sha,
        "cases":len(records),
        "with_mapped_classes":sum(r["classes_mapped"]>0 for r in records),
        "structural_conversion_pass":sum(r["structural_conversion_pass"] for r in records),
        "pytest_pass":sum(r["exported_pytest"]=="PASS" for r in records),
        "class_declarations_total":sum(r["class_declarations"] for r in records),
        "mapped_classes_total":sum(r["classes_mapped"] for r in records),
        "relation_candidates_total":sum(r["relation_candidates"] for r in records),
        "mapped_relations_total":sum(r["relations_mapped"] for r in records),
        "unsupported_relations_total":sum(r["unsupported_relations"] for r in records),
        "limits":[
            "Independent expert-curated educational/research UML corpus, not deployed industrial projects.",
            "Conservative class/relationship mapping is NOT full PlantUML support.",
            "Class model export and structural validation only; no TLC checking for class diagrams.",
            "No evaluation of full UML semantic preservation or equivalent generated Python behavior.",
            "Original upstream source files are not republished; archive provenance and SHA256 retained."
        ]
    }
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2))
    print("FORMIPY_EXTERNAL_SUMMARY="+json.dumps(summary),flush=True)
    print("FORMIPY_EXTERNAL_COMPLETE",flush=True)

if __name__=="__main__":
    evaluate()
