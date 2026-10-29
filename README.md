# 在线页面替换：Adaptive V5

在队友 V3 与已有 V4 上继续优化的 C++17 模拟器。每行一个页号，逐行处理，输出 **5、10、20、50、100** 页框的缺页次数和五档算术平均。

```bash
bash run.sh "老师给的文件.txt"
```

[现场说明](QUICKSTART.md) · [实验报告](REPORT.md) · [论文与探索](RESEARCH_V5.md) · [15 页 PPT](presentation/contest-v5.pptx) · [PDF](presentation/contest-v5.pdf) · [讲稿](presentation/V5_SPEAKER_NOTES.md)

四条课程轨迹、20 个配置的平均缺页：**V5 16,688.45，V4 17,002.35，V3 17,100.79**。V5 比 V4 少 **1.846%**，比 V3 少 **2.411%**。其中 LU/100 页框少 1,498 次，mm32/100 页框少 1,582 次。相对 V4 为 14 改善、4 持平、2 退步；完整结果均保留。

冻结后新增的 10 类构造验证总体比 V4 少约 **2.91%**。构造验证不是老师的隐藏数据，课程数据参与了调参；不声称未知输入必胜或已到算法极限。

## 现场运行

```bash
bash run.sh data/mm32.txt
./build-live/pager "带空格的路径/test.txt"
bash run.sh test.txt --format json
bash run.sh test.txt --page-format decimal
bash run.sh test.txt --page-format token
cat test.txt | ./build-live/pager --contest -
bash run.sh test.txt --adaptive-version 4  # 复现旧 V4
```

默认每行一个 64 位无符号十六进制页号，支持 `0x`、空白、空行、UTF-8 BOM 与 CRLF。不再除以页大小。十进制用 `decimal`；任意标签用 `token`，按原字符串精确比较。非法输入返回 2，不输出部分成绩。Windows 可用 `run.ps1` 配合 CMake/C++17；交付目录也有交叉编译的 x64 可执行文件，未在真实 Windows 上运行验证。

新默认 V5 的 mm32 结果：**55006、48712、37986、19730、18022，平均 35891.20**。旧 V4 的平均 36558.20 只适用于显式 `--adaptive-version 4`。

## 算法

参考 LRB 的延迟标签、LHD 的条件年龄和在线缓存组合思路，自行实现有界条件复用分布，并与原 V4 的策略组成 25 个专家。依据已完成请求的衰减缺页数动态切换；收益主要来自更丰富的历史信号。没有声称复现论文成绩或继承其理论保证，来源与无效尝试见 [研究记录](RESEARCH_V5.md)。

真实缓存只在缺页时装入当前页，影子只保存页号和统计。`OnlineAdaptiveV5::access(page)` 只接收当前页，不读未来、不预取、不复制影子驻留页。数值流式模式元数据 O(F)，固定专家数下期望时间 O(NF)；token 模式另有 O(U) 标签表。

本次优先减少缺页：本机 mm32 五档模拟 V4 约 0.99 秒，V5 约 4.49 秒。百万行纯扫描 V5 约 95 秒、峰值 RSS 约 19.9 MiB；更少缺页需要更多模拟计算，详见报告。

Random、FIFO、OPT/MIN、LFU、LRU、Second chance 仍保留。OPT 只用于离线对照。LFU 统计当前驻留期次数、卸载清零，平局按 LRU。实验 CLI 的 CSV 列保持兼容：

```bash
./build/pager --trace data/mm32.txt --algorithm all --frames 5,10,20,50,100
./build/pager --trace data/mm32.txt --algorithm adaptive --frames 5,10,20,50,100 --adaptive-version 3
```

两个 CLI 默认 V5；实验 CLI 支持版本 1–5，现场 CLI 支持 4/5。C++ 旧 API 的默认选项为兼容性仍保留 V4；V5 显式使用 `{4,16,5}` 或新流式类。V4 冻结的三个核心源文件未修改。

## 构建与复现

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j4
ctest --test-dir build --output-on-failure
cmake -S . -B build-asan -DCMAKE_BUILD_TYPE=Debug -DENABLE_SANITIZERS=ON
cmake --build build-asan -j4
ctest --test-dir build-asan --output-on-failure
python3 scripts/learned_experiments.py
python3 scripts/learned_benchmark.py
python3 scripts/build_v5_report.py
python3 scripts/verify_v5.py
```

V5 正式评测共 **20,000 次运行**；研究/原型对照共 **33,110 行记录**。Random 和各 Adaptive 版本采用相同种子 0–29。Release、ASan、UBSan 已通过；检查真实驻留、精确 OPT 下界、前缀不变、页号重命名、流式一致、输入格式和平均值。GitHub Actions 还重跑课程数据并逐字节比较 CSV。

PPT 本地生成：安装 `presentation/requirements.txt` 后运行 `python presentation/build_v5.py`。`verify_v5.py` 独立核对 PPT 原生图表和四张附录表的数据。V3、V4 的报告、课件、结果与复现脚本均保留；`build_v4_report.py` 现在写入 `REPORT_V4.md`。

| 位置 | 内容 |
|---|---|
| `results/v5/course_*` | 四条课程轨迹、九种方法、逐种子结果 |
| `results/v5/development_*` | 已参与设计的十类构造轨迹 |
| `results/v5/regression_*` | 原 V4 的八类验证，现在作为已有回归集 |
| `results/v5/holdout_*` | V5 冻结后生成的十类新构造验证 |
| `results/v5/research/` | 参数、专家、组合与论文基线，包括失败方向 |
| `results/v5/frozen_algorithm.json` | 规则、冻结时间、源码哈希 |
| `REPORT_V4.md`、`results/v4/` | V4 历史材料 |

PR：<https://github.com/CHiSwsz/os-page-replacement/pull/4>。已有写入授权时，可用 `bash scripts/submit_pr.sh` 推送同一分支并返回 PR；不会直接修改或合并 main。
