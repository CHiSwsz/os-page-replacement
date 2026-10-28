"""Prepare the slide builder's data from the recorded experiment CSVs."""
from pathlib import Path
import csv,json,sys
ROOT=Path(__file__).resolve().parents[1]
out=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'build/presentation'
out.mkdir(parents=True,exist_ok=True)
data={}
for name in ['summary','overall','version_comparison','synthetic_summary','parameters_summary','timing_summary']:
    with (ROOT/'results'/f'{name}.csv').open() as f:data[name]=list(csv.DictReader(f))
data['diagnostics']=json.loads((ROOT/'results/trace_diagnostics.json').read_text())
data['manifest']=json.loads((ROOT/'data/manifest.json').read_text())
(out/'data.json').write_text(json.dumps(data),encoding='utf8')
print(out/'data.json')
