#!/usr/bin/env python3
"""Development-only ablation of conditional-reuse distributions; fixed controller."""
import concurrent.futures, csv, hashlib, json, statistics, subprocess
from pathlib import Path
import explore_v5 as base

base.EXPERTS += ['two_predecessor','two_predecessor_conditional','successor','successor_conditional','neighbors','neighbors_conditional']
base.build('density')
prefix=(base.BUILD/'predictors_density_s16.cpp').read_text()
harness=(base.ROOT/'experiments/v5_harness.hpp').read_text()
harness=harness.replace('std::vector<Controller> controllers;', 'pools.resize(1);\n    std::vector<Controller> controllers;')
harness=harness.replace('{2U,4U,8U}','{8U}').replace('{1U,20U,100U}','{20U}').replace('{2U,15U}','{15U}')
(base.BUILD/'density_fixed.hpp').write_text(harness)
paths=[base.ROOT/'data'/d['file'] for d in json.loads((base.ROOT/'data/manifest.json').read_text())['datasets']]
paths+=sorted((base.ROOT/'results/synthetic_traces').glob('*.txt'))+sorted((base.ROOT/'results/fresh_traces').glob('*.txt'))
configs=[(d,16,32,4) for d in [.9,.95,.98,.995,.999]]
configs += [(.98,s,32,4) for s in [8,32,64]]
configs += [(.98,16,h,4) for h in [8,16,64,128]]
configs += [(.98,16,32,t) for t in [2,8,16]]

def execute(cfg):
    decay,samples,horizon,threshold=cfg
    name=f'd{decay}_s{samples}_h{horizon}_t{threshold}'
    model=(base.ROOT/'experiments/v5_reuse_density.hpp').read_text().replace('sample_count = 16',f'sample_count = {samples}')
    model=model.replace('*=.98',f'*={decay}').replace('capacity*32',f'capacity*{horizon}').replace('.size<4',f'.size<{threshold}')
    (base.BUILD/(name+'.hpp')).write_text(model)
    source=prefix.replace('"density_s16.hpp"',f'"{name}.hpp"').replace('"v5_harness.hpp"','"density_fixed.hpp"')
    cpp=base.BUILD/(name+'.cpp'); cpp.write_text(source)
    binary=base.BUILD/name
    subprocess.run(['g++','-std=c++17','-O3','-w','-I'+str(base.ROOT/'include'),'-I'+str(base.ROOT/'experiments'),str(cpp),'-o',str(binary)],check=True)
    raw=subprocess.check_output([str(binary),'sweep','4','16','follow',*map(str,paths)],text=True)
    rows=list(csv.DictReader(raw.splitlines()))
    for r in rows:r.update(variant=name,dataset=str(Path(r['dataset']).relative_to(base.ROOT)))
    course=statistics.mean(int(r['faults']) for r in rows if r['dataset'].startswith('data/'))
    dev=statistics.mean(int(r['faults']) for r in rows if not r['dataset'].startswith('data/'))
    print(name,course,dev,flush=True)
    return rows

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: rows=[r for group in pool.map(execute,configs) for r in group]
with (base.OUT/'density_parameters.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
sources=['src/context.cpp','experiments/v5_reuse_density.hpp','experiments/v5_harness.hpp','scripts/explore_v5.py','scripts/explore_v5_density.py']
(base.OUT/'density_parameters_metadata.json').write_text(json.dumps({'interpretation':'development only; 15 parameter candidates','configurations':configs,'experts':base.EXPERTS,'seed':0,'source_sha256':{p:hashlib.sha256((base.ROOT/p).read_bytes()).hexdigest() for p in sources},'trace_sha256':{str(p.relative_to(base.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2)+'\n')
