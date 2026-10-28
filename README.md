# 页面替换算法基线实验

C++17 demand-paging 模拟器，实现 **Random、FIFO、MIN/OPT、LFU、LRU**，附四个课程 trace、实验原始记录、图表与中文分析。

完整结果见 [实验报告](REPORT.md)，原始数据见 [results/](results/)。本次实现范围是课件第 4 页的五种基线。

## 编译与测试

在 Linux / WSL 的仓库根目录执行，需要 C++17 编译器、CMake 和 Python 3。模拟器与测试不依赖第三方 Python 包。

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

内存与未定义行为检查：

```bash
cmake -S . -B build-sanitize -DCMAKE_BUILD_TYPE=Debug -DENABLE_SANITIZERS=ON
cmake --build build-sanitize -j4
ctest --test-dir build-sanitize --output-on-failure
```

## 运行任意 trace

```bash
./build/pager --trace data/sort1.txt --algorithm all --frames 5,10,20,50,100
./build/pager --trace data/mm32.txt --algorithm random --frames 50 --seed 7
./build/pager --trace data/sort1.txt --algorithm lru --frames 5 --events build/events.csv
```

`--algorithm` 支持 `random`、`fifo`、`opt`、`min`、`lfu`、`lru`、`all`，其中 `min` 是 `opt` 的别名。统计结果以 CSV 写到标准输出，可重定向到文件。错误写到标准错误，退出码为 2。

输出字段是 `algorithm,frames,seed,references,hits,faults,evictions,fault_rate`。确定性算法的 `seed` 为空。`fault_rate` 是 0～1 的比例。空 trace 的缺页率定义为 0。

`--events` 只允许单算法、单页框数量，记录 `reference,page,hit,frame,evicted`。访问序号从 1 开始，物理页框编号从 0 开始，页面号使用十六进制；没有淘汰时 `evicted` 为空。

## 模型与算法口径

- 统一的虚拟页号空间，内存初始为空。命中时不换页；缺页先使用空页框，只有已满时才淘汰。
- 不预取，不模拟磁盘耗时、脏页写回、TLB、页内偏移或多进程竞争。每次访问只计命中或缺页。
- **Random**：均匀随机选择驻留页框。使用 `mt19937_64` 和拒绝采样，消除取模偏差，并避免不同标准库的 `uniform_int_distribution` 实现差异。
- **FIFO**：淘汰最早装入的页面，命中不改变装入顺序。
- **OPT**：淘汰下一次访问最远的页面，永不再使用优先；并列时选择编号最小的页框。提前反向扫描 trace 计算每次访问的下一次出现位置。它是利用未来信息的离线最优基准。
- **LFU**：统计当前这次驻留期间的访问次数，装入时计数为 1，命中加 1，淘汰后丢弃计数。并列按 LRU 决定；未使用衰减或窗口。
- **LRU**：淘汰最后访问最早的页面，每次命中更新最近访问位置。

除 OPT 外，决策只依赖已发生的访问。即使 CLI 为方便运行多个算法而把 trace 读入内存，四种在线算法也不会查看未来位置。

实现采用页号到页框的哈希表，命中检查为期望 O(1)。Random 的淘汰为期望 O(1)；FIFO、LRU、LFU、OPT 为便于讲解，淘汰时扫描 F 个页框，耗时 O(F)。它们在本任务 F≤100 的规模下可快速完成实验。OPT 的预处理期望 O(N)，额外空间 O(N+U)，N 是访问次数，U 是不同页面数。所有算法的页框状态占 O(F)，读取完整 trace 另占 O(N)，开启事件日志再增加 O(N)。这份实验比较缺页次数，不把程序运行时间当作算法优劣指标。

## 数据格式与来源

`data/` 的四个文本来自用户提供的课程 `TraceSet1.zip`，保留原始字节。来源压缩包及文件的 SHA-256、访问次数、不同页数记录在 [data/manifest.json](data/manifest.json)。

| 数据集 | 文件 | 访问次数 | 不同页数 |
|---|---|---:|---:|
| qsort | `sort1.txt` | 524 | 192 |
| lu | `lu.txt` | 41,832 | 531 |
| mm16 | `mm16.txt` | 9,075 | 515 |
| mm32 | `mm32.txt` | 67,235 | 1,667 |

每个非空行是一个**十六进制虚拟页号**，不是地址，不要再除以页面大小。忽略首尾空白，支持可选的 `0x` 前缀及大小写字母，以数值统一比较。拒绝多列、负数、非十六进制字符及超出 64 位的页号。

如需重新导入原始包：

```bash
python3 scripts/import_traces.py /path/to/TraceSet1.zip
```

课程更新版课件要求四个数据集都做；原压缩包附带的旧说明不改变本次要求。课件另要求 Second chance 和自己的算法，这两项不属于当前五基线实现。

## 复现实验

```bash
python3 scripts/experiments.py
python3 scripts/analyze_traces.py
```

默认页框数 5、10、20、50、100。四种确定性算法各运行一次，Random 使用固定种子 0～29 各运行一次，共 680 次正式运行、100 组汇总；另进行 20 次“页框数等于不同页数”的正确性检查。每次运行重新清空内存、计数器与随机数发生器。

图表需要 matplotlib，以下安装只影响仓库内的虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python scripts/plot_results.py
```

如果系统有 pip、但缺少创建 venv 所需的 ensurepip，可使用：

```bash
python3 -m venv --without-pip .venv
python3 -m pip --python .venv/bin/python install -r requirements-lock.txt
```

`requirements.txt` 只固定 matplotlib 版本；`requirements-lock.txt` 记录本次绘图使用的完整包版本。图表横轴使用真实页框数量的对数刻度，Random 阴影是均值 ±1 个样本标准差。

| 输出 | 内容 |
|---|---|
| `results/raw.csv` | 每次模拟的完整统计，含 Random 的 30 个种子 |
| `results/summary.csv` | 每个 trace / 页框数 / 算法的均值、标准差、最小值、最大值 |
| `results/mean_by_trace.csv` | 每条 trace 上五档页框数的算术平均缺页次数 |
| `results/overall.csv` | 20 个 trace / 页框配置的等权平均缺页次数、宏平均缺页率 |
| `results/metadata.json` | 参数、环境、源代码与二进制校验值 |
| `results/trace_diagnostics.json` | 重用距离分析，以及独立核对的 LRU 缺页次数 |
| `results/fault_counts.png` / `.svg` | 缺页次数图 |
| `results/fault_rates.png` / `.svg` | 缺页率图 |

## 正确性保障

- 穷举三种页号、长度 0～6 的全部 1,093 条 trace，分别测试 1～4 个页框及五种算法。
- OPT 与“枚举所有合法淘汰选择”的独立最优解比较。FIFO、LRU、LFU 的每次淘汰与独立的简单参考实现比较。
- 逐步检查页框容量、命中状态、缺页时才装入、满内存时才淘汰、统计和事件一致。
- 固定序列覆盖 Belady 异常、LFU 并列与重载计数重置、页号 0 / 最大 64 位值、Random 种子复现。
- CLI 检查非法输入、路径空格、空 trace、结果格式，以及禁止事件输出覆盖输入文件或其符号链接。
- 在真实数据上验证 OPT 下界、LRU / OPT 的容量单调性、冷启动缺页下界、足够内存时的精确计数；用独立的重用距离分析再次核对 LRU。
- GitHub Actions 自动编译、运行普通与 sanitizer 测试，并逐字节复现已记录的原始实验 CSV。

## 仓库维护

修改使用独立 feature 分支，向本仓库的 `main` 提 PR，由用户审阅并合并。提交源码、数据、复现实验脚本及正式结果；不要提交 build 目录和虚拟环境。修改算法或实验口径后重新生成结果和报告。
