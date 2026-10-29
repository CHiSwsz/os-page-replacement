#!/usr/bin/env python3
"""Evaluate frozen V5; keep development and post-freeze validation separate."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics
from experiments import ROOT, run, write_csv
from supplementary_experiments import summarize

OUT=ROOT/'results/v5'
FRAMES=[5,10,20,50,100]
ALGORITHMS=['random','fifo','opt','lfu','lru','second_chance','adaptive_v3','adaptive_v4','adaptive_v5']

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def check_frozen():
    frozen=json.loads((ROOT/'results/v5/frozen_algorithm.json').read_text())
    for p,h in frozen['source_sha256'].items():
        if digest(ROOT/p)!=h:raise RuntimeError('V5 changed after freeze: '+p)
    return frozen

def holdouts():
    """Written and first generated after the rule freeze; no retuning on these."""
    rng=random.Random(918270501)
    cases={}
    for alpha in [.8,1.25]:
        cases[f'zipf_{alpha}']=rng.choices(range(1536),weights=[(i+1)**(-alpha) for i in range(1536)],k=14000)
    cases['shuffled_block_reuse']=[]
    for _ in range(80):
        block=list(range(157));rng.shuffle(block);cases['shuffled_block_reuse']+=block
    trace=[]
    for phase in range(12):
        period=[11,47,97,193,83,29][phase%6]
        trace.extend(1000*(phase%3)+j%period for j in range(1100))
    cases['changing_loop_periods']=trace
    trace=[]
    for cycle in range(120):
        trace.extend(rng.randrange(23) for _ in range(40))
        trace.extend(10000+cycle*70+i for i in range(70))
    cases['hot_set_with_new_scans']=trace
    trace=[]
    for i in range(14000):
        stream=rng.choices(range(3),weights=[.6,.3,.1])[0]
        trace.append(stream*1000+((i//[1,3,7][stream])%[31,89,211][stream]))
    cases['interleaved_programs']=trace
    # Explicit virtual page IDs for three matrices, 16 elements per page.
    trace=[]; n=24
    for i in range(n):
        for k in range(n):
            for j in range(n):trace.extend([(i*n+k)//16,1000+(k*n+j)//16,2000+(i*n+j)//16])
    cases['matrix_ikj_24']=trace
    trace=[]; n=18
    for t in range(12):
        for i in range(1,n-1):
            for j in range(1,n-1):
                trace.extend((t%2)*1000+(x*n+y)//8 for x,y in [(i,j),(i-1,j),(i+1,j),(i,j-1),(i,j+1)])
                trace.append(((t+1)%2)*1000+(i*n+j)//8)
    cases['double_buffer_stencil']=trace
    trace=[]
    for cycle in range(50):
        for period in [6,11,21,51,101]:trace.extend(range(period))
        trace.extend([cycle%17]*8)
    cases['capacity_boundaries']=trace
    cases['uniform_997']=[rng.randrange(997) for _ in range(14000)]
    return cases

def paths_for(suite):
    if suite=='course':return [(d['name'],ROOT/'data'/d['file']) for d in json.loads((ROOT/'data/manifest.json').read_text())['datasets']]
    if suite=='development':return [(p.stem,p) for folder in ['synthetic_traces','fresh_traces'] for p in sorted((ROOT/'results'/folder).glob('*.txt'))]
    if suite=='regression':return [(p.stem,p) for p in sorted((ROOT/'results/v4/holdout_traces').glob('*.txt'))]
    directory=ROOT/'results/v5/holdout_traces';directory.mkdir(exist_ok=True)
    paths=[]
    for name,pages in holdouts().items():
        p=directory/(name+'.txt');content=''.join(f'{x:x}\n' for x in pages)
        if p.exists():assert p.read_text()==content,'holdout generator changed'
        else:p.write_text(content)
        paths.append((name,p))
    return paths

def suite(name,seeds,workers,binary):
    frozen=check_frozen();paths=paths_for(name)
    jobs=[]
    for dataset,path in paths:
        jobs.append((dataset,path,'all',0,5))
        for seed in range(seeds):
            jobs.extend([(dataset,path,'adaptive',seed,3),(dataset,path,'adaptive',seed,4)])
            if seed:jobs.extend([(dataset,path,'random',seed,5),(dataset,path,'adaptive',seed,5)])
    def execute(job):
        dataset,path,algorithm,seed,version=job
        rows=run(binary,path,algorithm,FRAMES,seed,adaptive_version=version)
        for r in rows:
            if r['algorithm']=='adaptive':r['algorithm']=f'adaptive_v{version}'
        return [dict(dataset=dataset,**r) for r in rows]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:raw=[r for group in pool.map(execute,jobs) for r in group]
    summary=summarize(raw,['dataset','frames','algorithm'])
    means=[dict(dataset=ds,algorithm=a,average_faults=statistics.mean(r['faults_mean'] for r in summary if r['dataset']==ds and r['algorithm']==a)) for ds,_ in paths for a in ALGORITHMS]
    manifest=[]
    for ds,p in paths:
        pages=[int(x,16) for x in p.read_text().splitlines()]
        manifest.append(dict(name=ds,path=str(p.relative_to(ROOT)),sha256=digest(p),references=len(pages),unique_pages=len(set(pages))))
        lower={r['frames']:r['faults'] for r in raw if r['dataset']==ds and r['algorithm']=='opt'}
        for r in raw:
            if r['dataset']!=ds:continue
            assert len(set(pages))<=lower[r['frames']]<=r['faults']<=len(pages)
            assert r['faults']+r['hits']==len(pages)
            assert r['evictions']==r['faults']-min(r['frames'],len(set(pages)))
    for suffix,rows in [('raw',raw),('summary',summary),('means',means)]:write_csv(OUT/f'{name}_{suffix}.csv',rows)
    interpretation={'course':'Public course traces used for development and parameter selection.','development':'Ten constructed traces already used for V4/V5 development.','regression':'Previously inspected V4 holdout; now an existing regression suite, not a fresh blind test.','holdout':'Ten new constructed traces generated after V5 freeze, never used to change V5; not instructor hidden tests.'}[name]
    metadata=dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),suite=name,seeds=list(range(seeds)),frames=FRAMES,rows=len(raw),datasets=manifest,interpretation=interpretation,frozen_algorithm=frozen,script_sha256=digest(Path(__file__)))
    (OUT/f'{name}_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(name, len(raw),'runs', {a:round(statistics.mean(r['average_faults'] for r in means if r['algorithm']==a),4) for a in ['opt','adaptive_v3','adaptive_v4','adaptive_v5']},flush=True)

def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=['all','course','development','regression','holdout'],default='all')
    parser.add_argument('--seeds',type=int,default=30);parser.add_argument('--workers',type=int,default=6)
    parser.add_argument('--binary',type=Path,default=ROOT/'build/pager');parser.add_argument('--out',type=Path,default=OUT)
    args=parser.parse_args()
    if args.seeds<1 or args.workers<1:parser.error('positive seeds/workers required')
    OUT=args.out.resolve();OUT.mkdir(parents=True,exist_ok=True)
    for name in (['course','development','regression','holdout'] if args.suite=='all' else [args.suite]):suite(name,args.seeds,args.workers,args.binary.resolve())

if __name__=='__main__':main()
