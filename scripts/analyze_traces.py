#!/usr/bin/env python3
"""Measure exact reuse distances and independently check the saved LRU results."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Fenwick:
    def __init__(self, size):
        self.tree = [0] * (size + 1)

    def add(self, index, delta):
        while index < len(self.tree):
            self.tree[index] += delta
            index += index & -index

    def prefix(self, index):
        total = 0
        while index:
            total += self.tree[index]
            index -= index & -index
        return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    with (args.results / "summary.csv").open() as stream:
        summary = list(csv.DictReader(stream))
    capacities = sorted({int(row["frames"]) for row in summary})
    datasets = json.loads((args.data / "manifest.json").read_text())["datasets"]
    diagnostics = []
    for dataset in datasets:
        raw = (args.data / dataset["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != dataset["sha256"]:
            raise ValueError("Trace checksum mismatch")
        pages = [int(line, 16) for line in raw.splitlines() if line.strip()]
        tree = Fenwick(len(pages))
        last = {}
        distances = []
        gaps = []
        for i, page in enumerate(pages, start=1):
            if page in last:
                previous = last[page]
                # One marker at the most recent position of each distinct page.
                distances.append(len(last) - tree.prefix(previous))
                gaps.append(i - previous - 1)
                tree.add(previous, -1)
            last[page] = i
            tree.add(i, 1)
        expected_faults = {str(frames): len(last) + sum(distance >= frames for distance in distances)
                           for frames in capacities}
        for row in summary:
            if row["dataset"] == dataset["name"] and row["algorithm"] == "lru":
                if expected_faults[row["frames"]] != int(float(row["faults_mean"])):
                    raise RuntimeError("LRU disagrees with exact reuse-distance calculation")
        item = {"dataset": dataset["name"], "references": len(pages), "unique_pages": len(last),
                "repeated_references": len(distances), "minimum_reuse_distance": min(distances) if distances else None,
                "minimum_intervening_references": min(gaps) if gaps else None,
                "lru_faults_from_reuse_distances": expected_faults}
        diagnostics.append(item)
        print(f"{dataset['name']}: minimum reuse distance={item['minimum_reuse_distance']}; all LRU counts verified")
    (args.results / "trace_diagnostics.json").write_text(json.dumps(diagnostics, indent=2) + "\n")


if __name__ == "__main__":
    main()
