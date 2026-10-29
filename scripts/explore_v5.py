#!/usr/bin/env python3
"""Build a standalone delayed-label predictor prototype; development data only."""
import argparse
import concurrent.futures
import csv
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/v5/research'
BUILD=ROOT/'build/v5-search'
EXPERTS=['random','lru','ewma_gap','historical_replay','decayed_frequency','cold_prior','anchor_signature',
         'page_gap_transition','global_gap_transition','global_pair_transition','predecessor_transition',
         'pair_count_transition','gap_conditional','pair_conditional','predecessor_conditional',
         'last_gap','alternating_gap','lru2_score','gap_sequence']

def build(model='initial',samples=16):
    BUILD.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'src/context.cpp').read_text()
    source=source[:source.index('struct OnlineAdaptive::Impl')]
    header=ROOT/'experiments'/({'initial':'v5_reuse_initial.hpp','context':'v5_reuse_model.hpp','density':'v5_reuse_density.hpp','trend':'v5_reuse_trend.hpp','markov':'v5_reuse_density.hpp'}[model])
    configured=BUILD/f'{model}_s{samples}.hpp'
    configured.write_text(header.read_text().replace('sample_count = 16',f'sample_count = {samples}'))
    source=source.replace('#include "paging.hpp"',f'#include "paging.hpp"\n#include "{configured.name}"')
    source=source.replace('expert_count = 7','expert_count = '+str(len(EXPERTS)))
    source=source.replace('class Observations {','class Observations {\n    ReuseModel learned_;')
    source=source.replace(': history_limit_(limit(capacity, history_factor)),',
                          ': learned_(capacity, history_factor), history_limit_(limit(capacity, history_factor)),')
    source=source.replace('double score(Page page, std::size_t now, std::size_t policy) const {',
                          'double score(Page page, std::size_t now, std::size_t policy) const {\n        if (policy >= 7) return learned_.score(page, now, policy-7);')
    source=source.replace('void observe(Page page, std::size_t now) {','void observe(Page page, std::size_t now) {\n        learned_.observe(page, now);')
    if model!='initial':
        source=source.replace('void prepare(Page page, std::size_t now) {','void prepare(Page page, std::size_t now) {\n        learned_.prepare(page, now);')
    if model=='markov':
        source=source.replace('#include "paging.hpp"','#include "paging.hpp"\n#include "v5_markov.hpp"')
        source=source.replace('ReuseModel learned_;','MarkovForecast markov_;\n    ReuseModel learned_;')
        source=source.replace(': learned_(capacity, history_factor),',': markov_(capacity), learned_(capacity, history_factor),')
        source=source.replace('learned_.prepare(page, now);','markov_.prepare(page);\n        learned_.prepare(page, now);')
        source=source.replace('learned_.observe(page, now);','markov_.observe(page);\n        learned_.observe(page, now);')
        source=source.replace('if (policy >= 7)', 'if (policy >= 25) return markov_.score(page, learned_.score(page,now,8),policy-25);\n        if (policy >= 7)')
    harness='v5_harness_initial.hpp' if model=='initial' else 'v5_harness.hpp'
    source+=f'\n}} // namespace paging\n#include "{harness}"\n'
    cpp=BUILD/f'predictors_{model}_s{samples}.cpp'; cpp.write_text(source)
    binary=BUILD/f'predictors_{model}_s{samples}'
    subprocess.run(['g++','-std=c++17','-O3','-I'+str(ROOT/'include'),'-I'+str(ROOT/'experiments'),str(cpp),'-o',str(binary)],check=True)
    return binary

def main():
    global EXPERTS
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool')
    parser.add_argument('--model',choices=['initial','context','density','trend','markov'],default='initial')
    parser.add_argument('--samples',type=int,default=16)
    parser.add_argument('--window',type=int,default=4)
    parser.add_argument('--history',type=int,default=16)
    parser.add_argument('--mode',default='follow',choices=['follow','direct'])
    parser.add_argument('--name',default='predictors_initial')
    parser.add_argument('--no-build',action='store_true')
    args=parser.parse_args()
    if args.model!='initial': EXPERTS+=['two_predecessor','two_predecessor_conditional','successor','successor_conditional','neighbors','neighbors_conditional']
    if args.model=='trend': EXPERTS+=['linear_gap','linear_unclipped','alternating_linear','adaptive_period','multiplicative_gap','minimum_gap','strict_gap','strict_linear','strict_alternating']
    if args.model=='markov': EXPERTS+=['markov_latest_soft','markov_latest_additive','markov_modal_soft','markov_modal_additive']
    if args.pool is None: args.pool=','.join(map(str,range(len(EXPERTS))))
    binary=BUILD/f'predictors_{args.model}_s{args.samples}' if args.no_build else build(args.model,args.samples)
    paths=[ROOT/'data'/d['file'] for d in json.loads((ROOT/'data/manifest.json').read_text())['datasets']]
    paths+=sorted((ROOT/'results/synthetic_traces').glob('*.txt'))+sorted((ROOT/'results/fresh_traces').glob('*.txt'))
    OUT.mkdir(parents=True,exist_ok=True)
    output=OUT/(args.name+'.csv')
    with output.open('w') as f:
        subprocess.run([str(binary),args.pool,str(args.window),str(args.history),args.mode,*map(str,paths)],stdout=f,check=True)
    rows=list(csv.DictReader(output.open()))
    for r in rows: r['dataset']=str(Path(r['dataset']).relative_to(ROOT))
    with output.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    for group in ['course','development']:
        subset=[r for r in rows if r['dataset'].startswith('data/')==(group=='course')]
        print(group,'actual',statistics.mean(int(r['faults']) for r in subset),flush=True)
        for i,name in enumerate(EXPERTS):
            print(i,name,round(statistics.mean(int(r['expert_faults_'+str(i)]) for r in subset),3),flush=True)
    (OUT/(args.name+'_metadata.json')).write_text(json.dumps({
        'interpretation':'All inputs are development/tuning data; none are a fresh holdout.',
        'arguments':vars(args),'experts':EXPERTS,'seed':0,
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'src/context.cpp',ROOT/'experiments'/({'initial':'v5_reuse_initial.hpp','context':'v5_reuse_model.hpp','density':'v5_reuse_density.hpp','trend':'v5_reuse_trend.hpp','markov':'v5_reuse_density.hpp'}[args.model]),ROOT/'experiments'/('v5_harness_initial.hpp' if args.model=='initial' else 'v5_harness.hpp'),Path(__file__)] + ([ROOT/'experiments/v5_markov.hpp'] if args.model=='markov' else [])},
        'trace_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2)+'\n')

if __name__=='__main__': main()
