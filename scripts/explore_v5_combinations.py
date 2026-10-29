#!/usr/bin/env python3
"""Evaluate development-only mixtures of the delayed-label predictors."""
import csv, hashlib, json, statistics, subprocess
from pathlib import Path
from collections import defaultdict
import explore_v5 as base

base.EXPERTS += ['two_predecessor','two_predecessor_conditional','successor','successor_conditional','neighbors','neighbors_conditional']
binary=base.build('density')
source=binary.with_suffix('.cpp').read_text().replace('"v5_harness.hpp"','"v5_combinations.hpp"')
cpp=base.BUILD/'combinations.cpp'; cpp.write_text(source)
binary=base.BUILD/'combinations'
subprocess.run(['g++','-O3','-std=c++17','-I'+str(base.ROOT/'include'),'-I'+str(base.ROOT/'experiments'),str(cpp),'-o',str(binary)],check=True)
paths=[base.ROOT/'data'/d['file'] for d in json.loads((base.ROOT/'data/manifest.json').read_text())['datasets']]
paths+=sorted((base.ROOT/'results/synthetic_traces').glob('*.txt'))+sorted((base.ROOT/'results/fresh_traces').glob('*.txt'))
out=base.OUT/'combinations.csv'
with out.open('w') as f: subprocess.run([str(binary),*map(str,paths)],stdout=f,check=True)
rows=list(csv.DictReader(out.open()))
for r in rows:r['dataset']=str(Path(r['dataset']).relative_to(base.ROOT))
with out.open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
groups=defaultdict(lambda:[[],[]])
for r in rows:groups[r['variant']][0 if r['dataset'].startswith('data/') else 1].append(int(r['faults']))
print(sorted((statistics.mean(c),statistics.mean(d),n) for n,(c,d) in groups.items())[:20])
sources=['src/context.cpp','experiments/v5_reuse_density.hpp','experiments/v5_combinations.hpp','scripts/explore_v5.py','scripts/explore_v5_combinations.py']
(base.OUT/'combinations_metadata.json').write_text(json.dumps({'interpretation':'development only; 90 candidates, no holdout', 'experts':base.EXPERTS,'seed':0,'source_sha256':{p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in sources},'trace_sha256':{str(p.relative_to(base.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2)+'\n')
