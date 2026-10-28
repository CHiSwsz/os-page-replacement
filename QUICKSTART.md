# 现场使用说明

## 最短操作

在仓库目录打开终端，运行：

```bash
bash run.sh "/完整路径/老师现场给的文件.txt"
```

脚本自动编译 C++17 Release 程序，打印 **5、10、20、50、100** 个页框的缺页次数、缺页率，最后一行是 **Average page faults (5 capacities)**，即五个缺页次数的算术平均。不是平均缺页率，也不是运行多次后挑出的最好值。

已经编译过时，直接运行更快：

```bash
./build-live/pager "/完整路径/老师现场给的文件.txt"
```

文件名、文件长度和页号大小不会被用来选择算法。默认固定 Adaptive V4、seed=0、window factor=4、history factor=16。每档页框从空内存开始，五个模拟器互不共享驻留页。程序按行读入，只把当前页号交给算法。

## 先做一次现场演练

```bash
bash run.sh data/mm32.txt
```

应得到：

| 页框数 | 缺页次数 |
|---:|---:|
| 5 | 55,006 |
| 10 | 49,256 |
| 20 | 39,016 |
| 50 | 19,909 |
| 100 | 19,604 |
| 平均 | **36,558.20** |

老师换文件时只改路径，保持同一套规则。未知文件的成绩无法提前保证。

## 输入格式

默认每行一个 **64 位无符号十六进制页号**，沿用课程数据口径；`a`、`A`、`0xA`、`000a` 都是同一页。支持首尾空格、空行、UTF-8 BOM 和 Windows CRLF。页面号已经是页号，不再除以页大小。

如果老师明确给的是十进制：

```bash
bash run.sh test.txt --page-format decimal
```

如果页面编号是任意字符串、负数标签或超过 64 位的标签：

```bash
bash run.sh test.txt --page-format token
```

`token` 按字符精确比较，`10`、`010` 不同，`0xA`、`a` 也不同。此模式额外保留标签到内部编号的映射，空间随不同标签数增长。默认 hex / decimal 模式的算法状态空间不随文件长度增长。

所有模式都要求每个非空行只有一个页号，不接受多列或行尾注释。错误会显示行号并返回退出码 2，完整读入有效文件后才打印成绩，避免把部分结果当作最终成绩。

## Windows / macOS / Linux

Linux、WSL、macOS：需要 C++17 编译器；有 CMake 时脚本优先用 CMake，否则直接用 `c++` 编译。运行不依赖网络、Python、模型 API 或额外数据文件。

Windows 原生：安装 CMake 和 Visual Studio C++ Build Tools，PowerShell 中执行：

```powershell
.\run.ps1 "C:\Users\你的名字\Desktop\test.txt"
```

提供了 Windows 构建入口，当前环境实际验证的是 Linux GCC 11，未声称在 Windows 上实机测试。若现场已有 WSL，使用上面的 `bash run.sh` 更直接。

没有 CMake 时手动编译（Linux / WSL / macOS）：

```bash
c++ -std=c++17 -O3 -Iinclude src/*.cpp -o pager
./pager test.txt
```

## 导出和标准输入

```bash
bash run.sh test.txt --format json > result.json
bash run.sh test.txt --format csv > result.csv
cat test.txt | ./build-live/pager --contest -
```

CSV 的最后一行 `frames=average` 是平均值。JSON 的 `results` 固定有五项，`average_faults` 是评分值。构建日志写到标准错误，不混入 Linux 脚本的结果文件。

## 课堂说明的关键三句话

1. 我们让多个只看历史的策略并行统计表现，以衰减缺页数选择策略；切换有门槛。
2. 重复访问片段、近期复用间隔和上下文签名用于预测；新页还可以使用近期复用间隔的统计先验。
3. 影子缓存只是页号元数据。真实缓存只在缺页时装入当前请求页，切换不复制影子页，不预取、不超过 F 个物理页框。

完整讲解、公式、数据和局限见 [REPORT.md](REPORT.md)，10 分钟汇报见 [PPT](presentation/contest-v4.pptx)。原版 V3 的结果与 PPT 作为历史材料保留。
