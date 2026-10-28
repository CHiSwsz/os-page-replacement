#!/usr/bin/env python3
"""Measure live-mode latency and bounded-memory scaling on this host."""
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path
from experiments import ROOT, write_csv


def main():
    binary=ROOT/'build/pager'
    rows=[]
    for version in [3,4]:
        command=[str(binary),'--trace',str(ROOT/'data/mm32.txt'),'--algorithm','adaptive','--frames','5,10,20,50,100','--adaptive-version',str(version)]
        subprocess.run(command,stdout=subprocess.DEVNULL,check=True)
        for repeat in range(5):
            start=time.perf_counter()
            subprocess.run(command,stdout=subprocess.DEVNULL,check=True)
            rows.append({'case':'mm32_five_capacities','version':version,'repeat':repeat,'milliseconds':(time.perf_counter()-start)*1000})
    write_csv(ROOT/'results/v4/timing_raw.csv',rows)
    directory=ROOT/'build/v4-performance'
    directory.mkdir(exist_ok=True)
    scaling=[]
    for n in [10000,1000000]:
        trace=directory/f'unique_{n}.txt'
        with trace.open('w') as stream:
            for i in range(n): stream.write(f'{i:x}\n')
        usage=directory/'resource.txt'
        command=[str(binary),str(trace),'--format','json']
        if Path('/usr/bin/time').exists(): command=['/usr/bin/time','-f','%e,%M','-o',str(usage),*command]
        start=time.perf_counter()
        result=json.loads(subprocess.check_output(command,text=True))
        elapsed=time.perf_counter()-start
        assert all(r['faults']==n for r in result['results']) and result['average_faults']==n
        rss=int(usage.read_text().strip().split(',')[1]) if usage.exists() else None
        scaling.append({'references':n,'elapsed_seconds':elapsed,'peak_rss_kib':rss,'average_faults':result['average_faults']})
    (ROOT/'results/v4/performance.json').write_text(json.dumps({'platform':platform.platform(),
        'timing_scope':'end-to-end Release simulator, five capacities, includes parsing; not OS fault latency',
        'median_milliseconds':{str(v):statistics.median(r['milliseconds'] for r in rows if r['version']==v) for v in [3,4]},
        'unique_scan_scaling':scaling},indent=2)+'\n')
    print((ROOT/'results/v4/performance.json').read_text())


if __name__=='__main__':main()
