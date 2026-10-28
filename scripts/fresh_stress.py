#!/usr/bin/env python3
"""Additional constructed workloads, defined before seeing V3 validation results."""
from pathlib import Path
import hashlib,json,random
from experiments import ROOT,run,write_csv
from supplementary_experiments import summarize


def cases():
    rng=random.Random(2718281)
    rotating=[]
    for phase in range(8):
        rotating.extend(phase*60+rng.randrange(20) if rng.random()<0.8 else 1000+rng.randrange(400) for _ in range(1200))
    jitter=[]
    for _ in range(80):
        pages=list(range(97))
        for _ in range(15):
            i=rng.randrange(96);pages[i],pages[i+1]=pages[i+1],pages[i]
        jitter.extend(pages)
    returning=[]
    for _ in range(8):
        for phase in range(7):returning.extend(phase*80+i%80 for i in range(160))
    mixed=[]
    for block in range(100):
        mixed.extend(rng.randrange(8) for _ in range(32))
        mixed.extend(1000+block*70+i for i in range(70))
    return {'rotating_hotsets':rotating,'jittered_cycle_97':jitter,'returning_sets_560':returning,'hot8_scan70':mixed}


def main():
    directory=ROOT/'results/fresh_traces';directory.mkdir(exist_ok=True)
    raw=[];manifest=[]
    for name,pages in cases().items():
        path=directory/f'{name}.txt';path.write_text(''.join(f'{p:x}\n' for p in pages))
        rows=run(ROOT/'build/pager',path,'all',[5,10,20,50,100],0)
        for seed in range(30):
            old=run(ROOT/'build/pager',path,'adaptive',[5,10,20,50,100],seed,adaptive_version=2)
            rows.extend({**r,'algorithm':'adaptive_v2'} for r in old)
            if seed:
                for algorithm in ['random','adaptive']:
                    rows.extend(run(ROOT/'build/pager',path,algorithm,[5,10,20,50,100],seed))
        lower={r['frames']:r['faults'] for r in rows if r['algorithm']=='opt'}
        for r in rows:assert len(set(pages))<=lower[r['frames']]<=r['faults']<=len(pages)
        raw.extend({'dataset':name,**r} for r in rows)
        manifest.append({'name':name,'references':len(pages),'unique_pages':len(set(pages)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        print(name,'complete',flush=True)
    write_csv(ROOT/'results/fresh_raw.csv',raw)
    write_csv(ROOT/'results/fresh_summary.csv',summarize(raw,['dataset','frames','algorithm']))
    (ROOT/'results/fresh_metadata.json').write_text(json.dumps({'generator_seed':2718281,'seeds':list(range(30)),'cases':manifest,'rows':len(raw),'interpretation':'Additional constructed stress tests, specified before their results were inspected. V3 rules frozen before this run; no retuning on these results. Not instructor hidden data.'},indent=2)+'\n')


if __name__=='__main__':main()
