# Repository instructions

- This is the standalone repository `CHiSwsz/os-page-replacement`, separate from the OS kernel labs.
- Work in Linux as `xzzduang` in WSL distribution `Ubuntu-22.04`, under `/home/xzzduang/os-course/os-page-replacement`.
- Inspect the working tree first and preserve user work.
- Use a feature branch and a PR with explicit base `main` in this repository. Do not merge or enable auto-merge; the user reviews and merges.
- Current authorized scope: Random, FIFO, OPT/MIN, LFU and LRU baselines, their validation, experiments and documentation. Do not add another algorithm without a user request.
- Keep LFU tie-breaking and frequency lifetime documented. Keep Random seeds and every raw result.
- Build with CMake, run CTest, and run the sanitizer configuration for changes to the simulator.
- When changing algorithm semantics or experiment scripts, regenerate results, verify source/data hashes and update REPORT.md.
- Source traces already contain hexadecimal virtual page numbers. Never divide them by page size.
