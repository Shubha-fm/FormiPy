#!/usr/bin/env python3
"""Inventory the independently curated Golden UML archive before conversion."""
import io, json, os, urllib.request, zipfile
from pathlib import Path
url=os.environ.get("GOLDENUML_URL","https://zenodo.org/records/16985873/files/models.zip?download=1")
request=urllib.request.Request(url,headers={"User-Agent":"FormiPy-SoftwareX-benchmark/1.0"})
with urllib.request.urlopen(request,timeout=120) as response:
    payload=response.read(25_000_000)
print("SOURCE_URL",url)
print("BYTES",len(payload))
with zipfile.ZipFile(io.BytesIO(payload)) as z:
    names=[x for x in z.namelist() if not x.endswith("/")]
    print("TOTAL_FILES",len(names))
    print("EXTENSIONS",json.dumps({ext:sum(Path(n).suffix.lower()==ext for n in names) for ext in sorted(set(Path(n).suffix.lower() for n in names))}))
    print("FIRST_PATHS",json.dumps(names[:60]))
    puml=[n for n in names if n.lower().endswith((".puml",".plantuml",".txt"))]
    for n in puml[:5]:
        data=z.read(n).decode("utf-8",errors="replace")
        print("EXAMPLE",n,repr(data[:1300]))
