#!/usr/bin/env python3
"""Measure the final V5 executable, after other benchmark processes finish."""
import hashlib,json,platform,statistics,subprocess,time
from experiments import ROOT,write_csv
from learned_experiments import check_frozen
check_frozen()
binary=ROOT/'build/pager';out=ROOT/'results/v5';rows=[]
for version in [3,4,5]:
    command=[str(binary),'--trace',str(ROOT/'data/mm32.txt'),'--algorithm','adaptive','--frames','5,10,20,50,100','--adaptive-version',str(version)]
    subprocess.run(command,stdout=subprocess.DEVNULL,check=True)
    for repeat in range(5):
        start=time.perf_counter();subprocess.run(command,stdout=subprocess.DEVNULL,check=True)
        rows.append(dict(version=version,repeat=repeat,milliseconds=1000*(time.perf_counter()-start)))
write_csv(out/'timing_raw.csv',rows)
directory=ROOT/'build/v5-performance';directory.mkdir(exist_ok=True)
scaling=[]
for n in [10000,1000000]:
    path=directory/f'unique_{n}.txt'
    with path.open('w') as f:
        for i in range(n):f.write(f'{i:x}\n')
    usage=directory/'resource.txt'
    start=time.perf_counter()
    payload=json.loads(subprocess.check_output(['/usr/bin/time','-f','%e,%M','-o',str(usage),str(binary),str(path),'--format','json'],text=True))
    elapsed=time.perf_counter()-start
    assert payload['version']==5 and payload['average_faults']==n and all(r['faults']==n for r in payload['results'])
    scaling.append(dict(references=n,elapsed_seconds=elapsed,peak_rss_kib=int(usage.read_text().strip().split(',')[1]),average_faults=n))
    print(scaling[-1],flush=True)
metadata=dict(platform=platform.platform(),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),scope='Release end-to-end five-capacity simulator; includes parsing. This is simulation time, not OS page fault latency.',median_milliseconds={str(v):statistics.median(r['milliseconds'] for r in rows if r['version']==v) for v in [3,4,5]},unique_scan_scaling=scaling)
(out/'performance.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(metadata,flush=True)
