#!/usr/bin/env python3
"""Generate standalone figures from saved summary data, without rerunning simulations."""
import argparse
import csv
import importlib.metadata
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"random": "#8b5cf6", "fifo": "#e58b18", "opt": "#11856b", "lfu": "#c84b62", "lru": "#2875c7",
          "second_chance": "#87929e", "adaptive": "#101827"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    with (args.results / "summary.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    datasets = list(dict.fromkeys(row["dataset"] for row in rows))
    if len(datasets) != 4:
        raise ValueError("The course overview expects four datasets")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold", "savefig.facecolor": "white",
                         "svg.hashsalt": "page-replacement-baselines"})
    for rate in [False, True]:
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        fig.subplots_adjust(top=0.86, bottom=0.20, left=0.09, right=0.97, hspace=0.48, wspace=0.24)
        fig.suptitle("Demand paging: Adaptive and six baselines", x=0.09, y=0.97, ha="left", fontsize=20, fontweight="bold")
        fig.text(0.09, 0.915, "Four course traces | Empty initial memory | No prefetching | Lower is better", color="#555555", fontsize=11)
        for ax, dataset in zip(axes.flat, datasets):
            subset = [row for row in rows if row["dataset"] == dataset]
            references = int(subset[0]["references"])
            ax.set_title(f"{dataset}  ({references:,} references)", loc="left", pad=10)
            for algorithm, color in COLORS.items():
                selected = sorted((row for row in subset if row["algorithm"] == algorithm), key=lambda row: int(row["frames"]))
                x = [int(row["frames"]) for row in selected]
                scale = 100 / references if rate else 1
                y = [float(row["faults_mean"]) * scale for row in selected]
                label = "OPT (offline)" if algorithm == "opt" else ("Random (30-seed mean)" if algorithm == "random" else algorithm.upper())
                if algorithm in {"random", "adaptive"}:
                    label = f"{algorithm.title()} ({selected[0]['runs']}-seed mean)"
                if algorithm == "second_chance":
                    label = "Second chance"
                ax.plot(x, y, marker="o", markersize=4, linewidth=2, color=color,
                        linestyle="--" if algorithm == "opt" else "-", label=label)
                if algorithm in {"random", "adaptive"}:
                    sd = [float(row["faults_stddev"]) * scale for row in selected]
                    ax.fill_between(x, [max(0, a-b) for a,b in zip(y,sd)], [a+b for a,b in zip(y,sd)], color=color, alpha=0.12)
            ax.set_xscale("log")
            ax.set_xticks(x)
            ax.xaxis.set_major_formatter(ScalarFormatter())
            ax.minorticks_off()
            ax.set_xlabel("Physical frames (log scale)")
            ax.set_ylabel("Page fault rate (%)" if rate else "Page faults")
            ax.set_ylim(bottom=0)
            ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
            ax.set_axisbelow(True)
        handles, labels = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.53, 0.055), ncol=4, frameon=False, fontsize=10)
        fig.text(0.09, 0.025, "Shading: mean ± 1 sample standard deviation for Random and Adaptive. Lower is better.", fontsize=10, color="#555555")
        stem = "fault_rates" if rate else "fault_counts"
        for extension in ["png", "svg"]:
            path = args.results / f"{stem}.{extension}"
            fig.savefig(path, dpi=180, metadata={"Date": None} if extension == "svg" else None)
            if extension == "svg":
                path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
        plt.close(fig)
    packages = {name: importlib.metadata.version(name) for name in ["matplotlib", "numpy"]}
    (args.results / "plot_environment.json").write_text(json.dumps(packages, indent=2) + "\n")
    print("Saved fault_counts and fault_rates figures (PNG + SVG).")


if __name__ == "__main__":
    main()
