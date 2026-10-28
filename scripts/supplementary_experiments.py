#!/usr/bin/env python3
"""Parameter sensitivity and synthetic regression/stress tests with frozen defaults."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import statistics

from experiments import ALGORITHMS, ROOT, run, write_csv


def summarize(rows, keys):
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(row[key] for key in keys)].append(row)
    output = []
    for identity, group in grouped.items():
        values = [int(row["faults"]) for row in group]
        output.append({**dict(zip(keys, identity)), "runs": len(group), "references": int(group[0]["references"]),
                       "faults_mean": statistics.mean(values),
                       "faults_stddev": statistics.stdev(values) if len(values) > 1 else 0,
                       "faults_min": min(values), "faults_max": max(values)})
    return output


def synthetic_traces():
    rng = random.Random(20261028)
    cases = {"scan_unique": list(range(6000)),
             "cycle_73": [i % 73 for i in range(6000)],
             "cycle_149": [i % 149 for i in range(6000)]}
    mixed = []
    for block in range(80):
        mixed.extend(rng.randrange(10) for _ in range(40))
        mixed.extend(1000 + 32 * block + i for i in range(32))
    cases["hot_with_scans"] = mixed
    phase = []
    for block, size in enumerate([7, 73, 12, 149]):
        phase.extend(1000 * block + (i % size) for i in range(1500))
    cases["phase_changes"] = phase
    cases["iid_uniform_256"] = [rng.randrange(256) for _ in range(6000)]
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/pager")
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument("--random-runs", type=int, default=30)
    args = parser.parse_args()
    if args.random_runs < 2:
        parser.error("At least two seeds are required")
    binary = args.binary.resolve()
    args.results.mkdir(parents=True, exist_ok=True)
    frames = [5, 10, 20, 50, 100]
    datasets = json.loads((ROOT / "data/manifest.json").read_text())["datasets"]
    variants = [(2,16), (4,16), (8,16), (4,8), (4,32)]
    with (args.results / "raw.csv").open() as stream:
        default_rows = [row for row in csv.DictReader(stream) if row["algorithm"] == "adaptive" and int(row["seed"]) < args.random_runs]
    if len(default_rows) != len(datasets) * len(frames) * args.random_runs:
        raise RuntimeError("Run main experiments with matching seed count first")
    parameter_rows = []
    for window, history in variants:
        if (window, history) == (4,16):
            parameter_rows.extend({"window_factor": window, "history_factor": history, **row} for row in default_rows)
        else:
            for dataset in datasets:
                for seed in range(args.random_runs):
                    rows = run(binary, ROOT / "data" / dataset["file"], "adaptive", frames, seed, window, history)
                    parameter_rows.extend({"window_factor": window, "history_factor": history, "dataset": dataset["name"], **row} for row in rows)
        print(f"Parameter variant window={window}, history={history} complete", flush=True)
    # CSV input uses strings, so normalize grouping fields before aggregation.
    for row in parameter_rows:
        row["frames"] = int(row["frames"])
    write_csv(args.results / "parameters_raw.csv", parameter_rows)
    write_csv(args.results / "parameters_summary.csv", summarize(parameter_rows, ["window_factor", "history_factor", "dataset", "frames"]))

    directory = args.results / "synthetic_traces"
    directory.mkdir(exist_ok=True)
    synthetic_rows, manifest = [], []
    for name, pages in synthetic_traces().items():
        path = directory / f"{name}.txt"
        path.write_text("".join(f"{page:x}\n" for page in pages))
        rows = run(binary, path, "all", frames, 0)
        for seed in range(1, args.random_runs):
            for algorithm in ["random", "adaptive"]:
                rows.extend(run(binary, path, algorithm, frames, seed))
        optimum = {row["frames"]: row["faults"] for row in rows if row["algorithm"] == "opt"}
        for row in rows:
            if not (len(set(pages)) <= row["faults"] <= len(pages)) or row["faults"] < optimum[row["frames"]]:
                raise RuntimeError("Synthetic result violates a fault-count bound")
        synthetic_rows.extend({"dataset": name, **row} for row in rows)
        manifest.append({"name": name, "references": len(pages), "unique_pages": len(set(pages)),
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print(f"Synthetic case {name}: {len(rows)} runs complete", flush=True)
    write_csv(args.results / "synthetic_raw.csv", synthetic_rows)
    write_csv(args.results / "synthetic_summary.csv", summarize(synthetic_rows, ["dataset", "frames", "algorithm"]))
    (args.results / "supplementary_metadata.json").write_text(json.dumps({
        "parameter_variants": variants, "random_seeds": list(range(args.random_runs)),
        "parameter_rows": len(parameter_rows), "synthetic_rows": len(synthetic_rows),
        "synthetic_generator_seed": 20261028, "synthetic_cases": manifest,
        "interpretation": "The six synthetic cases were already inspected in V1 and are now regression tests, not unseen validation. V3 was selected on course traces before rerunning these cases; no retuning afterward."
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
