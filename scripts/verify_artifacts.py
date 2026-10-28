#!/usr/bin/env python3
"""Audit recorded counts, aggregation, data provenance and all delivered wide tables."""
from collections import defaultdict
import csv
import hashlib
import json
import math
import statistics

from experiments import ALGORITHMS, ROOT, STOCHASTIC


def read(name):
    with (ROOT/"results"/name).open() as stream:
        return list(csv.DictReader(stream))


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def aggregate_check(raw, summary, keys):
    groups=defaultdict(list)
    for row in raw:
        groups[tuple(row[k] for k in keys)].append(row)
        check(int(row["hits"])+int(row["faults"])==int(row["references"]),"raw hit/fault accounting")
    check(len(groups)==len(summary),"summary group count")
    for row in summary:
        group=groups[tuple(row[k] for k in keys)]
        faults=[int(x["faults"]) for x in group]
        check(int(row["runs"])==len(faults),"run count")
        check(math.isclose(float(row["faults_mean"]),statistics.mean(faults),rel_tol=1e-12),"mean")
        check(math.isclose(float(row["faults_stddev"]),statistics.stdev(faults) if len(faults)>1 else 0,abs_tol=1e-9),"standard deviation")
        check(int(row["faults_min"])==min(faults) and int(row["faults_max"])==max(faults),"extrema")
    return groups


def main():
    metadata=json.loads((ROOT/"results/metadata.json").read_text())
    for path,expected in metadata["source_sha256"].items():
        check(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected,f"source hash: {path}")
    for dataset in metadata["datasets"]:
        check(hashlib.sha256((ROOT/"data"/dataset["file"]).read_bytes()).hexdigest()==dataset["sha256"],"trace hash")
    raw,summary=read("raw.csv"),read("summary.csv")
    check(len(raw)==metadata["runs"] and len(summary)==metadata["summary_groups"],"metadata counts")
    groups=aggregate_check(raw,summary,["dataset","frames","algorithm"])
    for key,group in groups.items():
        seeds={int(r["seed"]) for r in group} if key[-1] in STOCHASTIC else {r["seed"] for r in group}
        check(seeds==(set(metadata["random_seeds"]) if key[-1] in STOCHASTIC else {""}),"complete seed range")
    lookup={(r["dataset"],r["frames"],r["algorithm"]):r for r in summary}
    for row in read("fault_counts_table.csv"):
        for a in ALGORITHMS:
            check(float(row[a])==float(lookup[(row["dataset"],row["frames"],a)]["faults_mean"]),"wide table value")
    for row in read("fault_counts_seed0.csv"):
        for a in ALGORITHMS:
            candidates=[r for r in groups[(row["dataset"],row["frames"],a)] if r["seed"] in {"","0"}]
            check(len(candidates)==1 and int(row[a])==int(candidates[0]["faults"]),"seed-0 table value")
    aggregate_check(read("parameters_raw.csv"),read("parameters_summary.csv"),["window_factor","history_factor","dataset","frames"])
    aggregate_check(read("synthetic_raw.csv"),read("synthetic_summary.csv"),["dataset","frames","algorithm"])
    fg=aggregate_check(read("fresh_raw.csv"),read("fresh_summary.csv"),["dataset","frames","algorithm"])
    for (_,_,algorithm),group in fg.items():
        expected=set(range(30)) if algorithm in {'random','adaptive','adaptive_v2'} else {''}
        seeds={int(r['seed']) for r in group} if algorithm in {'random','adaptive','adaptive_v2'} else {r['seed'] for r in group}
        check(seeds==expected,'fresh complete seed range')
    fresh=json.loads((ROOT/"results/fresh_metadata.json").read_text())
    check(len(read("fresh_raw.csv"))==fresh["rows"],"fresh row count")
    for case in fresh["cases"]:
        check(hashlib.sha256((ROOT/"results/fresh_traces"/(case["name"]+".txt")).read_bytes()).hexdigest()==case["sha256"],"fresh trace hash")
    versions=read("versions_raw.csv")
    vg=aggregate_check(versions,read("versions_summary.csv"),["version","dataset","frames"])
    for (version,dataset,frames),group in vg.items():
        check({int(r['seed']) for r in group}==set(range(30)),"version seed range")
        if version=='3':
            expected={r['seed']:r['faults'] for r in groups[(dataset,frames,'adaptive')]}
            check(all(r['faults']==expected[r['seed']] for r in group),'V3 agrees with formal results')
    for r in read('version_comparison.csv'):
        for v in [1,2,3]:
            expected=statistics.mean(int(x['faults']) for x in vg[(str(v),r['dataset'],r['frames'])])
            check(math.isclose(float(r[f'v{v}']),expected), 'version comparison mean')
        check(math.isclose(float(r['difference']),float(r['v3'])-float(r['v2']),abs_tol=1e-9),'version difference')
    search=read('v3_search.csv')
    check(len(search)==1500 and len({r['variant'] for r in search})==15,'complete candidate search')
    for r in search:
        if r['variant'] in {'fast_dev0','v2'}:
            version='3' if r['variant']=='fast_dev0' else '2'
            reference=next(x for x in vg[(version,r['dataset'],r['frames'])] if x['seed']==r['seed'])
            check(all(r[k]==reference[k] for k in reference if k!='version'),'exploratory/final implementation agreement')
    supplemental=json.loads((ROOT/"results/supplementary_metadata.json").read_text())
    for case in supplemental["synthetic_cases"]:
        check(hashlib.sha256((ROOT/"results/synthetic_traces"/(case["name"]+".txt")).read_bytes()).hexdigest()==case["sha256"],"synthetic trace hash")
    print("PASS: source/data hashes, raw counts, seed ranges, all aggregates and both wide count tables")


if __name__ == "__main__":
    main()
