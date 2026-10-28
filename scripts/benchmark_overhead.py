#!/usr/bin/env python3
"""Measure end-to-end CLI overhead on mm32/100; separate from page-fault quality."""
import argparse
import json
from pathlib import Path
import platform
import random
import statistics
import subprocess
import time

from experiments import ALGORITHMS, ROOT, sha256, write_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/pager")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("At least two measurements are required")
    binary=args.binary.resolve()
    def command(algorithm):
        return [str(binary),"--trace",str(ROOT/"data/mm32.txt"),"--algorithm",algorithm,"--frames","100","--seed","0"]
    for algorithm in ALGORITHMS:
        subprocess.run(command(algorithm),stdout=subprocess.DEVNULL,check=True)
    jobs=[(algorithm,repeat) for repeat in range(args.repeats) for algorithm in ALGORITHMS]
    random.Random(20261028).shuffle(jobs)
    rows=[]
    for algorithm,repeat in jobs:
        start=time.perf_counter()
        subprocess.run(command(algorithm),stdout=subprocess.DEVNULL,check=True)
        rows.append({"algorithm":algorithm,"repeat":repeat,"wall_time_ms":(time.perf_counter()-start)*1000})
    summary=[]
    for algorithm in ALGORITHMS:
        times=[r["wall_time_ms"] for r in rows if r["algorithm"]==algorithm]
        summary.append({"algorithm":algorithm,"repeats":len(times),"median_ms":statistics.median(times),
                        "min_ms":min(times),"max_ms":max(times)})
    write_csv(args.out/"timing_raw.csv",rows)
    write_csv(args.out/"timing_summary.csv",summary)
    (args.out/"timing_metadata.json").write_text(json.dumps({"platform":platform.platform(),"binary_sha256":sha256(binary),
        "dataset":"mm32","frames":100,"seed":0,"repeats":args.repeats,"warmup_runs_per_algorithm":1,
        "scope":"End-to-end subprocess wall time, including startup, trace parsing and simulation. Not actual OS paging latency."
    },indent=2)+"\n")
    print(json.dumps(summary,indent=2))


if __name__ == "__main__":
    main()
