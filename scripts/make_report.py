#!/usr/bin/env python3
"""Build the Chinese report and wide count tables directly from recorded CSV values."""
import csv
import statistics
from decimal import Decimal, ROUND_HALF_UP

from experiments import ALGORITHMS, ROOT, write_csv

NAMES = {"random":"Random", "fifo":"FIFO", "opt":"OPT", "lfu":"LFU", "lru":"LRU",
         "second_chance":"Second chance", "adaptive":"Adaptive（我们）"}
FRAMES = [5,10,20,50,100]
DATASETS = ["qsort","lu","mm16","mm32"]


def read(name):
    with (ROOT/"results"/name).open() as stream:
        return list(csv.DictReader(stream))


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "---|"*len(headers),
                      *("| " + " | ".join(map(str,row)) + " |" for row in rows)])


def main():
    summary=read("summary.csv")
    data={(r["dataset"],int(r["frames"]),r["algorithm"]):r for r in summary}
    if len(data)!=140:
        raise RuntimeError("Expected 4 traces x 5 capacities x 7 algorithms")
    raw=read("raw.csv")
    seed0={(r["dataset"],int(r["frames"]),r["algorithm"]):r for r in raw if r["seed"] in {"", "0"}}
    overall={r["algorithm"]:r for r in read("overall.csv")}
    mean=lambda algorithm:float(overall[algorithm]["mean_faults"])
    wide=[]
    exact=[]
    details=[]
    for dataset in DATASETS:
        for frames in FRAMES:
            row={"dataset":dataset,"frames":frames}
            one={"dataset":dataset,"frames":frames}
            for algorithm in ALGORITHMS:
                source=data[(dataset,frames,algorithm)]
                row[algorithm]=float(source["faults_mean"]) if algorithm in {"random","adaptive"} else int(source["faults_mean"])
                one[algorithm]=int(seed0[(dataset,frames,algorithm)]["faults"])
            wide.append(row)
            exact.append(one)
            baseline=min(float(data[(dataset,frames,a)]["faults_mean"]) for a in ALGORITHMS if a not in {"opt","adaptive"})
            ours=row["adaptive"]
            details.append((dataset,frames,ours,baseline))
    write_csv(ROOT/"results/fault_counts_table.csv",wide)
    write_csv(ROOT/"results/fault_counts_seed0.csv",exact)
    wins=sum(ours<best for _,_,ours,best in details)
    ties=sum(ours==best for _,_,ours,best in details)
    losses=len(details)-wins-ties
    paragraphs=["# 自适应页面替换算法与完整实验报告", "",
        f"本次实现一个按容量初始化、根据过去访问表现调整策略的 **Adaptive** 算法，并补齐课件要求的 **Second chance**。同 Random、FIFO、OPT、LFU、LRU 比较，在四条课程轨迹、五档容量的 20 个配置上，Adaptive 的平均缺页次数为 **{mean('adaptive'):,.2f}**，比 Random 少 **{100*(1-mean('adaptive')/mean('random')):.2f}%**，比 LRU 少 **{100*(1-mean('adaptive')/mean('lru')):.2f}%**。",
        f"与各配置中表现最好的在线基线相比，Adaptive 有 **{wins} 个配置严格更好、{ties} 个持平、{losses} 个落后**。这些是 30 个固定种子的均值比较，不是对未知课堂轨迹的性能保证。OPT 是离线最优参照，Adaptive 的总体平均缺页仍比 OPT 多 **{100*(mean('adaptive')/mean('opt')-1):.2f}%**。", "",
        "## 1. 算法如何利用容量和访问特征", "",
        "一个程序接收页框数 F。小容量（F≤20）以 Random 起步，较大容量以 LRU 起步；后续策略不由文件名、页号或预先知道的轨迹类型决定。", "",
        "同时维护三个仅含页号的影子模拟器，分别执行 Random、LRU 和历史间隔预测。它们只处理已经发生的访问，用于比较过去一段窗口内的缺页次数。**影子状态没有页面内容，切换策略时不会把影子页面复制进真实内存。真实内存始终只有 F 个页框，只在当前缺页时装入当前页。**", "",
        "历史间隔预测为最近 H 个不同页号保留末次访问位置和间隔统计，包括已被淘汰的页。一个页再次出现时，用指数平滑更新访问间隔 g，V3 使用 g←0.5g+0.5Δ，首次重复直接令 g=Δ。预测参考间隔仅为 g，移除 V2 的波动附加项，避免一次长间隔长期压低该页的优先级。若距上次访问的时间还没超过该值，就用剩余间隔评分；若已经逾期，评分改为已经等待的时间，使过时页面逐渐失去保护。没有重复历史的页面优先考虑淘汰，评分相同时选最久未访问的页。这个预测是启发式，不是 OPT 的真实未来位置。", "",
        "每经过约 W/4 次访问，比较过去 W 次访问中三个影子策略的缺页数。F≤20 时切换门槛为 max(1, floor(W/50))；F>20 时提高到 max(1, floor(W/20))，候选策略必须比当前策略少超过该门槛才切换。比较只用截至前一次访问的结果。", "",
        "V3 保留 V2 的对齐机制：在 F>20 时，每 W 次访问把真实缓存的页号、最近访问位置和随机数状态复制到三个影子模拟器，作为下一轮比较的共同起点。复制方向始终为真实到影子。窗口内部仍允许策略切换，所以这只能减少状态不一致，不能保证影子收益完全兑现。F≤20 不重置影子缓存；V3 的间隔更新方式在所有容量均生效。", "",
        "默认 F≤20 时 H=max(32,16F)，F>20 时 H=max(32,8F)，避免保留太久以前的间隔。F≤20 时 W=max(32,4F)，F>20 时 W=2×max(32,4F)，所有课程轨迹使用同一组容量规则：", "",
        table(["页框 F","初始策略","比较窗口 W","历史页号上限 H"],
              [[f,"Random" if f<=20 else "LRU",max(32,4*f)*(1 if f<=20 else 2),max(32,(8 if f>20 else 16)*f)] for f in FRAMES]), "",
        "容量越大，算法保留更长的历史、用更长的窗口判断策略表现；但初始策略可以在运行中改变。这不是提前为每条测试轨迹选择最好的算法。", "",
        "## 2. 实验口径", "",
        "四条轨迹：qsort（sort1.txt，524 次访问 / 192 个不同页）、lu（41,832 / 531）、mm16（9,075 / 515）、mm32（67,235 / 1,667）。输入已经是十六进制虚拟页号。每次模拟从空内存开始，不预取。", "",
        "七种方法 × 四条轨迹 × 五档页框数，共 140 组配置。Random 和 Adaptive 各使用种子 0～29，共保存 **1,300 次正式运行**。其余五种算法为确定性算法。LFU 采用驻留期间累计频次、并列按 LRU 决胜；Second chance 采用 Clock 环形指针，新装入和命中都把访问位设为 1。", "",
        "以下表格中 Random / Adaptive 是 30 次运行的平均缺页次数，所以可能有小数；其他列为精确整数。每次真实运行的整数值、种子、标准差、最小值和最大值均已保存。另提供 [种子 0 的整数表](results/fault_counts_seed0.csv) 和 [完整宽表](results/fault_counts_table.csv)。", "",
        "## 3. 按课件示例绘制的对比图", "",
        "课件第 8 页示例采用分组柱状图，并把基准值归一化为 1。这里同时提供绝对缺页次数的分组柱状图，以及 LRU=1 的两柱对比图，避免只看比例而忽略实际数量。", "",
        "![各容量下七种方法的缺页次数](results/comparison_by_frames.png)", "",
        "图中 Adaptive 在小容量的优势较明显，mm32 在 50 个页框时也有大幅改善。V3 在 mm16/100 上进一步低于 LRU，在 mm16/50 与 mm32/100 上保持与 LRU 相同。误差线为 Random / Adaptive 的均值 ±1 个样本标准差，是固定轨迹上随种子变化的波动。", "",
        "![相对 LRU 归一化的缺页次数](results/normalized_vs_lru.png)", "",
        "灰柱是 LRU=1，深色柱为 Adaptive/LRU；低于 1 表示 Adaptive 缺页更少。右下角先对五档容量平均缺页次数，再相除。本次所有配置均不差于 LRU，但 qsort/100 仍比 Random 差，也不能据此保证未知轨迹。", "",
        "## 4. 各方法、各 frame 数的详细缺页次数", ""]
    explanations={
        "qsort":"小容量下历史间隔预测帮助保留即将重用的页面。50、100 个页框时 Adaptive 没有切换，全部使用 LRU；因此均为 199 次。100 个页框下 Random 的均值 196.30 反而更低，说明短轨迹的启动期和窗口长度会影响自适应收益。",
        "lu":"Adaptive 在五档容量上都优于在线基线。小容量阶段大部分时间采用间隔预测；50 个页框时在 LRU 和预测之间切换，100 个页框时以预测为主。容量增大仍能显著降低缺页，但与 OPT 的差距表明历史估计尚不能准确捕获所有未来复用。",
        "mm16":"V3 在 100 页框时平均缺页 2,714.17 次，相比 V2 的 2,964 次减少 8.43%。50 页框仍与 LRU 相同。",
        "mm32":"20 页框时 V3 比 V2 少 812 次，50 页框时少 454 次。100 页框仍为 19,604 次，与 LRU 持平。10 页框多 4 次，属于本轮退化配置。"}
    for dataset in DATASETS:
        paragraphs.extend([f"### {dataset}", "",table(["Frames",*[NAMES[a] for a in ALGORITHMS]],
            [[f,*[f"{float(data[(dataset,f,a)]['faults_mean']):,.2f}" if a in {"random","adaptive"} else f"{int(data[(dataset,f,a)]['faults_mean']):,}" for a in ALGORITHMS]] for f in FRAMES]),
            "",explanations[dataset],"",f"单独图：[PNG](results/faults_{dataset}.png) / [SVG](results/faults_{dataset}.svg)。",""])
    paragraphs.extend(["## 5. 总体平均与统计方式", "",table(["方法","20 个配置平均缺页次数","宏平均缺页率"],
        [[NAMES[a],f"{mean(a):,.2f}",f"{float(overall[a]['macro_mean_fault_rate'])*100:.2f}%"] for a in sorted(ALGORITHMS,key=mean)]),"",
        "先对随机算法的种子取平均，再对四条轨迹 × 五档容量等权平均。原始缺页次数的平均更受长轨迹数值大小影响；宏平均缺页率先除以各自访问次数，再等权平均。两种指标没有混用。", "",
        "## 6. 参数变化实验", "",
        "分别改变比较窗口因子 2、4、8（历史因子固定 16），以及历史因子 8、16、32（窗口因子固定 4）。每种设置都覆盖四条轨迹、五档容量、30 个种子，共 3,000 条参数实验记录，其中默认设置复用正式实验的 600 条记录。", "",
        "![窗口与历史长度的参数敏感性](results/parameter_sensitivity.png)", ""])
    parameters=read("parameters_summary.csv")
    variants=[(2,16),(4,16),(8,16),(4,8),(4,32)]
    parameter_table=[]
    for w,h in variants:
        chosen=[r for r in parameters if int(r["window_factor"])==w and int(r["history_factor"])==h]
        display=lambda value:f"{Decimal(str(value)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP):,}"
        parameter_table.append([w,h,*[display(statistics.mean(float(r['faults_mean']) for r in chosen if r['dataset']==ds)) for ds in DATASETS],
                                display(statistics.mean(float(r['faults_mean']) for r in chosen))])
    paragraphs.extend([table(["窗口因子","历史因子",*DATASETS,"总体平均"],parameter_table),"",
        "表内每条轨迹先平均五档容量。V3 在 F>20 时对窗口再乘 2，对历史因子减半并向下取整至至少 1。默认 4/16 与容量规则通过已知课程轨迹的探索确定；本表属于参数敏感性分析，不能当作未见数据上的证据。没有按文件名或页号选择参数。", "",
        "## 7. 构造轨迹回归测试", "",
        "补充六类压力测试：纯顺序扫描、73 页循环、149 页循环、热点夹杂扫描、访问阶段切换、256 页均匀独立随机访问。每类仍测试五档容量和七种算法，随机算法各 30 个种子，共 1,950 次运行。轨迹由脚本确定性生成，保留文件和校验值。这些数据不是老师的隐藏测试集，不能代替现场验证。", "",
        "![构造轨迹压力测试](results/synthetic_comparison.png)", ""])
    synthetic=read("synthetic_summary.csv")
    synthetic_table=[]
    for ds in dict.fromkeys(r["dataset"] for r in synthetic):
        synthetic_table.append([ds,*[f"{statistics.mean(float(r['faults_mean']) for r in synthetic if r['dataset']==ds and r['algorithm']==a):,.2f}" for a in ["random","lru","opt","adaptive"]]])
    paragraphs.extend([table(["构造轨迹","Random","LRU","OPT","Adaptive"],synthetic_table),"",
        "表中是五档容量平均缺页次数，图中是平均缺页率。纯扫描没有复用，所有方法均缺页 6,000 次。六条构造轨迹在 V1 阶段已经看过，本次只作为回归测试，不能称为全新验证集；V3 参数固定后重新运行，未据此进一步调参。课堂的新轨迹仍需现场评测。", "",
        "## 8. 开销与局限", "",
        "Adaptive 维护真实缓存 F 个页框、三个影子缓存的页号元数据、最多 H 个历史页号，以及 W 条三策略缺页记录。默认参数下额外元数据为 O(F)，并非零开销；影子缓存不占用额外的真实页面内容。每次访问期望 O(1) 更新历史；真实或影子策略需要选择 LRU/预测淘汰对象时会扫描 F 个页框，整个模拟的期望上界为 O(NF)。", "",
        "下表是在相同 WSL 环境的 Release 可执行程序上，运行 mm32 / 100 个页框 / seed=0 的端到端耗时。每种方法预热一次，再以打乱顺序测量 10 次。包含进程启动、输入解析和模拟，不是实际操作系统的缺页处理延迟。", ""])
    timing=read("timing_summary.csv")
    paragraphs.extend([table(["方法","耗时中位数（ms）","最小值","最大值"],
        [[NAMES[r["algorithm"]],f"{float(r['median_ms']):.2f}",f"{float(r['min_ms']):.2f}",f"{float(r['max_ms']):.2f}"] for r in timing]),"",
        "Adaptive 的模拟开销明显高于简单基线，这是维护影子策略和间隔预测的代价。优化缺页次数不等于使模拟器本身运行更快。策略选择还有窗口滞后、预测错误和真实/影子缓存状态不一致等限制，没有对任意未知轨迹优于全部基线的保证。", "",
        "## 9. 正确性与复现", "",
        "Release、AddressSanitizer 和 UndefinedBehaviorSanitizer 测试通过。算法测试包括 1,093 条小轨迹 × 四档测试容量 × 七种算法，OPT 对照独立穷举最优解，Second chance 对照队列参考实现。另验证 V1/V2 在 F≤20 时逐步决策一致。", "",
        "增加了在线前缀不变性检查：截断未来后缀时，前面的命中、页框和淘汰决定保持一致。另检查页号重命名不变性、随机种子复现、策略切换后的物理容量约束、历史上限与参数范围。正式实验验证 OPT 下界、LRU/OPT 容量单调性，并做了 28 次足够内存检查；真实轨迹的 LRU 结果也与独立重用距离计算一致。", "",
        "复现命令见 [README](README.md)。[raw.csv](results/raw.csv) 保存全部正式运行，[summary.csv](results/summary.csv) 保存每组均值、标准差和极值；[parameters_raw.csv](results/parameters_raw.csv)、[synthetic_raw.csv](results/synthetic_raw.csv) 保存补充实验原始记录。所有图均附 PNG 和 SVG，可直接插入汇报 PPT。", "",
        "现有四条课程轨迹已用于理解访问规律，因此不能把它们称为真正未见的泛化评测。课堂新轨迹必须按输入顺序运行，不能预扫未来频次或下一次访问位置；只有 OPT 基线允许使用未来信息。", ""])
    versions=read("version_comparison.csv")
    old=statistics.mean(float(r['v2']) for r in versions)
    paragraphs.extend(["## 10. 本轮优化前后对照", "",
        f"V2 总体平均 {old:,.2f}，V3 为 {mean('adaptive'):,.2f}，进一步降低 {100*(1-mean('adaptive')/old):.3f}%。20 个配置中 9 个改善、6 个完全一致、5 个退化。", "",
        table(["轨迹","Frames","V2","V3","缺页变化"],[[r['dataset'],r['frames'],f"{float(r['v2']):,.2f}",f"{float(r['v3']):,.2f}",f"{float(r['difference']):+,.2f}"] for r in versions]),"",
        "![V2 与 V3 在大容量的对比](results/version_comparison.png)","",
        "保留 `--adaptive-version 1|2` 可复现旧版，默认是 3。[versions_raw.csv](results/versions_raw.csv) 保存相同种子下三版的 1,800 条记录。旧版 1,200 条记录与上一提交逐字段一致。探索阶段先在种子 0～4 上比较 15 个候选方案，包括历史长度、平滑系数、波动惩罚与切换门槛，选择课程配置平均缺页最少者，再固定规则用 0～29 复测。[v3_search.csv](results/v3_search.csv) 保存全部 1,500 条初筛结果，`scripts/explore_v3.py` 可从固定的 V2 提交重建。已知课程数据参与了选择，收益只是本数据上的实测结果。", ""])
    fresh=read("fresh_summary.csv")
    fresh_table=[]
    for ds in dict.fromkeys(r["dataset"] for r in fresh):
        av=lambda a:statistics.mean(float(x["faults_mean"]) for x in fresh if x["dataset"]==ds and x["algorithm"]==a)
        fresh_table.append([ds,*[f"{av(a):,.2f}" for a in ["adaptive_v2","adaptive","lru","opt"]],f"{100*(av('adaptive')/av('adaptive_v2')-1):+.3f}%"])
    paragraphs.extend(["## 11. 新增构造压力测试", "",
        "在冻结 V3 之前定义四类额外轨迹，在规则固定后第一次查看结果，未根据结果继续调参。这些是构造测试，仍不能当作老师的隐藏数据。包括轮换热点、相邻访问顺序扰动的 97 页循环、7 组各 80 页交替回访、8 页热点混入 70 页扫描。每条覆盖五档容量，V2、V3、Random 各 30 个种子，其余基线各一次，共 1,900 条记录。", "",
        table(["轨迹","V2","V3","LRU","OPT","V3 相对 V2"],fresh_table), "",
        "表内先对五档容量等权平均，正百分比表示退化。扰动循环平均退化 0.938%，其中 10/20/50 页框分别多 70.77/128.43/38 次缺页；快速更新更容易受短期扰动影响。轮换热点的整体收益很小，但 5 页框退化约 42.97 次。热点加扫描在 5 页框多 5.47 次；交替回访完全相同。课程数据上的总体收益不能外推为所有新轨迹都会改善。", "",
        "![新增构造轨迹 V2/V3 对照](results/fresh_comparison.png)", "",
        "全部整数运行与轨迹校验值见 [fresh_raw.csv](results/fresh_raw.csv)、[fresh_summary.csv](results/fresh_summary.csv) 和 [fresh_metadata.json](results/fresh_metadata.json)。"])
    (ROOT/"REPORT.md").write_text("\n\n".join(p for p in paragraphs if p!="")+"\n",encoding="utf-8")
    print("Generated REPORT.md, mean count table and seed-0 integer count table.")


if __name__ == "__main__":
    main()
