The classroom runner previously required several flags and did not print the required five-capacity average. This change adds `bash run.sh TRACE.txt` / `pager TRACE.txt`, processes one page at a time with Adaptive V4, and prints faults for 5, 10, 20, 50 and 100 frames plus their arithmetic mean.

Adaptive V4 combines bounded historical replay, decayed frequency, cold-page reuse priors and learned context signatures with the existing interval predictor. Exponentially decayed shadow losses and a switching margin choose the policy; actual frames are reconciled only through legal demand-page evictions. No future references, prefetching or shadow-resident copying are used. V1–V3 and the original experiment CSV schema remain available.

Across the four course traces and 20 configurations, V4 averages **17,002.35** faults versus V3 **17,100.79** and LRU **24,438.00** (15 improvements and 5 ties versus V3). Eight constructed workloads generated after rule freeze improve by **1.11%** on average, with the noisy-cycle regression retained. All seed-0..29 runs, parameter studies, candidate search records, source/data hashes, a Chinese guide, report and 17-slide deck are included. No claim is made about winning unseen classroom tests.

Validation:
- CMake Release and AddressSanitizer/UndefinedBehaviorSanitizer CTest pass, including more than 2.5 million assertions, exhaustive OPT checks, valid resident/victim events, prefix invariance, page-ID renaming and streaming/vector equivalence.
- CLI checks cover the five-count mean, stdin, path spaces, UTF-8 BOM/CRLF, hexadecimal/decimal/token inputs, empty files and failures without partial scores.
- 13,450 final experiment runs; legacy V3 results remain reproducible.
- One-million-line unique scan returns exactly 1,000,000 faults for each capacity; measured peak RSS about 9.3 MiB in the streaming numeric mode.
- PowerPoint chart/table data are checked against CSV; the deck is rendered locally to PDF for layout review. Linux is tested; the Windows launcher is provided but not claimed as tested.

The simulator is slower than V3 because it maintains more predictors; the report includes the measured overhead. Historical V3 artifacts are explicitly separated from current V4 results.
