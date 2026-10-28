#!/usr/bin/env python3
"""Run all assigned datasets/capacities; retain every seed and aggregate results."""
import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ALGORITHMS = ["random", "fifo", "opt", "lfu", "lru", "second_chance", "adaptive"]
STOCHASTIC = {"random", "adaptive"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(binary, trace, algorithm, capacities, seed, window_factor=4, history_factor=16):
    command = [str(binary), "--trace", str(trace), "--algorithm", algorithm,
               "--frames", ",".join(map(str, capacities)), "--seed", str(seed),
               "--window-factor", str(window_factor), "--history-factor", str(history_factor)]
    completed = subprocess.run(command, capture_output=True, text=True, check=True)
    rows = list(csv.DictReader(io.StringIO(completed.stdout)))
    expected = len(capacities) * (len(ALGORITHMS) if algorithm == "all" else 1)
    if len(rows) != expected:
        raise RuntimeError(f"Expected {expected} rows; got {len(rows)}")
    for row in rows:
        for key in ["frames", "references", "hits", "faults", "evictions", "policy_random", "policy_lru",
                    "policy_predict", "policy_switches", "history_peak"]:
            row[key] = int(row[key])
        row["fault_rate"] = float(row["fault_rate"])
        if row["hits"] + row["faults"] != row["references"]:
            raise RuntimeError("Invalid hit/fault accounting")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/pager")
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--frames", type=int, nargs="+", default=[5, 10, 20, 50, 100])
    parser.add_argument("--random-runs", type=int, default=30)
    args = parser.parse_args()
    if args.random_runs < 2 or not args.frames or min(args.frames) <= 0 or len(set(args.frames)) != len(args.frames):
        parser.error("Use at least 2 random runs and distinct positive frame counts")
    args.frames.sort()
    binary = args.binary.resolve()
    datasets = json.loads((args.data / "manifest.json").read_text())["datasets"]
    raw = []
    for dataset in datasets:
        trace = args.data / dataset["file"]
        if sha256(trace) != dataset["sha256"]:
            raise RuntimeError(f"Trace checksum mismatch: {trace}")
        pages = [int(line.strip(), 16) for line in trace.read_text().splitlines() if line.strip()]
        if len(pages) != dataset["references"] or len(set(pages)) != dataset["unique_pages"]:
            raise RuntimeError(f"Trace statistics mismatch: {trace}")
        # Seed 0 includes every algorithm; stochastic policies repeat with seeds 1..29.
        runs = run(binary, trace, "all", args.frames, 0)
        for seed in range(1, args.random_runs):
            runs.extend(run(binary, trace, "random", args.frames, seed))
            runs.extend(run(binary, trace, "adaptive", args.frames, seed))
        optimum = {row["frames"]: row["faults"] for row in runs if row["algorithm"] == "opt"}
        for row in runs:
            if row["references"] != dataset["references"] or row["faults"] < optimum[row["frames"]]:
                raise RuntimeError("Invalid references or result below OPT")
            if row["faults"] < dataset["unique_pages"] or row["evictions"] != row["faults"] - min(row["frames"], dataset["unique_pages"]):
                raise RuntimeError("Invalid compulsory-fault or eviction accounting")
            raw.append({"dataset": dataset["name"], **row})
            if row["algorithm"] == "adaptive":
                if sum(row[key] for key in ["policy_random", "policy_lru", "policy_predict"]) != row["references"]:
                    raise RuntimeError("Adaptive policy accounting mismatch")
                if row["history_peak"] > max(32, 16 * row["frames"]):
                    raise RuntimeError("Adaptive history exceeded its bound")
        for algorithm in ["opt", "lru"]:
            values = [row["faults"] for row in runs if row["algorithm"] == algorithm]
            if values != sorted(values, reverse=True):
                raise RuntimeError(f"Stack-property violation for {algorithm}")
        # Independent semantic check on each real trace: enough frames => exactly one fault per unique page.
        for row in run(binary, trace, "all", [dataset["unique_pages"]], 0):
            if row["faults"] != dataset["unique_pages"] or row["evictions"] != 0:
                raise RuntimeError("Enough-memory check failed")
        print(f"{dataset['name']}: {len(runs)} runs + {len(ALGORITHMS)} enough-memory checks passed", flush=True)

    grouped = defaultdict(list)
    for row in raw:
        grouped[(row["dataset"], row["frames"], row["algorithm"])].append(row)
    summary = []
    for dataset in datasets:
        for frames in args.frames:
            for algorithm in ALGORITHMS:
                rows = grouped[(dataset["name"], frames, algorithm)]
                faults = [row["faults"] for row in rows]
                expected_runs = args.random_runs if algorithm in STOCHASTIC else 1
                if len(rows) != expected_runs:
                    raise RuntimeError("Incomplete group")
                mean = statistics.mean(faults)
                summary.append({"dataset": dataset["name"], "frames": frames, "algorithm": algorithm,
                                "runs": len(rows), "references": dataset["references"],
                                "faults_mean": mean, "faults_stddev": statistics.stdev(faults) if len(rows) > 1 else 0.0,
                                "faults_min": min(faults), "faults_max": max(faults),
                                "fault_rate_mean": mean / dataset["references"]})
    by_trace = []
    for dataset in datasets:
        for algorithm in ALGORITHMS:
            rows = [row for row in summary if row["dataset"] == dataset["name"] and row["algorithm"] == algorithm]
            by_trace.append({"dataset": dataset["name"], "algorithm": algorithm,
                             "mean_faults_over_capacities": statistics.mean(row["faults_mean"] for row in rows),
                             "mean_fault_rate_over_capacities": statistics.mean(row["fault_rate_mean"] for row in rows)})
    overall = []
    for algorithm in ALGORITHMS:
        rows = [row for row in summary if row["algorithm"] == algorithm]
        overall.append({"algorithm": algorithm, "configurations": len(rows),
                        "mean_faults": statistics.mean(row["faults_mean"] for row in rows),
                        "macro_mean_fault_rate": statistics.mean(row["fault_rate_mean"] for row in rows)})
    sources = sorted([ROOT / "CMakeLists.txt", *ROOT.glob("src/*.cpp"), *ROOT.glob("include/*.hpp"),
                      *ROOT.glob("scripts/*.py"), *ROOT.glob("tests/*.*")])
    metadata = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "platform": platform.platform(), "python": sys.version, "compiler": subprocess.check_output(["c++", "--version"], text=True).splitlines()[0],
                "frames": args.frames, "random_seeds": list(range(args.random_runs)),
                "runs": len(raw), "summary_groups": len(summary), "extra_enough_memory_checks": len(datasets) * len(ALGORITHMS),
                "stochastic_algorithms": sorted(STOCHASTIC),
                "adaptive_options": {"window_factor": 4, "history_factor": 16},
                "adaptive_policy": "past-window shadow losses select Random/LRU/reuse predictor; real frames retained on switches",
                "random_stddev": "sample standard deviation, ddof=1; variation across seeds on a fixed trace",
                "lfu_policy": "current-residency count; reset to 1 on insertion; ties by least-recent use",
                "initial_memory": "empty for every simulation", "prefetch": False,
                "binary_sha256": sha256(binary), "datasets": datasets,
                "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in sources}}
    args.out.mkdir(parents=True, exist_ok=True)
    for filename, rows in [("raw.csv", raw), ("summary.csv", summary), ("mean_by_trace.csv", by_trace), ("overall.csv", overall)]:
        write_csv(args.out / filename, rows)
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(raw)} runs and {len(summary)} summary groups to {args.out}")


if __name__ == "__main__":
    main()
