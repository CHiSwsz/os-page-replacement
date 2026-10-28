#!/usr/bin/env python3
"""Reproduce all 15 V3 candidates from the immutable V2 source, seeds 0..4.

This is tuning on supplied course traces, not held-out evaluation. Build files
are isolated so the default implementation and its API need not be rolled back.
"""
import concurrent.futures
import csv
import io
import statistics
import subprocess
from experiments import ROOT, write_csv

BASE = '3d4397108057d9dba434af5e9e66c7afa8b1f67e'


def variants(code):
    short = code.replace('History history(scaled_limit(capacity, options.history_factor));',
                         'History history(scaled_limit(capacity, capacity > 20 ? std::max(std::size_t{1}, options.history_factor / 2) : options.history_factor));')
    fast = short.replace('0.75', '0.5').replace('0.25', '0.5')
    out = {'v2': code, 'short_large': short}
    for weight in ['0.0', '0.5', '2.0']:
        out['short_dev'+weight] = short.replace('record.gap + record.deviation', 'record.gap + '+weight+' * record.deviation')
    for old, new in [('0.5', '0.5'), ('0.875', '0.125')]:
        out['short_smooth'+new] = short.replace('0.75', old).replace('0.25', new)
    out['short_overdue_gap'] = short.replace('estimate - age : age', 'estimate - age : std::max(age - estimate, record.gap)')
    out.update({
        'fast_margin10': fast.replace('aligned ? 20 : 50', 'aligned ? 10 : 50'),
        'fast_dev0.5': fast.replace('record.gap + record.deviation', 'record.gap + 0.5 * record.deviation'),
        'fast_dev0': fast.replace('record.gap + record.deviation', 'record.gap'),
        'fast_margin8': fast.replace('aligned ? 20 : 50', 'aligned ? 8 : 50'),
        'short_margin10': short.replace('aligned ? 20 : 50', 'aligned ? 10 : 50')})
    for scale in [5, 10]:
        source = fast.replace('std::size_t limit_;', 'std::size_t limit_;\n    std::size_t capacity_;')
        source = source.replace('explicit History(std::size_t limit) : limit_(limit) {}',
                                'History(std::size_t limit, std::size_t capacity) : limit_(limit), capacity_(capacity) {}')
        source = source.replace('record.gap + record.deviation', f'record.gap + record.deviation * std::min(1.0, {scale}.0 / static_cast<double>(capacity_))')
        source = source.replace('options.history_factor));', 'options.history_factor), capacity);')
        out[f'fast_capacity{scale}'] = source
    return out


def main():
    build = ROOT / 'build/v3-search'
    build.mkdir(parents=True, exist_ok=True)
    for source in ['include/paging.hpp', 'src/main.cpp', 'src/paging.cpp', 'src/adaptive.cpp']:
        (build / source.split('/')[-1]).write_bytes(subprocess.check_output(['git', 'show', f'{BASE}:{source}'], cwd=ROOT))
    candidates = variants((build/'adaptive.cpp').read_text())
    for name, code in candidates.items():
        source = build / f'{name}.cpp'
        source.write_text(code)
        subprocess.run(['g++', '-O3', '-std=c++17', '-I', str(build), str(build/'main.cpp'),
                        str(build/'paging.cpp'), str(source), '-o', str(build/name)], check=True)

    def run(task):
        name, dataset, seed = task
        out = subprocess.check_output([str(build/name), '--trace', str(ROOT/'data'/f'{dataset}.txt'),
                                       '--algorithm', 'adaptive', '--frames', '5,10,20,50,100', '--seed', str(seed)], text=True)
        return [dict(variant=name, dataset='qsort' if dataset=='sort1' else dataset, **r) for r in csv.DictReader(io.StringIO(out))]

    tasks = [(name, ds, seed) for name in candidates for ds in ['sort1', 'lu', 'mm16', 'mm32'] for seed in range(5)]
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for batch in pool.map(run, tasks):
            rows.extend(batch)
    write_csv(ROOT/'results/v3_search.csv', rows)
    for name in candidates:
        print(name, statistics.mean(int(r['faults']) for r in rows if r['variant']==name))


if __name__ == '__main__':
    main()
