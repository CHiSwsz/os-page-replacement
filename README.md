# 在线页面替换：Adaptive V4

在队友 V3 的基础上优化的 C++17 页面替换模拟器。**现场一条命令读取任意文本，输出 5、10、20、50、100 页框的缺页次数及五档算术平均。**

```bash
bash run.sh "/path/to/test.txt"
```

[现场操作说明](QUICKSTART.md) · [当前实验报告](REPORT.md) · [10 分钟 PPT](presentation/contest-v4.pptx) · [PDF 预览](presentation/contest-v4.pdf) · [讲稿/答辩](presentation/V4_SPEAKER_NOTES.md)

当前默认 V4 在四个课程数据集的 20 个配置上平均缺页 **17,002.35**，比 LRU 少 **30.43%**，比 V3 再少 **0.576%**；相对 V3 为 **15 个改善、5 个持平**。冻结后 8 类构造测试总体少约 **1.11%**，但噪声循环有退化。未知课堂数据不能保证第一，全部不利结果见报告。

## 现场运行

Linux / WSL / macOS：脚本使用 CMake，缺少 CMake 时自动改用 C++17 编译器。运行只需要本地 C++ 程序，不依赖 Python、网络或模型服务。

```bash
bash run.sh data/mm32.txt
./build-live/pager "老师给的文件.txt"
bash run.sh test.txt --format json > result.json
bash run.sh test.txt --page-format decimal
bash run.sh test.txt --page-format token
cat test.txt | ./build-live/pager --contest -
```

默认页号为 64 位无符号十六进制，支持 `0x` 前缀、大小写、空白、UTF-8 BOM、CRLF。十进制用 `--page-format decimal`；任意字符串标签用 `--page-format token`，按原字符串精确比较。每个非空行只能有一个页号。输入已经是页号，不能再除以页大小。

Windows 提供 `run.ps1`，需要 CMake 和 C++17 编译器。实际验证环境为 Linux GCC 11，Windows 入口未实机验证。

```powershell
.\run.ps1 "C:\path\test.txt"
```

每档页框从空内存开始，固定 seed=0。`mm32` 应输出 `55006, 49256, 39016, 19909, 19604`，平均 **36558.20**。JSON 的 `average_faults` 是评分；CSV 最后一行 `frames=average` 是平均值。错误返回 2，并且不输出部分成绩。

## 算法和在线约束

保留 Random、FIFO、MIN/OPT、LFU、LRU、Second chance；`adaptive` 默认 V4，也可显式选择 `--adaptive-version 1|2|3|4`。

V4 组合 Random、LRU、历史间隔、历史片段重放、衰减频率、新页先验和上下文签名七种专家。通过已完成请求的衰减缺页数与切换门槛选择策略。影子只保存页号和统计，真实缓存只在缺页时装入当前请求页。**不预取、不复制影子驻留集合、不读取真实未来。** `OnlineAdaptive::access(page)` 只接收一个当前页号。

元数据为 O(F)，处理 N 次请求期望 O(NF)。现场数值模式逐行处理；字符串模式额外有 O(U) 标签映射。基线 LFU 统计当前驻留期次数、卸载清零、平局按 LRU；V4 的 Frequency 专家使用独立的衰减历史频次。OPT 使用真实未来，严格限定为离线对照，不是现场算法。

## 编译和验证

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j4
ctest --test-dir build --output-on-failure
cmake -S . -B build-sanitize -DCMAKE_BUILD_TYPE=Debug -DENABLE_SANITIZERS=ON
cmake --build build-sanitize -j4
ctest --test-dir build-sanitize --output-on-failure
```

Release、ASan、UBSan 已通过。包含独立 OPT 穷举、逐步驻留/淘汰验证、在线前缀不变性、页号重命名、流式/向量一致性、非法输入和均值检查。百万行输入也已实测，开销见报告。GitHub Actions 配置同时验证历史结果与 V4 数据；本地验证不等于声称远端 CI 已运行。

原有实验 CLI 及 CSV 列保持兼容，默认 adaptive 已变为 V4：

```bash
./build/pager --trace data/mm32.txt --algorithm all --frames 5,10,20,50,100
./build/pager --trace data/mm32.txt --algorithm adaptive --frames 5,10,20,50,100 --adaptive-version 3
./build/pager --trace data/sort1.txt --algorithm adaptive --frames 5 --events build/events.csv
```

`--events` 只允许单算法、单容量，记录真实命中和淘汰，不允许覆盖输入文件。该实验入口为运行 OPT 而读取完整 trace；现场入口采用流式处理。

## 实验、图表和汇报复现

```bash
python3 scripts/contest_experiments.py
python3 scripts/contest_benchmark.py
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt -r presentation/requirements.txt
.venv/bin/python scripts/build_v4_report.py
.venv/bin/python presentation/build_v4.py
python3 scripts/verify_v4.py
```

`contest_experiments.py --suite course|development|holdout|parameters` 可分开复现。默认 Random/V3/V4 都使用种子 0–29。最终 13,450 条运行记录和图表均在 `results/v4/`，课件要求的四个基本算法、四个数据集、五档容量及参数变化全部覆盖。开发数据与冻结后的构造验证单独标注，构造验证不是老师的隐藏数据。

开发探索另有 49 个候选、3,430 条记录，可用 `python3 scripts/explore_v4.py` 和 `python3 scripts/explore_v4.py --signature` 复现。`experiments/` 是历史候选源码，正式编译只使用 `src/`；它们保留了探索中的无效和不利方案。

| 位置 | 内容 |
|---|---|
| `results/v4/course_*` | 四条课程轨迹，八种方法，逐种子结果及汇总 |
| `results/v4/development_*` | 已参与设计的 10 类压力轨迹 |
| `results/v4/holdout_*` | 固定规则后生成的 8 类构造轨迹与结果 |
| `results/v4/parameters_*` | 窗口/历史长度敏感性，3,000 次运行 |
| `results/v4/frozen_algorithm.json` | 固定规则与源码 SHA-256 |
| `results/v4/performance.json` | 五档运行耗时、百万行验证、RSS |
| `presentation/contest-v4.pptx` | 17 页新汇报，含讲稿和 4 页数据附录 |
| `REPORT_V3.md`、原 `results/*.csv`、原 PPT | V3 历史存档 |

旧 `scripts/experiments.py` 等工具显式运行 V3，继续复现原 `results/*.csv`，不会把 V4 数字混入旧报告。`scripts/make_report.py` 现在写入 `REPORT_V3.md`；当前报告使用 `scripts/build_v4_report.py`。

## 提交 PR

在已认证、允许创建 fork 的 GitHub CLI 环境中，准备好的分支可运行：

```bash
bash scripts/submit_pr.sh
```

脚本使用当前 GitHub 用户的 fork，向 `CHiSwsz/os-page-replacement` 的 `main` 发起 PR；不直接修改或合并 main。描述见 `PR_BODY.md`。若已有同一分支的 PR，返回其地址。
