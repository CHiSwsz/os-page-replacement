#!/usr/bin/env python3
"""Grouped bars following slide 8's example, plus sensitivity and stress-test figures."""
import argparse
import csv
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from experiments import ALGORITHMS, ROOT
from plot_results import COLORS

LABELS = {"random": "Random", "fifo": "FIFO", "opt": "OPT (offline)", "lfu": "LFU", "lru": "LRU",
          "second_chance": "Second chance", "adaptive": "Adaptive"}
FRAMES = [5, 10, 20, 50, 100]
DATASETS = ["qsort", "lu", "mm16", "mm32"]


def read(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def save(fig, directory, name):
    for extension in ["png", "svg"]:
        path = directory / f"{name}.{extension}"
        fig.savefig(path, dpi=180, metadata={"Date": None} if extension == "svg" else None)
        if extension == "svg":
            path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    plt.close(fig)


def style(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#e1e5ea", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(bottom=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    out = args.results
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.titleweight": "bold",
                         "svg.hashsalt": "adaptive-paging-report", "savefig.facecolor": "white"})
    rows = read(out / "summary.csv")
    data = {(r["dataset"], int(r["frames"]), r["algorithm"]): r for r in rows}

    def draw_faults(ax, dataset):
        x = np.arange(len(FRAMES))
        width = 0.112
        for i, algorithm in enumerate(ALGORITHMS):
            selected = [data[(dataset, f, algorithm)] for f in FRAMES]
            y = [float(r["faults_mean"]) for r in selected]
            sd = [float(r["faults_stddev"]) for r in selected]
            ax.bar(x + (i - 3) * width, y, width, color=COLORS[algorithm], label=LABELS[algorithm],
                   yerr=sd if algorithm in {"random", "adaptive"} else None,
                   error_kw={"elinewidth": 0.7, "capsize": 1.5, "ecolor": "#333333"},
                   hatch="//" if algorithm == "opt" else None)
        ax.set_xticks(x, [str(f) for f in FRAMES])
        ax.set_xlabel("Physical frames")
        ax.set_ylabel("Page faults")
        references = int(data[(dataset, 5, "lru")]["references"])
        ax.set_title(f"{dataset}  ({references:,} references)", loc="left", pad=10)
        style(ax)

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.subplots_adjust(left=0.085, right=0.98, bottom=0.17, top=0.85, hspace=0.43, wspace=0.23)
    fig.suptitle("Page faults by frame count", x=0.085, y=0.975, ha="left", fontsize=23, fontweight="bold")
    fig.text(0.085, 0.92, "Grouped comparisons following the lecture example; lower is better.", color="#555555")
    for ax, dataset in zip(axes.flat, DATASETS):
        draw_faults(ax, dataset)
    handles, labels = axes[0,0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.53,0.05), ncol=7, frameon=False, fontsize=10)
    fig.text(0.085,0.025,"Random / Adaptive: mean of 30 seeds; error bars: ±1 sample SD. OPT uses future references.",fontsize=10,color="#555555")
    save(fig, out, "comparison_by_frames")
    for dataset in DATASETS:
        fig, ax = plt.subplots(figsize=(10,6))
        fig.subplots_adjust(left=0.1,right=0.98,top=0.88,bottom=0.24)
        draw_faults(ax, dataset)
        ax.legend(loc="upper center",bbox_to_anchor=(0.5,-0.16),ncol=4,frameon=False,fontsize=10)
        fig.text(0.1,0.025,"Random / Adaptive: 30-seed means. Error bars: ±1 sample SD.",fontsize=10,color="#555555")
        save(fig,out,f"faults_{dataset}")

    fig, axes = plt.subplots(2,3,figsize=(14,8))
    fig.subplots_adjust(left=0.07,right=0.98,bottom=0.16,top=0.84,hspace=0.5,wspace=0.22)
    fig.suptitle("Normalized page faults: LRU = 1",x=0.07,y=0.97,ha="left",fontsize=22,fontweight="bold")
    fig.text(0.07,0.915,"Same two-bar normalization as the lecture example. Values below 1 favor Adaptive.",color="#555555")
    for ax, capacity in zip(axes.flat,[*FRAMES,None]):
        ratios=[]
        for dataset in DATASETS:
            if capacity is None:
                numerator=statistics.mean(float(data[(dataset,f,"adaptive")]["faults_mean"]) for f in FRAMES)
                denominator=statistics.mean(float(data[(dataset,f,"lru")]["faults_mean"]) for f in FRAMES)
            else:
                numerator=float(data[(dataset,capacity,"adaptive")]["faults_mean"])
                denominator=float(data[(dataset,capacity,"lru")]["faults_mean"])
            ratios.append(numerator/denominator)
        x=np.arange(4)
        ax.bar(x-0.18,[1]*4,0.36,color="#a7adb4",label="LRU baseline")
        bars=ax.bar(x+0.18,ratios,0.36,color=COLORS["adaptive"],label="Adaptive")
        ax.bar_label(bars,labels=[f"{v:.2f}" for v in ratios],padding=3,fontsize=10)
        ax.set_title(f"{capacity} frames" if capacity else "Mean over five capacities",loc="left")
        ax.set_xticks(x,DATASETS)
        ax.set_ylabel("Faults / LRU faults")
        style(ax)
        ax.set_ylim(0,max(1.22,max(ratios)*1.2))
        ax.axhline(1,color="#555555",linestyle=":",linewidth=1)
    fig.legend(*axes[0,0].get_legend_handles_labels(),loc="lower center",bbox_to_anchor=(0.5,0.05),ncol=2,frameon=False)
    fig.text(0.07,0.02,"Adaptive uses only observed history; it is not guaranteed to beat LRU on every workload or capacity.",fontsize=10,color="#555555")
    save(fig,out,"normalized_vs_lru")

    parameters=read(out/"parameters_summary.csv")
    fig,axes=plt.subplots(1,2,figsize=(13,5.5))
    fig.subplots_adjust(left=0.08,right=0.98,top=0.8,bottom=0.24,wspace=0.25)
    fig.suptitle("Adaptive parameter sensitivity",x=0.08,y=0.96,ha="left",fontsize=21,fontweight="bold")
    fig.text(0.08,0.87,"Mean faults over the five capacities, normalized to the default (window=4F, history=16F).",color="#555555",fontsize=10)
    for ax,parameter,factors,fixed in [(axes[0],"window_factor",[2,4,8],("history_factor",16)),
                                      (axes[1],"history_factor",[8,16,32],("window_factor",4))]:
        x=np.arange(4)
        for j,factor in enumerate(factors):
            values=[]
            for dataset in DATASETS:
                selected=[r for r in parameters if r["dataset"]==dataset and int(r[parameter])==factor and int(r[fixed[0]])==fixed[1]]
                default=statistics.mean(float(data[(dataset,f,"adaptive")]["faults_mean"]) for f in FRAMES)
                values.append(statistics.mean(float(r["faults_mean"]) for r in selected)/default)
            ax.bar(x+(j-1)*0.24,values,0.24,label=f"{factor} × frames",color=["#9aa7b4","#101827","#3f8e9f"][j])
        ax.set_xticks(x,DATASETS)
        ax.set_ylabel("Mean faults / default mean faults")
        ax.set_title("Comparison window" if parameter=="window_factor" else "Page-ID history capacity",loc="left")
        style(ax)
        ax.axhline(1,color="#555555",linestyle=":",linewidth=1)
        ax.legend(loc="upper center",bbox_to_anchor=(0.5,-0.13),ncol=3,frameon=False,fontsize=9)
    fig.text(0.08,0.03,"Both limits have a minimum of 32. Each setting uses 30 seeds; defaults are shared across all traces.",fontsize=10,color="#555555")
    save(fig,out,"parameter_sensitivity")

    synthetic=read(out/"synthetic_summary.csv")
    cases=list(dict.fromkeys(r["dataset"] for r in synthetic))
    fig,ax=plt.subplots(figsize=(13,6))
    fig.subplots_adjust(left=0.08,right=0.98,top=0.82,bottom=0.3)
    fig.suptitle("Synthetic stress tests",x=0.08,y=0.96,ha="left",fontsize=21,fontweight="bold")
    fig.text(0.08,0.87,"Mean over five capacities; these are constructed cases, not the instructor's hidden traces.",color="#555555",fontsize=10)
    x=np.arange(len(cases))
    for j,algorithm in enumerate(["random","lru","adaptive"]):
        values=[statistics.mean(float(r["faults_mean"])/int(r["references"])*100 for r in synthetic if r["dataset"]==case and r["algorithm"]==algorithm) for case in cases]
        ax.bar(x+(j-1)*0.24,values,0.24,color=COLORS[algorithm],label=LABELS[algorithm])
    ax.set_xticks(x,[s.replace("_","\n") for s in cases])
    ax.set_ylabel("Mean page fault rate (%)")
    style(ax)
    ax.legend(loc="upper center",bbox_to_anchor=(0.5,-0.28),ncol=3,frameon=False)
    save(fig,out,"synthetic_comparison")
    print("Saved grouped, normalized, sensitivity, synthetic and per-trace figures (PNG + SVG).")


if __name__ == "__main__":
    main()
