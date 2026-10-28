#!/usr/bin/env python3
"""V4 experiments, separated into course, development, holdout and parameter suites."""
import argparse
import concurrent.futures
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics

from experiments import ROOT, run, write_csv
from supplementary_experiments import summarize

FRAMES = [5,10,20,50,100]
OUT = ROOT/'results/v4'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def holdouts():
    """Constructed after the V4 rule was frozen; never use these to select defaults."""
    rng = random.Random(20261029)
    cases = {}
    for exponent in [1.05, 1.5]:
        cases['zipf_'+str(exponent).replace('.','_')] = rng.choices(range(1024), weights=[1/(i+1)**exponent for i in range(1024)], k=12000)
    blocks, group = [], 0
    for _ in range(12000):
        if rng.random() < .08: group = rng.randrange(40)
        blocks.append(group*16 + rng.randrange(16))
    cases['markov_blocks'] = blocks
    drift = []
    for phase in range(8):
        size = [7,31,83,13][phase%4]
        drift.extend(phase*100 + rng.randrange(size) if rng.random()<.85 else 10000+rng.randrange(2048) for _ in range(1500))
    cases['drifting_popularity'] = drift
    noisy = []
    for cycle in range(100):
        pages = list(range(101))
        for _ in range(8):
            i,j = rng.randrange(101),rng.randrange(101)
            pages[i],pages[j] = pages[j],pages[i]
        pages[rng.randrange(101)] = 10000+cycle
        noisy.extend(pages)
    cases['noisy_cycle_101'] = noisy
    bursts = []
    for block in range(60):
        bursts.extend(rng.randrange(8) for _ in range(50))
        bursts.extend(1000+block*120+i for i in range(120))
    cases['bursts_long_scans'] = bursts
    cases['alternating_loops'] = [((i%1000)%57 if i//1000%2==0 else 1000+(i%1000)%193) for i in range(12000)]
    cases['uniform_2048'] = [rng.randrange(2048) for _ in range(12000)]
    return cases


def paths_for(suite):
    if suite == 'course':
        return [(d['name'],ROOT/'data'/d['file']) for d in json.loads((ROOT/'data/manifest.json').read_text())['datasets']]
    if suite == 'development':
        return [(p.stem,p) for folder in ['synthetic_traces','fresh_traces'] for p in sorted((ROOT/'results'/folder).glob('*.txt'))]
    directory = OUT/'holdout_traces'
    directory.mkdir(exist_ok=True)
    paths = []
    for name,pages in holdouts().items():
        path = directory/(name+'.txt')
        content = ''.join(f'{p:x}\n' for p in pages)
        path.write_text(content, encoding='utf-8')
        paths.append((name,path))
    return paths


def experiment_suite(suite, seeds, workers):
    paths = paths_for(suite)
    jobs = []
    for name,path in paths:
        jobs.append((name,path,'all',0,4))
        for seed in range(seeds):
            jobs.append((name,path,'adaptive',seed,3))
            if seed:
                jobs.extend([(name,path,'random',seed,4),(name,path,'adaptive',seed,4)])

    def execute(job):
        name,path,algorithm,seed,version = job
        rows = run(ROOT/'build/pager', path, algorithm, FRAMES, seed, adaptive_version=version)
        if version == 3:
            for row in rows: row['algorithm'] = 'adaptive_v3'
        return [{'dataset':name, **row} for row in rows]

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        raw = [r for group in pool.map(execute,jobs) for r in group]
    manifest = []
    for name,path in paths:
        pages = [int(x,16) for x in path.read_text().splitlines() if x.strip()]
        rows = [r for r in raw if r['dataset']==name]
        opt = {r['frames']:r['faults'] for r in rows if r['algorithm']=='opt'}
        for r in rows:
            assert r['references']==len(pages)
            assert len(set(pages)) <= opt[r['frames']] <= r['faults'] <= len(pages)
            assert r['evictions']==r['faults']-min(r['frames'],len(set(pages)))
            if r['algorithm'] in {'adaptive','adaptive_v3'}:
                assert sum(r[k] for k in ['policy_random','policy_lru','policy_predict'])==len(pages)
                assert r['history_peak'] <= max(32,(8 if r['frames']>20 else 16)*r['frames'])
        manifest.append({'name':name,'path':str(path.relative_to(ROOT)), 'references':len(pages),'unique_pages':len(set(pages)),'sha256':digest(path)})
    summary = summarize(raw,['dataset','frames','algorithm'])
    by_trace = []
    for name,_ in paths:
        for algorithm in ['random','fifo','opt','lfu','lru','second_chance','adaptive_v3','adaptive']:
            group = [r for r in summary if r['dataset']==name and r['algorithm']==algorithm]
            by_trace.append({'dataset':name,'algorithm':algorithm,
                'average_faults':statistics.mean(r['faults_mean'] for r in group),
                'average_fault_rate':statistics.mean(r['faults_mean']/r['references'] for r in group)})
    for suffix,rows in [('raw',raw),('summary',summary),('means',by_trace)]:
        write_csv(OUT/f'{suite}_{suffix}.csv', rows)
    (OUT/f'{suite}_metadata.json').write_text(json.dumps({'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'suite':suite,'frames':FRAMES,'seeds':list(range(seeds)),'rows':len(raw),'datasets':manifest,
        'algorithm_source':json.loads((OUT/'frozen_algorithm.json').read_text()),
        'platform':platform.platform(),'interpretation':'Constructed holdout after rule freeze; not instructor hidden tests.' if suite=='holdout'
          else 'Public course data used during development.' if suite=='course' else 'All ten cases participated in development; not holdout.'},indent=2)+'\n')
    print(suite, 'saved',len(raw),'runs;', 'V3',round(statistics.mean(r['average_faults'] for r in by_trace if r['algorithm']=='adaptive_v3'),3),
          'V4',round(statistics.mean(r['average_faults'] for r in by_trace if r['algorithm']=='adaptive'),3),flush=True)


def parameters(seeds, workers):
    jobs = [(name,path,w,h,seed) for w,h in [(2,16),(4,16),(8,16),(4,8),(4,32)]
            for name,path in paths_for('course') for seed in range(seeds)]
    def execute(job):
        name,path,w,h,seed = job
        return [{'window_factor':w,'history_factor':h,'dataset':name,**r} for r in
                run(ROOT/'build/pager',path,'adaptive',FRAMES,seed,w,h,4)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        raw=[r for group in pool.map(execute,jobs) for r in group]
    write_csv(OUT/'parameters_raw.csv',raw)
    write_csv(OUT/'parameters_summary.csv',summarize(raw,['window_factor','history_factor','dataset','frames']))
    print('parameters saved',len(raw),'runs',flush=True)


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['course','development','holdout','parameters','all'],default='all')
    parser.add_argument('--seeds',type=int,default=30)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--out',type=Path,default=OUT)
    args=parser.parse_args()
    if args.seeds<1 or args.workers<1: parser.error('seeds and workers must be positive')
    frozen=json.loads((ROOT/'results/v4/frozen_algorithm.json').read_text())
    for path,expected in frozen['source_sha256'].items():
        if digest(ROOT/path)!=expected: raise RuntimeError('Algorithm changed after freeze: '+path)
    OUT=args.out.resolve()
    OUT.mkdir(parents=True,exist_ok=True)
    if OUT != ROOT/'results/v4':
        (OUT/'frozen_algorithm.json').write_text(json.dumps(frozen,indent=2)+'\n')
    suites=['course','development','holdout','parameters'] if args.suite=='all' else [args.suite]
    for suite in suites:
        if suite=='parameters': parameters(args.seeds,args.workers)
        else: experiment_suite(suite,args.seeds,args.workers)


if __name__=='__main__':main()
