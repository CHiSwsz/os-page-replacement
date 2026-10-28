# 页面替换算法与自适应策略实验

C++17 demand-paging 模拟器，实现 **Random、FIFO、MIN/OPT、LFU、LRU、Second chance**，以及根据容量和过去访问历史调整策略的 **Adaptive**。附四个课程 trace、完整实验记录、课件示例形式的分组柱状图、参数实验和中文分析。

完整结果见 [实验报告](REPORT.md)，原始数据见 [results/](results/)，详细缺页次数见 [宽表](results/fault_counts_table.csv)。新版 Adaptive V3 在本次 20 个配置上的平均缺页次数比 Random 少 26.70%，比 LRU 少 30.02%，相对 V2 进一步降低 1.46%。本轮 9 个配置改善、6 个不变、5 个退化；新增扰动循环压力测试平均退化 0.94%。仍有落后于基线或旧版的配置，详见报告。

[汇报 PPT（21 页，含讲稿备注和详细数据附录）](presentation/page-replacement.pptx) 使用用户指定的 v22 模板制作，图表与表格可编辑。

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
./build/pager --trace data/mm32.txt --algorithm adaptive --frames 5,10,20,50,100 --seed 0
./build/pager --trace data/mm16.txt --algorithm adaptive --frames 100 --window-factor 4 --history-factor 16
./build/pager --trace data/mm16.txt --algorithm adaptive --frames 100 --adaptive-version 1
```

`--algorithm` 支持 `random`、`fifo`、`opt`、`min`、`lfu`、`lru`、`second_chance`、`adaptive`、`all`，其中 `min` 是 `opt` 的别名，`clock` / `second-chance` 是 `second_chance` 的别名。`all` 运行七种算法。统计结果以 CSV 写到标准输出，可重定向到文件。错误写到标准错误，退出码为 2。

核心输出字段是 `algorithm,frames,seed,references,hits,faults,evictions,fault_rate`，后接 `policy_random,policy_lru,policy_predict,policy_switches,history_peak`，用于解释 Adaptive 的行为；其他算法这些附加列为 0。确定性算法的 `seed` 为空，Random / Adaptive 保留种子。`fault_rate` 是 0～1 的比例。空 trace 的缺页率定义为 0。

`--events` 只允许单算法、单页框数量，记录 `reference,page,hit,frame,evicted`。访问序号从 1 开始，物理页框编号从 0 开始，页面号使用十六进制；没有淘汰时 `evicted` 为空。

## 模型与算法口径

- 统一的虚拟页号空间，内存初始为空。命中时不换页；缺页先使用空页框，只有已满时才淘汰。
- 不预取，不模拟磁盘耗时、脏页写回、TLB、页内偏移或多进程竞争。每次访问只计命中或缺页。
- **Random**：均匀随机选择驻留页框。使用 `mt19937_64` 和拒绝采样，消除取模偏差，并避免不同标准库的 `uniform_int_distribution` 实现差异。
- **FIFO**：淘汰最早装入的页面，命中不改变装入顺序。
- **OPT**：淘汰下一次访问最远的页面，永不再使用优先；并列时选择编号最小的页框。提前反向扫描 trace 计算每次访问的下一次出现位置。它是利用未来信息的离线最优基准。
- **LFU**：统计当前这次驻留期间的访问次数，装入时计数为 1，命中加 1，淘汰后丢弃计数。并列按 LRU 决定；未使用衰减或窗口。
- **LRU**：淘汰最后访问最早的页面，每次命中更新最近访问位置。
- **Second chance**：Clock 环形指针，访问位初始和命中时设为 1；替换时跳过并清除为 1 的位，淘汰遇到的第一个 0 位页面。
- **Adaptive**：F≤20 时从 Random 起步，其他容量从 LRU 起步。用最近 max(32,4F) 次访问的影子模拟缺页数，在 Random、LRU、历史间隔预测之间选择。F≤20 保留最多 max(32,16F) 个历史页号，F>20 保留最多 max(32,8F) 个（含被淘汰页）。V3 用新样本权重为 0.5 的平滑间隔估计复用，移除 V2 的波动附加项，过期预测逐渐失去保护。所有决策只看已发生访问。影子状态仅为元数据，切换时不复制其驻留集合，真实物理内存始终为 F 个页框。

V3 保留 V2 的影子对齐规则：F>20 时将上述窗口加倍，把切换门槛提高到窗口的 1/20，并每 W 次访问将真实缓存的页号、最近访问位置和 RNG 状态复制到三个影子缓存作为共同起点。F≤20 不重置影子，V3 的间隔预测更新对所有容量生效。复制方向始终是实际到影子，不改变真实页框。周期内仍可能有状态偏差，不能保证所有切换都受益。

除 OPT 外，决策只依赖已发生的访问。即使 CLI 为方便运行多个算法而把 trace 读入内存，六种在线算法也不会查看未来位置。Adaptive 的 `--window-factor` / `--history-factor` 范围为 1～64，默认 4 / 16，仅作用于 Adaptive。`--adaptive-version` 默认为 3，传 1 或 2 可逐字段复现旧版。V3 在 F>20 时将输入的历史因子减半、向下取整到至少 1，再计算 H=max(32,F×因子)。完整公式、切换条件和局限见报告。

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

课程更新版课件要求四个数据集都做；原压缩包附带的旧说明不改变本次要求。本实现已包含课件要求的 FIFO、MIN、LRU、Second chance 和自设组合策略，另保留 Random 与 LFU 对照。自设组合不宣称为新的学术算法。

## 复现实验

```bash
python3 scripts/experiments.py
python3 scripts/compare_versions.py
python3 scripts/analyze_traces.py
python3 scripts/supplementary_experiments.py
python3 scripts/fresh_stress.py
python3 scripts/benchmark_overhead.py
```

默认页框数 5、10、20、50、100。五种确定性算法各运行一次，Random / Adaptive 使用固定种子 0～29 各运行一次，共 1,300 次正式运行、140 组汇总；另进行 28 次“页框数等于不同页数”的正确性检查。每次运行重新清空内存、计数器与随机数发生器。补充脚本产生 3,000 条参数实验记录（其中 600 条复用默认配置）和 1,950 次构造轨迹测试。

`compare_versions.py` 保存 1,800 条 V1/V2/V3 配对记录，其中 V3 复用正式实验。`fresh_stress.py` 保存规则冻结后的四类新增构造轨迹，共 1,900 条记录。V3 初筛全部 15 个方案的 1,500 条记录见 `results/v3_search.csv`，可通过 `python3 scripts/explore_v3.py` 从固定 V2 提交复现。探索过程的 2,400 条记录见 `results/optimization_search_raw.csv`，可通过 `python3 scripts/explore_candidates.py` 从保留的 V1 提交重新生成。探索使用课程轨迹和种子 0～4，不能视作泛化评测。

图表需要 matplotlib，以下安装只影响仓库内的虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python scripts/plot_results.py
.venv/bin/python scripts/plot_comparisons.py
python3 scripts/make_report.py
python3 scripts/verify_artifacts.py
```

如果系统有 pip、但缺少创建 venv 所需的 ensurepip，可使用：

```bash
python3 -m venv --without-pip .venv
python3 -m pip --python .venv/bin/python install -r requirements-lock.txt
```

`requirements.txt` 只固定 matplotlib 版本；`requirements-lock.txt` 记录本次绘图使用的完整包版本。趋势图使用对数横轴；课件示例形式的分组柱状图使用五档容量分类横轴。Random / Adaptive 的阴影或误差线为均值 ±1 个样本标准差。

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
| `results/comparison_by_frames.png` / `.svg` | 七方法 × 五容量分组柱状图 |
| `results/normalized_vs_lru.png` / `.svg` | 按课件示例，将 LRU 归一化为 1 的对比图 |
| `results/fault_counts_table.csv` | 全部方法、各 frame 数的平均缺页次数宽表 |
| `results/fault_counts_seed0.csv` | seed=0 时全部方法的整数缺页次数 |
| `results/parameters_*.csv` | 窗口与历史长度的参数实验 |
| `results/synthetic_*.csv` | 构造轨迹压力测试，独立于课程给定数据 |
| `results/fresh_*.csv` | 四类新增构造压力测试，V2/V3 配对结果 |
| `results/versions_*.csv` | 三个 Adaptive 版本的完整配对结果 |
| `results/timing_*.csv` | mm32 / 100 页框的端到端程序耗时 |

## 正确性保障

- 穷举三种页号、长度 0～6 的全部 1,093 条 trace，分别测试 1～4 个页框及七种算法。
- OPT 与“枚举所有合法淘汰选择”的独立最优解比较。FIFO、LRU、LFU 的每次淘汰与独立的简单参考实现比较。
- 逐步检查页框容量、命中状态、缺页时才装入、满内存时才淘汰、统计和事件一致。
- 固定序列覆盖 Belady 异常、LFU 并列与重载计数重置、页号 0 / 最大 64 位值、Random 种子复现。
- Second chance 对照独立队列实现。Adaptive 检查改变未来后缀不改变过去决策、页号重命名不变、种子复现、策略切换后仍遵守物理容量、历史上限及参数边界。
- CLI 检查非法输入、路径空格、空 trace、结果格式，以及禁止事件输出覆盖输入文件或其符号链接。
- 在真实数据上验证 OPT 下界、LRU / OPT 的容量单调性、冷启动缺页下界、足够内存时的精确计数；用独立的重用距离分析再次核对 LRU。
- GitHub Actions 自动编译、运行普通与 sanitizer 测试，并逐字节复现已记录的原始实验 CSV。

## 仓库维护

修改使用独立 feature 分支，向本仓库的 `main` 提 PR，按用户授权，在验证与 CI 通过后自行合并。提交源码、数据、复现实验脚本及正式结果；不要提交 build 目录和虚拟环境。修改算法或实验口径后重新生成结果和报告。
