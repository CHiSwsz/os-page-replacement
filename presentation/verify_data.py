"""Independently compare native PPTX chart/table data with experiment CSVs."""
from pathlib import Path
from zipfile import ZipFile
import csv,math,posixpath,statistics,xml.etree.ElementTree as E
ROOT=Path(__file__).resolve().parents[1]
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
REL='{http://schemas.openxmlformats.org/package/2006/relationships}'
def read(n):
    with (ROOT/'results'/f'{n}.csv').open() as f:return list(csv.DictReader(f))
rows=read('summary');algs=['random','fifo','opt','lfu','lru','second_chance','adaptive'];frames=[5,10,20,50,100];datasets=['qsort','lu','mm16','mm32']
value=lambda d,f,a:float(next(r['faults_mean'] for r in rows if r['dataset']==d and int(r['frames'])==f and r['algorithm']==a))
def text(el):return ''.join(el.itertext())
checks=0
with ZipFile(ROOT/'presentation/page-replacement.pptx') as z:
    def relations(part):
        relpath=posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')
        return {r.get('Id'):posixpath.normpath(posixpath.join(posixpath.dirname(part),r.get('Target'))) for r in E.fromstring(z.read(relpath))}
    pr=relations('ppt/presentation.xml')
    ids=E.fromstring(z.read('ppt/presentation.xml')).findall('p:sldIdLst/p:sldId',NS)
    slides=[pr[s.get('{'+NS['r']+'}id')] for s in ids]
    assert len(slides)==21
    def xml(n):return E.fromstring(z.read(slides[n-1]))
    def table(n):
        return [[''.join(t.text or '' for t in cell.findall('.//a:t',NS)) for cell in row.findall('a:tc',NS)] for row in xml(n).findall('.//a:tbl/a:tr',NS)]
    for n,ds in enumerate(datasets,16):
        expected=[['页框','Random','FIFO','OPT','LFU','LRU','Clock','V3']]
        expected.extend([[str(f),*[f'{value(ds,f,a):,.2f}' if a in ['random','adaptive'] else f'{value(ds,f,a):,.0f}' for a in algs]] for f in frames])
        assert table(n)==expected,(n,table(n),expected);checks+=35
    changes=[next(r for r in read('version_comparison') if r['dataset']==d and int(r['frames'])==f) for d,f in [('lu',50),('lu',100),('mm32',20),('mm32',50),('mm16',100),('lu',5),('qsort',20)]]
    expected=[['轨迹 / 页框','V2','V3','变化']]+[[f'{r["dataset"]} / {r["frames"]}',f'{float(r["v2"]):,.2f}',f'{float(r["v3"]):,.2f}',f'{float(r["difference"]):+,.2f}'] for r in changes]
    assert table(13)==expected;checks+=21
    params=read('parameters_summary');expected=[['窗口因子','历史因子',*datasets,'总体平均']]
    for w,h in [(2,16),(4,16),(8,16),(4,8),(4,32)]:
        group=[r for r in params if int(r['window_factor'])==w and int(r['history_factor'])==h]
        expected.append([str(w),str(h),*[f'{statistics.mean(float(r["faults_mean"]) for r in group if r["dataset"]==d):,.2f}' for d in datasets],f'{statistics.mean(float(r["faults_mean"]) for r in group):,.2f}'])
    actual=table(20)
    assert actual[0]==expected[0] and len(actual)==len(expected)
    for (w,h),row in zip([(2,16),(4,16),(8,16),(4,8),(4,32)],actual[1:]):
        assert row[:2]==[str(w),str(h)]
        group=[r for r in params if int(r['window_factor'])==w and int(r['history_factor'])==h]
        precise=[statistics.mean(float(r['faults_mean']) for r in group if r['dataset']==d) for d in datasets]+[statistics.mean(float(r['faults_mean']) for r in group)]
        for shown,source in zip(row[2:],precise):
            assert abs(float(shown.replace(',',''))-source)<=0.005000001,'two-decimal rounding tolerance'
            checks+=1
    def chart_values(n):
        part=slides[n-1];rels=relations(part);out=[]
        for ch in xml(n).findall('.//c:chart',NS):
            c=E.fromstring(z.read(rels[ch.get('{'+NS['r']+'}id')]))
            assert c.find('c:externalData',NS) is not None,'chart needs embedded workbook'
            values=[]
            for ser in c.findall('.//c:ser',NS):
                points=ser.findall('c:val/c:numRef/c:numCache/c:pt',NS)
                assert points,'native data must have workbook references'
                values.append([float(pt.find('c:v',NS).text) for pt in points])
            out.append(values)
        return out
    expected={4:[[[1]*4,[value(d,20,'adaptive')/int(next(r['references'] for r in rows if r['dataset']==d)) for d in datasets]]],
              9:[[[float(next(r['mean_faults'] for r in read('overall') if r['algorithm']==a)) for a in algs]]],
              10:[[[value(d,f,a) for f in frames] for a in algs] for d in datasets[:2]],
              11:[[[value(d,f,a) for f in frames] for a in algs] for d in datasets[2:]],
              12:[[[1]*5,[value(d,f,'adaptive')/value(d,f,'lru') for f in frames]] for d in datasets]}
    syn=read('fresh_summary');cases=['rotating_hotsets','jittered_cycle_97','returning_sets_560','hot8_scan70']
    sm=lambda d,a:statistics.mean(float(r['faults_mean']) for r in syn if r['dataset']==d and r['algorithm']==a)
    expected[14]=[[[sm(d,'adaptive_v2') for d in cases],[sm(d,'adaptive') for d in cases]]]
    for slide,charts in expected.items():
        actual=chart_values(slide);assert len(actual)==len(charts)
        for ac,ex in zip(actual,charts):
            assert len(ac)==len(ex)
            for av,ev in zip(ac,ex):
                assert len(av)==len(ev)
                for a,b in zip(av,ev):assert math.isclose(a,b,abs_tol=1e-8,rel_tol=0),(slide,a,b);checks+=1
    notes=[n for n in z.namelist() if n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml')]
    assert len(notes)==21
    for n in notes:assert '数据与实现来源' in text(E.fromstring(z.read(n)))
print(f'PASS: {checks} native chart/table numeric values agree with CSV; 21 sourced speaker notes; embedded workbooks present')
