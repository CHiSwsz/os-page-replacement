#!/usr/bin/env python3
"""Independently audit V4 counts, provenance, averages and delivered PPTX data."""
import csv
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import xml.etree.ElementTree as E
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/v4'


def read(name):
    with (OUT/(name+'.csv')).open() as stream:return list(csv.DictReader(stream))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(raw,summary,keys):
    groups=defaultdict(list)
    for r in raw:
        groups[tuple(r[k] for k in keys)].append(r)
        assert int(r['hits'])+int(r['faults'])==int(r['references'])
    assert len(groups)==len(summary)
    for row in summary:
        group=groups[tuple(row[k] for k in keys)]
        values=[int(r['faults']) for r in group]
        assert len(values)==int(row['runs'])
        assert math.isclose(statistics.mean(values),float(row['faults_mean']),rel_tol=1e-12)
        assert math.isclose(statistics.stdev(values) if len(values)>1 else 0,float(row['faults_stddev']),abs_tol=1e-9)
        assert min(values)==int(row['faults_min']) and max(values)==int(row['faults_max'])
    return groups


def main():
    frozen=json.loads((OUT/'frozen_algorithm.json').read_text())
    for path,expected in frozen['source_sha256'].items():assert sha(ROOT/path)==expected, path
    for suite in ['course','development','holdout']:
        meta=json.loads((OUT/(suite+'_metadata.json')).read_text())
        assert meta['seeds']==list(range(30)) and meta['frames']==[5,10,20,50,100]
        raw,summary=read(suite+'_raw'),read(suite+'_summary')
        assert len(raw)==meta['rows']
        groups=audit(raw,summary,['dataset','frames','algorithm'])
        for (ds,f,a),group in groups.items():
            assert {r['seed'] for r in group}==({str(i) for i in range(30)} if a in ['random','adaptive','adaptive_v3'] else {''})
            optimum=int(groups[(ds,f,'opt')][0]['faults'])
            assert all(int(r['faults'])>=optimum for r in group)
        for d in meta['datasets']:
            assert sha(ROOT/d['path'])==d['sha256']
            pages=[int(x,16) for x in (ROOT/d['path']).read_text().splitlines() if x.strip()]
            assert len(pages)==d['references'] and len(set(pages))==d['unique_pages']
            for r in raw:
                if r['dataset']!=d['name']:continue
                assert d['unique_pages']<=int(r['faults'])<=len(pages)
                assert int(r['evictions'])==int(r['faults'])-min(int(r['frames']),d['unique_pages'])
        for r in read(suite+'_means'):
            values=[float(x['faults_mean']) for x in summary if x['dataset']==r['dataset'] and x['algorithm']==r['algorithm']]
            assert len(values)==5 and math.isclose(float(r['average_faults']),statistics.mean(values),rel_tol=1e-12)
    parameters=read('parameters_raw')
    assert len(parameters)==3000
    pg=audit(parameters,read('parameters_summary'),['window_factor','history_factor','dataset','frames'])
    assert all({r['seed'] for r in group}=={str(i) for i in range(30)} for group in pg.values())
    with (ROOT/'results/raw.csv').open() as f:legacy=list(csv.DictReader(f))
    old={(r['dataset'],r['frames'],r['seed']):r for r in legacy if r['algorithm']=='adaptive'}
    for r in read('course_raw'):
        if r['algorithm']=='adaptive_v3':
            before=old[r['dataset'],r['frames'],r['seed']]
            assert all(r[k]==before[k] for k in before if k!='algorithm'), 'V3 historical compatibility'
    for prefix,prototype in [('search','v4_prototype.cpp'),('signature_search','v4_signature_prototype.cpp')]:
        meta=json.loads((OUT/(prefix+'_metadata.json')).read_text())
        assert sha(ROOT/'experiments'/prototype)==meta['prototype_sha256']
        assert len(read(prefix+'_raw'))==meta['rows']
        for path,expected in meta['trace_sha256'].items():assert sha(ROOT/path)==expected
    # Cleanup must not change the selected candidate's decisions on any of the
    # 14 development traces, including adversarial outcomes.
    selected=[r for r in read('signature_search_raw') if r['variant']==frozen['selected_candidate']]
    courses=json.loads((OUT/'course_metadata.json').read_text())['datasets']
    lookup={d['path']:d['name'] for d in courses}
    final=read('course_raw')+read('development_raw')
    for r in selected:
        name=lookup.get(r['dataset'],Path(r['dataset']).stem)
        actual=next(x for x in final if x['dataset']==name and x['frames']==r['frames'] and x['algorithm']=='adaptive' and x['seed']=='0')
        assert r['faults']==actual['faults'] and r['switches']==actual['policy_switches'], ('selected candidate',name,r['frames'])
    # Independent PPTX XML audit: chart values and all four appendix tables.
    ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
    course=read('course_summary');overall=read('course_means')
    with ZipFile(ROOT/'presentation/contest-v4.pptx') as z:
        slides=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
        notes=[n for n in z.namelist() if n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml')]
        assert len(slides)==len(notes)==17
        for n in notes:assert '数据与实现来源' in ''.join(E.fromstring(z.read(n)).itertext())
        algorithms=['random','fifo','opt','lfu','lru','second_chance','adaptive_v3','adaptive']
        for i,ds in enumerate(['qsort','lu','mm16','mm32'],14):
            root=E.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
            rows=[[''.join(c.itertext()) for c in row.findall('a:tc',ns)] for row in root.findall('.//a:tbl/a:tr',ns)]
            expected=[['Frames','Random','FIFO','OPT','LFU','LRU','Clock','V3','V4']]
            for f in [5,10,20,50,100]:
                values=[]
                for a in algorithms:
                    n=float(next(r['faults_mean'] for r in course if r['dataset']==ds and r['frames']==str(f) and r['algorithm']==a))
                    values.append(f'{n:,.2f}' if a in ['random','adaptive_v3'] else f'{n:,.0f}')
                expected.append([str(f),*values])
            assert rows==expected, ('PPT table',ds)
        native=E.fromstring(z.read('ppt/charts/chart1.xml'))
        got=[float(n.text) for n in native.findall('.//c:val/c:numRef/c:numCache/c:pt/c:v',ns)]
        keys=['opt','adaptive','adaptive_v3','random','lru','second_chance','fifo','lfu']
        expected=[statistics.mean(float(r['average_faults']) for r in overall if r['algorithm']==a) for a in keys]
        assert len(got)==len(expected) and all(math.isclose(a,b,rel_tol=1e-12) for a,b in zip(got,expected))
    print('PASS: V4 source/data hashes, 13,450 runs, aggregates, seeds, V3 compatibility, selected candidate, 17-slide notes and native chart/table values')


if __name__=='__main__':main()
