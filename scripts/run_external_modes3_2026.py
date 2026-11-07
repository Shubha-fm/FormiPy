#!/usr/bin/env python3
"""Evaluate two external Yakindu/SCT railway engineering statecharts.

Published MoDeS3 section/turnout SCT files are sourced at a pinned upstream
commit, not recreated by FormiPy authors. We extract ONLY root-region vertices
and root-local transitions, omitting nested/orthogonal states and all event,
guard, and action semantics. Structural test only; never claim TLC safety proof.
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
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile
from fastapi.testclient import TestClient
from main import app

UPSTREAM_SHA="46a494ed16a11984175022239f8a48beee4b6461"
BASE="https://raw.githubusercontent.com/ftsrg/BME-MODES3/"+UPSTREAM_SHA+"/src/java/components/safetylogic/componentlevel.sc.model/model/"
NAMES=["Section","Turnout"]
OUT=Path(os.environ.get("FORMIPY_RAIL_RESULTS","results/softwarex_external_modes3"))
OUT.mkdir(parents=True,exist_ok=True)
CLIENT=TestClient(app)
XML_ID="{http://www.omg.org/XMI}id"
XSI_TYPE="{http://www.w3.org/2001/XMLSchema-instance}type"

def fetch(name):
    url=BASE+name+".sct"
    req=urllib.request.Request(url,headers={"User-Agent":"FormiPy-external-engineering-study/1.0"})
    with urllib.request.urlopen(req,timeout=90) as r:
        payload=r.read(2_000_000)
    return url,payload

def adapt(name, source):
    root=ET.fromstring(source)
    statechart=next((node for node in root.iter() if node.tag.endswith("Statechart")),None)
    if statechart is None:
        raise ValueError("No Yakindu statechart element")
    regions=[e for e in statechart if e.tag.endswith("regions")]
    if not regions:
        raise ValueError("No root regions")
    root_vertices=[]
    for region in regions:
        root_vertices.extend(v for v in region if v.tag.endswith("vertices"))
    all_vertices=[v for v in statechart.iter() if v.tag.endswith("vertices")]
    state_vertices=[v for v in root_vertices if v.attrib.get(XSI_TYPE,"").endswith(":State")]
    entry_vertices=[v for v in root_vertices if v.attrib.get(XSI_TYPE,"").endswith(":Entry")]
    if not state_vertices:
        raise ValueError("No root-level named states")
    names_by_id={x.attrib[XML_ID]:x.attrib.get("name") or "unnamed"
                 for x in state_vertices if XML_ID in x.attrib}
    top_ids=set(names_by_id)
    transitions=[]
    total_transitions=0
    omitted_transitions=0
    for vertex in all_vertices:
        for edge in vertex:
            if not edge.tag.endswith("outgoingTransitions"):
                continue
            total_transitions+=1
            from_id=vertex.attrib.get(XML_ID)
            target=edge.attrib.get("target")
            if from_id in top_ids and target in top_ids:
                transitions.append({"id":f"edge_{len(transitions)}","source":from_id,"target":target,
                                    "label":edge.attrib.get("specification","")[:180]})
            else:
                omitted_transitions+=1
    states=[{"id":vid,"name":name,"type":"state"} for vid,name in names_by_id.items()]
    # Root states are used directly: entry pseudostate paths are omitted.
    project={"name":"ExternalRail_"+name,"diagram_type":"state_machine",
             "states":states,"transitions":transitions}
    audit={
        "source_file_sha256":hashlib.sha256(source).hexdigest(),
        "root_regions":len(regions),
        "all_vertices":len(all_vertices),
        "root_vertices":len(root_vertices),
        "root_named_states":len(states),
        "nested_or_pseudostate_vertices":len(all_vertices)-len(states),
        "all_outgoing_transitions":total_transitions,
        "root_to_root_transitions":len(transitions),
        "transitions_omitted":omitted_transitions,
        "source_event_guard_action_semantics_preserved":False,
        "model_semantics_preserved":False,
        "explicit_tlc_properties_checked":False,
        "model_source":"Independent research railway demonstrator, NOT commercial deployment",
    }
    return project,audit

rows=[]
for name in NAMES:
    url,source=fetch(name)
    project,audit=adapt(name,source)
    folder=OUT/name
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"audit.json").write_text(json.dumps(audit,indent=2))
    (folder/"adapter_model.json").write_text(json.dumps(project,indent=2))
    resp=CLIENT.post("/api/convert",json=project)
    valid=resp.status_code==200 and resp.json().get("verification_kind")=="structural"
    (folder/"response.json").write_text(json.dumps(resp.json(),indent=2) if valid else resp.text)
    py_status="NOT_RUN"
    if valid:
        export=CLIENT.post("/api/export",json=project)
        if export.status_code!=200:
            raise AssertionError(f"{name}: export HTTP {export.status_code}")
        with tempfile.TemporaryDirectory(prefix="formipy_modes3_") as tmp:
            root=Path(tmp)
            with ZipFile(io.BytesIO(export.content)) as z:
                for file in ("pytest.ini","tests/test_generated.py",project["name"]+".py"):
                    target=root/file
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(z.read(file))
            proc=subprocess.run([sys.executable,"-m","pytest","-q",
                "-p","no:cacheprovider"],cwd=root,capture_output=True,text=True,timeout=45)
            py_status="PASS" if proc.returncode==0 else "FAIL"
            (folder/"pytest.log").write_text(proc.stdout+"\n"+proc.stderr)
    row={"name":name,"source_url":url,"source_file_sha256":audit["source_file_sha256"],
         "all_vertices":audit["all_vertices"],"root_named_states":audit["root_named_states"],
         "all_transitions":audit["all_outgoing_transitions"],
         "mapped_transitions":audit["root_to_root_transitions"],
         "omitted_transitions":audit["transitions_omitted"],
         "http_status":resp.status_code,"structural_success":int(valid),"pytest":py_status}
    print("MODES3_CASE="+json.dumps(row),flush=True)
    rows.append(row)
with (OUT/"results.csv").open("w",newline="") as fh:
    writer=csv.DictWriter(fh,fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
summary={
    "source_commit":os.getenv("GITHUB_SHA","local"),
    "external_project":"ftsrg/BME-MODES3",
    "upstream_commit":UPSTREAM_SHA,
    "cases":len(rows),
    "structural_successes":sum(r["structural_success"] for r in rows),
    "pytest_passes":sum(r["pytest"]=="PASS" for r in rows),
    "total_original_states_or_entries":sum(r["all_vertices"] for r in rows),
    "root_states_mapped":sum(r["root_named_states"] for r in rows),
    "original_transitions":sum(r["all_transitions"] for r in rows),
    "top_level_transitions_mapped":sum(r["mapped_transitions"] for r in rows),
    "limits":[
        "External research railway demonstrator, not a commercial industrial deployment.",
        "Top-level statechart skeleton only; nested/concurrent regions omitted.",
        "All Yakindu event, guard and action semantics omitted.",
        "Structural analysis only, no TLC safety verification or meaningful simulation equivalence.",
        "Passing Python smoke tests does not validate original statechart behavior."
    ]
}
(OUT/"summary.json").write_text(json.dumps(summary,indent=2))
print("FORMIPY_MODES3_SUMMARY="+json.dumps(summary),flush=True)
print("FORMIPY_MODES3_COMPLETE",flush=True)
