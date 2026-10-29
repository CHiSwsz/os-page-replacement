#!/usr/bin/env python3
"""Reproduce the development-only, mandatory-admission literature baselines."""
import csv,json,subprocess
from pathlib import Path
from experiments import ROOT,write_csv
binary=ROOT/'build/v5-search/baselines'
binary.parent.mkdir(parents=True,exist_ok=True)
subprocess.run(['g++','-std=c++17','-O3',str(ROOT/'experiments/v5_baselines.cpp'),'-o',str(binary)],check=True)
subprocess.run([str(binary),'--self-test'],check=True)
meta=json.loads((ROOT/'results/v5/research/literature_baselines_metadata.json').read_text())
output=subprocess.check_output([str(binary),*[str(ROOT/p) for p in meta['trace_sha256']]],text=True)
rows=list(csv.DictReader(output.splitlines()))
for r in rows:r['dataset']=str(Path(r['dataset']).relative_to(ROOT))
target=ROOT/'build/v5-search/literature_baselines.csv';write_csv(target,rows)
with (ROOT/'results/v5/research/literature_baselines.csv').open() as f:
    assert rows==list(csv.DictReader(f))
print('PASS: literature baseline results reproduced exactly')
