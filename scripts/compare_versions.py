#!/usr/bin/env python3
"""Paired V1/V2/V3 comparison. V3 parameters are frozen before supplementary reruns."""
import csv
import json
import statistics
from experiments import ROOT, run, write_csv
from supplementary_experiments import summarize


def main():
    datasets = json.loads((ROOT / 'data/manifest.json').read_text())['datasets']
    raw = []
    for version in [1,2]:
        for dataset in datasets:
            for seed in range(30):
                rows = run(ROOT / 'build/pager', ROOT / 'data' / dataset['file'],
                           'adaptive', [5,10,20,50,100], seed, adaptive_version=version)
                raw.extend({'version':version, 'dataset':dataset['name'], **r} for r in rows)
    with (ROOT/'results/raw.csv').open() as f:
        raw.extend({'version':3, **r} for r in csv.DictReader(f) if r['algorithm']=='adaptive')
    for r in raw:
        r['frames']=int(r['frames'])
    write_csv(ROOT/'results/versions_raw.csv',raw)
    summary=summarize(raw,['version','dataset','frames'])
    write_csv(ROOT/'results/versions_summary.csv',summary)
    compared=[]
    for ds in datasets:
        for frames in [5,10,20,50,100]:
            values={v:next(r['faults_mean'] for r in summary if r['version']==v and r['dataset']==ds['name'] and r['frames']==frames) for v in [1,2,3]}
            compared.append({'dataset':ds['name'],'frames':frames,'v1':values[1],'v2':values[2], 'v3':values[3],
                             'difference':values[3]-values[2], 'reduction_percent':100*(1-values[3]/values[2])})
    write_csv(ROOT/'results/version_comparison.csv',compared)
    for v in [1,2,3]:
        print(f'V{v} mean faults: {statistics.mean(r["faults_mean"] for r in summary if r["version"]==v):.6f}',flush=True)


if __name__=='__main__':main()
