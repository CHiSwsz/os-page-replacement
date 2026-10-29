The classroom runner reads one page ID per line and prints faults at 5, 10, 20, 50 and 100 frames plus their arithmetic mean. `bash run.sh TRACE.txt` now defaults to Adaptive V5; explicit versions 1–4 and the original experiment CSV schema remain available.

V5 adds bounded delayed-label conditional reuse distributions to V4's predictors, then selects among 25 experts using past decayed miss counts. Context features include observed predecessors and already observed successors. The real cache only evicts a resident page and admits the current request; shadow caches store IDs, and the streaming predictor receives no future trace. The three frozen V4 core sources remain byte-identical.

Across four course traces / 20 configurations, mean faults decrease from V4 **17,002.35** to V5 **16,688.45** (**1.846%**), versus V3 **17,100.79** (**2.411%**). LU/100 improves by 1,498 faults and mm32/100 by 1,582. Versus V4, 14 course configurations improve, 4 tie and 2 regress. Ten newly constructed post-freeze workloads improve **2.91%** overall; all regressions and the development/validation distinction remain visible.

The tradeoff is more simulation work: local Release mm32/five-capacity median increases from about 0.99s to 4.49s. One million unique requests finish in about 95s with ~19.9 MiB peak RSS and exactly one million faults at each capacity. These are simulator timings, not OS fault latency.

Validation and delivery:
- Release and ASan/UBSan CTest: 3/3, including exact OPT dynamic-program bounds, physical resident/victim checks, prefix invariance, page-ID bijection, streaming/vector equality, bounded metadata and CLI input/average contracts.
- 20,000 final runs with matching seed 0–29 ranges; 33,110 development/research records. Legacy V3 replay is byte-identical; V3/V4 course records agree with historical results.
- Primary-paper research notes, failed trend/Markov/voting attempts and ARC/S3-FIFO-demand/SIEVE baselines are included, with source/data hashes. This is an independently engineered combination, not a claim to reproduce LRB/LHD or inherit their guarantees.
- Updated Chinese guide, report, 15-slide deck, speaker notes and PDF; native chart/table values audited against CSV. Windows x64 is statically cross-compiled, not runtime-tested on Windows.

No claim is made about universal optimality or winning every unseen classroom input. The new mm32 rehearsal mean is **35891.20**; explicit V4 retains **36558.20**.
