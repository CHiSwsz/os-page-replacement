#!/usr/bin/env python3
"""Reproducible V4 development search. All of these are tuning data, not a holdout."""
import concurrent.futures
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import statistics
import subprocess

from experiments import ROOT, write_csv


def variants(code):
    stable = code.replace('window / 100', 'window / 20').replace('window / 8', 'window / 4')
    long = stable.replace('window(limit(capacity, options.window_factor))',
                          'window(limit(capacity, options.window_factor) * 2)')
    short = long.replace('observations(capacity, options.history_factor)',
                        'observations(capacity, capacity > 20 ? std::max(std::size_t{1}, options.history_factor / 2) : options.history_factor)')
    reset = short.replace('observations.prepare(page, now);',
                          'if (now % window == 0) for (auto& shadow : shadows) shadow = actual;\n        observations.prepare(page, now);')
    out = {'initial': code, 'stable': stable, 'long': long, 'short_history': short, 'reset': reset}
    out['no_reconcile'] = short.replace('reconcile = true', 'reconcile = false')
    out['epoch'] = short.replace('window / 4', 'window')
    out['wide_margin'] = short.replace('window / 20', 'window / 10')
    out['small_start_gap'] = short.replace('selected(capacity <= 20 ? 0 : 1)', 'selected(capacity <= 20 ? 2 : 1)')
    out['four_experts'] = short.replace('if (losses[j] < losses[best])', 'if (j != 5 && j != 6 && losses[j] < losses[best])')
    out['no_replay'] = short.replace('if (losses[j] < losses[best])', 'if (j != 3 && losses[j] < losses[best])')
    for prefix, source in [('short', short), ('reset', reset)]:
        deep = source.replace('context_length = 12', 'context_length = 32').replace('anchor_candidates = 8', 'anchor_candidates = 32')
        out[prefix + '_deep'] = deep
        wide = deep.replace('if (length > matched) { anchor = previous; matched = length; }',
                            'if (length > matched || (length == matched && std::min(horizon_, now-previous-1) > std::min(horizon_, now-anchor-1))) { anchor = previous; matched = length; }')
        wide = wide.replace('if (matched == context_length) break;',
                            'if (matched == context_length && now-anchor-1 >= horizon_) break;')
        out[prefix + '_wide'] = wide
        out[prefix + '_fallback'] = wide.replace('static_cast<double>(forecast_span_) + delay(page, now)',
                                                'std::max(static_cast<double>(forecast_span_ + 1), delay(page, now))')
    for factor in ['0.05', '0.1', '0.25', '0.5']:
        for prefix, source in [('reset', reset), ('long', short)]:
            grace = source.replace('const double estimate = policy == 5 ? record.conditional_gap : record.pattern_gap;',
                f'if (policy == 6) return age <= record.gap + std::max(2.0, {factor} * record.gap) ? std::max(0.0, record.gap - age) : age;\n            const double estimate = record.conditional_gap;')
            out[prefix + '_grace' + factor] = grace
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--signature', action='store_true')
    args = parser.parse_args()
    directory = ROOT / 'build/v4-search'
    directory.mkdir(parents=True, exist_ok=True)
    source = (ROOT / ('experiments/v4_signature_prototype.cpp' if args.signature else 'experiments/v4_prototype.cpp')).read_text()
    candidates = variants(source)
    if args.signature:
        candidates = {k: candidates[k] for k in ['short_history', 'reset', 'reset_wide']}
        cold_expr = 'record.repeated ? record.gap : record.signature_gap'
        original_expr = 'std::isfinite(record.signature_gap) ? record.signature_gap : (record.repeated ? record.gap : std::numeric_limits<double>::infinity())'
        for k, v in list(candidates.items()):
            cold = v.replace(original_expr, cold_expr)
            candidates[k+'_cold'] = cold
            for quantile in [25, 50, 75]:
                prior = cold.replace('std::size_t forecast_span_ = 0;', 'std::size_t forecast_span_ = 0;\n    std::deque<double> recent_gaps_;')
                prior = prior.replace('train_signature(record.signature, gap);',
                    'train_signature(record.signature, gap); recent_gaps_.push_back(gap); if (recent_gaps_.size() > 64) recent_gaps_.pop_front();')
                prior = prior.replace('if (tape_.size() == tape_limit_) {',
                    f'if (!updated.repeated && recent_gaps_.size() >= 8) {{ std::vector<double> samples(recent_gaps_.begin(), recent_gaps_.end()); auto mid = samples.begin() + static_cast<std::ptrdiff_t>(samples.size()*{quantile}/100); std::nth_element(samples.begin(), mid, samples.end()); updated.signature_gap = *mid; }}\n        if (tape_.size() == tape_limit_) {{')
                candidates[k+'_prior'+str(quantile)] = prior
        for k in ['short_history', 'reset', 'reset_wide']:
            combined = candidates[k].replace('std::size_t forecast_span_ = 0;', 'std::size_t forecast_span_ = 0;\n    std::deque<double> recent_gaps_;')
            combined = combined.replace('train_signature(record.signature, gap);',
                'train_signature(record.signature, gap); recent_gaps_.push_back(gap); if (recent_gaps_.size() > 64) recent_gaps_.pop_front();')
            combined = combined.replace('if (tape_.size() == tape_limit_) {',
                'if (!updated.repeated && recent_gaps_.size() >= 8) { std::vector<double> samples(recent_gaps_.begin(), recent_gaps_.end()); auto mid = samples.begin() + static_cast<std::ptrdiff_t>(samples.size()/4); std::nth_element(samples.begin(), mid, samples.end()); updated.conditional_gap = *mid; }\n        if (tape_.size() == tape_limit_) {')
            combined = combined.replace('if (policy == 5 || policy == 6) {',
                'if (policy == 5) { const auto found = records_.find(page); if (found == records_.end()) return std::numeric_limits<double>::infinity(); const auto& r = found->second; const double g = r.repeated ? r.gap : (r.conditional_gap > 0 ? r.conditional_gap : std::numeric_limits<double>::infinity()); const double age = static_cast<double>(now-r.last); return age < g ? g-age : age; }\n        if (false) {')
            candidates[k+'_combined'] = combined
            ewma = combined.replace('std::array<std::size_t, expert_count> losses{};',
                'std::array<std::size_t, expert_count> losses{};\n    std::array<double, expert_count> decayed{};')
            ewma = ewma.replace('if (losses[j] < losses[best])', 'if (decayed[j] < decayed[best])').replace('losses[selected] - losses[best] > margin', 'decayed[selected] - decayed[best] > static_cast<double>(margin)')
            ewma = ewma.replace('losses[j] += current[j];', 'losses[j] += current[j]; decayed[j] = decayed[j] * (1.0 - 1.0/static_cast<double>(window)) + current[j];')
            candidates[k+'_ewma'] = ewma
            candidates[k+'_start'] = ewma.replace('selected(capacity <= 20 ? 0 : 1)', 'selected(capacity <= 20 ? 2 : 1)')
        candidates = {'signature_'+k:v for k,v in candidates.items()}
    datasets = sorted((ROOT / 'data').glob('*.txt')) + sorted((ROOT / 'results/synthetic_traces').glob('*.txt')) + sorted((ROOT / 'results/fresh_traces').glob('*.txt'))
    datasets = [p for p in datasets if p.name != 'DataSetNote.txt']
    fieldnames = ['dataset','frames','faults','switches'] + [f'expert_faults_{i}' for i in range(7)] + [f'expert_uses_{i}' for i in range(7)]

    def evaluate(item):
        name, code = item
        cpp = directory / (name + '.cpp')
        binary = directory / name
        cpp.write_text(code)
        subprocess.run(['g++','-std=c++17','-O3','-I'+str(ROOT/'include'), str(ROOT/'experiments/v4_driver.cpp'),
                        str(ROOT/'src/paging.cpp'), str(ROOT/'src/adaptive.cpp'), str(cpp), '-o',str(binary)], check=True, capture_output=True)
        completed = subprocess.run([str(binary), *map(str, datasets)], check=True, capture_output=True, text=True)
        rows = []
        for r in csv.DictReader(io.StringIO(completed.stdout), fieldnames=fieldnames):
            r['dataset'] = str(Path(r['dataset']).relative_to(ROOT))
            rows.append({'variant':name, **r})
        write_csv(directory/(name+'.csv'), rows)
        course = statistics.mean(int(r['faults']) for r in rows if r['dataset'].startswith('data/'))
        stress = statistics.mean(int(r['faults']) for r in rows if not r['dataset'].startswith('data/'))
        print(name, round(course,2), round(stress,2), flush=True)
        return rows

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        raw = [row for group in pool.map(evaluate, candidates.items()) for row in group]
    out = ROOT/'results/v4'
    out.mkdir(exist_ok=True)
    prefix = 'signature_search' if args.signature else 'search'
    write_csv(out/(prefix+'_raw.csv'), raw)
    (out/(prefix+'_metadata.json')).write_text(json.dumps({'seed':0,'scope':'development/tuning only; course and existing synthetic traces',
        'variants':list(candidates), 'rows':len(raw), 'prototype_sha256':hashlib.sha256(source.encode()).hexdigest(),
        'trace_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in datasets}}, indent=2)+'\n')


if __name__ == '__main__':
    main()
