#!/usr/bin/env python3
"""Reproduce the two exploratory sweeps from the preserved V1 commit (5 seeds)."""
import concurrent.futures
import csv
import io
from pathlib import Path
import subprocess
import tempfile
from experiments import ROOT, write_csv

BASE='a2821373ea621ce932c7b82ec55934fcd6e462b6'


def main():
    with tempfile.TemporaryDirectory(prefix='paging-exploration-') as td:
        work=Path(td)
        for name in ['src/main.cpp','src/paging.cpp','src/adaptive.cpp','include/paging.hpp']:
            path=work/name;path.parent.mkdir(exist_ok=True)
            path.write_bytes(subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT))
        original=(work/'src/adaptive.cpp').read_text()
        anchor='        const auto event = actual.access'
        variants={'legacy':original}
        for interval in [1,2,4]:
            variants[f'align{interval}']=original.replace(anchor,f'        if (i % (check_interval * {interval}) == 0) {{ for (auto& shadow : shadows) shadow = actual; }}\n'+anchor)
        for align in [False,True]:
            for margin in [10,20]:
                code=original.replace('window / 50',f'window / {margin}')
                if align:code=code.replace(anchor,'        if (i % window == 0) { for (auto& shadow : shadows) shadow = actual; }\n'+anchor)
                variants[f'{"align" if align else "legacy"}m{margin}']=code
        for name,code in variants.items():
            source=work/(name+'.cpp');source.write_text(code)
            subprocess.run(['g++','-O3','-std=c++17','-I'+str(work/'include'),str(work/'src/main.cpp'),str(work/'src/paging.cpp'),str(source),'-o',str(work/name)],check=True)
        tasks=[(v,w,h,d,s) for v in variants for w,h in [(4,16),(4,8),(8,16)] for d in ['sort1','lu','mm16','mm32'] for s in range(5)]
        def run_one(task):
            v,w,h,d,s=task
            output=subprocess.check_output([str(work/v),'--trace',str(ROOT/'data'/f'{d}.txt'),'--algorithm','adaptive','--frames','5,10,20,50,100','--seed',str(s),'--window-factor',str(w),'--history-factor',str(h)],text=True)
            return [dict(variant=v,w=w,h=h,dataset=d,**r) for r in csv.DictReader(io.StringIO(output))]
        rows=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for batch in pool.map(run_one,tasks):rows.extend(batch)
        write_csv(ROOT/'results/optimization_search_raw.csv',rows)
        print(f'Saved {len(rows)} exploratory rows; these course traces are development data.')


if __name__=='__main__':main()
