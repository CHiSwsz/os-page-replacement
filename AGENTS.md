# Repository instructions

- This is the standalone repository `CHiSwsz/os-page-replacement`, separate from the OS kernel labs.
- Work in Linux as `xzzduang` in WSL distribution `Ubuntu-22.04`, under `/home/xzzduang/os-course/os-page-replacement`.
- Inspect the working tree first and preserve user work.
- Use a feature branch and a PR with explicit base `main` in this repository. The user authorized the ongoing workflow on 2026-10-28: create the PR, wait for validation and CI to pass, then merge it yourself. Do not push implementation changes directly to `main`.
- Current authorized scope: Random, FIFO, OPT/MIN, LFU, LRU, Second chance and the capacity/history-adaptive strategy, their validation, experiments, report and figures. Do not add another algorithm without a user request.
- Keep LFU tie-breaking and frequency lifetime documented. Keep Random seeds and every raw result.
- Build with CMake, run CTest, and run the sanitizer configuration for changes to the simulator.
- When changing algorithm semantics or experiment scripts, regenerate results, verify source/data hashes and update REPORT.md.
- Source traces already contain hexadecimal virtual page numbers. Never divide them by page size.
- Adaptive decisions must use only observed history. Shadow simulations contain page IDs only; never copy shadow residents into the actual cache or exceed the physical frame limit.
- Keep adverse results visible. Random and Adaptive need the same recorded seed range. Report parameter studies and synthetic stress tests separately from the four course traces.
