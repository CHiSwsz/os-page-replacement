#!/usr/bin/env python3
"""Independently audit the recorded V5 evidence and provenance."""
import csv,hashlib,json,math,statistics
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as E
from verify_v4 import audit
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/v5'
def read(path):
    with path.open() as f:return list(csv.DictReader(f))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    frozen=json.loads((OUT/'frozen_algorithm.json').read_text())
    for p,h in frozen['source_sha256'].items():assert sha(ROOT/p)==h,p
    total=0
    for suite in ['course','development','regression','holdout']:
        raw=read(OUT/f'{suite}_raw.csv');summary=read(OUT/f'{suite}_summary.csv');meta=json.loads((OUT/f'{suite}_metadata.json').read_text())
        assert meta['frozen_algorithm']==frozen and meta['script_sha256']==sha(ROOT/'scripts/learned_experiments.py')
        assert meta['generated_at_utc']>frozen['frozen_at_utc']
        assert meta['frames']==[5,10,20,50,100] and meta['seeds']==list(range(30))
        assert len(raw)==meta['rows'];total+=len(raw)
        groups=audit(raw,summary,['dataset','frames','algorithm'])
        for (ds,f,a),group in groups.items():
            assert {r['seed'] for r in group}==({str(i) for i in range(30)} if a=='random' or a.startswith('adaptive') else {''})
            opt=int(groups[ds,f,'opt'][0]['faults'])
            assert all(int(r['faults'])>=opt for r in group)
        for d in meta['datasets']:
            path=ROOT/d['path'];assert sha(path)==d['sha256']
            pages=[int(x,16) for x in path.read_text().splitlines()]
            assert len(pages)==d['references'] and len(set(pages))==d['unique_pages']
            for r in raw:
                if r['dataset']!=d['name']:continue
                assert d['unique_pages']<=int(r['faults'])<=len(pages)
                assert int(r['evictions'])==int(r['faults'])-min(int(r['frames']),d['unique_pages'])
                if r['algorithm'].startswith('adaptive'):
                    assert sum(int(r[k]) for k in ['policy_random','policy_lru','policy_predict'])==len(pages)
                    assert int(r['history_peak'])<=max(32,int(r['frames'])*(8 if int(r['frames'])>20 else 16))
        for r in read(OUT/f'{suite}_means.csv'):
            vals=[float(x['faults_mean']) for x in summary if x['dataset']==r['dataset'] and x['algorithm']==r['algorithm']]
            assert len(vals)==5 and math.isclose(statistics.mean(vals),float(r['average_faults']),rel_tol=1e-12)
    historical={ (r['dataset'],r['frames'],r['algorithm'].replace('adaptive','adaptive_v4') if r['algorithm']=='adaptive' else r['algorithm'],r['seed']):r for r in read(ROOT/'results/v4/course_raw.csv') }
    for r in read(OUT/'course_raw.csv'):
        if r['algorithm']=='adaptive_v5':continue
        old=historical[r['dataset'],r['frames'],r['algorithm'],r['seed']]
        assert all(r[k]==v for k,v in old.items() if k!='algorithm'),'V3/V4 compatibility'
    research_rows=0
    for p in sorted((OUT/'research').glob('*_metadata.json')):
        meta=json.loads(p.read_text())
        for key in ['source_sha256','trace_sha256']:
            for path,h in meta[key].items():assert sha(ROOT/path)==h,(p.name,path)
        research_rows+=len(read(p.with_name(p.name.replace('_metadata.json','.csv'))))
    selected={ (r['dataset'],r['frames']):r for r in read(OUT/'research/density_parameters.csv') if r['variant']=='d0.98_s16_h8_t4' }
    for r in read(OUT/'research/production_seed0.csv'):
        old=selected[r['dataset'],r['frames']]
        assert r['faults']==old['faults'] and r['policy_switches']==old['switches']
    # Native slide chart and every appendix table must exactly match the CSV.
    ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
    with ZipFile(ROOT/'presentation/contest-v5.pptx') as z:
        slides=sorted(n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml'))
        assert len(slides)==15
        assert len([n for n in z.namelist() if n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml')])==15
        means=read(OUT/'course_means.csv');summary=read(OUT/'course_summary.csv')
        keys=['opt','adaptive_v5','adaptive_v4','adaptive_v3','random','lru','second_chance','fifo','lfu']
        got=[float(p.text) for p in E.fromstring(z.read('ppt/charts/chart1.xml')).findall('.//c:val/c:numRef/c:numCache/c:pt/c:v',ns)]
        expected=[statistics.mean(float(r['average_faults']) for r in means if r['algorithm']==a) for a in keys]
        assert len(got)==len(expected) and all(math.isclose(a,b,rel_tol=1e-12) for a,b in zip(got,expected))
        for i,ds in enumerate(['qsort','lu','mm16','mm32'],12):
            root=E.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
            rows=[[''.join(c.itertext()) for c in row.findall('a:tc',ns)] for row in root.findall('.//a:tbl/a:tr',ns)]
            keys=['random','fifo','opt','lfu','lru','second_chance','adaptive_v3','adaptive_v4','adaptive_v5']
            expected=[['Frames','Random','FIFO','OPT','LFU','LRU','Clock','V3','V4','V5']]
            for f in [5,10,20,50,100]:
                values=[float(next(r['faults_mean'] for r in summary if r['dataset']==ds and r['frames']==str(f) and r['algorithm']==a)) for a in keys]
                expected.append([str(f),*[f'{x:,.2f}' for x in values]])
            assert rows==expected,('slide',ds)
    print(f'PASS: V5 hashes, {total} final runs, {research_rows} research rows, legal counts, aggregates, seeds, legacy compatibility, prototype reproduction, 15-slide data')
if __name__=='__main__':main()
