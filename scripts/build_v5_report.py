#!/usr/bin/env python3
"""Generate the current report from final measurements, preserving V4 history."""
import csv,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/v5'
def read(name):
    with (OUT/(name+'.csv')).open() as f:return list(csv.DictReader(f))
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|',*['| '+' | '.join(map(str,r))+' |' for r in rows]])
def main():
    means=read('course_means');course=read('course_summary')
    avg={a:statistics.mean(float(r['average_faults']) for r in means if r['algorithm']==a) for a in dict.fromkeys(r['algorithm'] for r in means)}
    val=lambda d,f,a:float(next(r['faults_mean'] for r in course if r['dataset']==d and r['frames']==str(f) and r['algorithm']==a))
    text=['# Adaptive V5 实验报告',
      f"V5 课程平均缺页 **{avg['adaptive_v5']:,.2f}**，V4 为 **{avg['adaptive_v4']:,.2f}**，队友 V3 为 **{avg['adaptive_v3']:,.2f}**。相对 V4 降低 **{100*(1-avg['adaptive_v5']/avg['adaptive_v4']):.3f}%**，相对 V3 降低 **{100*(1-avg['adaptive_v5']/avg['adaptive_v3']):.3f}%**，相对 LRU 降低 **{100*(1-avg['adaptive_v5']/avg['lru']):.2f}%**。",
      '这次优先追求更少缺页，允许组合和切换，也保留有收益但个别配置退步的方案。开发结果不能证明未知课堂文件必胜；没有“已经做到算法极限”的结论。',
      '[运行说明](QUICKSTART.md) · [论文与探索记录](RESEARCH_V5.md) · [15 页课件](presentation/contest-v5.pptx) · [讲稿](presentation/V5_SPEAKER_NOTES.md) · [V4 存档](REPORT_V4.md) · [V3 存档](REPORT_V3.md)',
      '## 1. 任务和评价口径',
      '一行一个页号，默认十六进制；分别分配 5、10、20、50、100 个物理页框，从空缓存开始，只按需载入当前页面。最终分数为五个缺页次数的算术平均。四条课程轨迹总体均值等价于 20 个配置等权平均。不能将缺页率、平均次数、seed 最小值混为一谈。',
      'Random 与 V3/V4/V5 均使用 seed 0–29，保存每次整数计数与样本标准差；其他基线确定性运行一次。课程 V5 在 30 个种子下计数一致。LFU 只统计当前驻留期频次，卸载清零，平局按 LRU。OPT 读取未来，仅作离线下界。',
      '## 2. V5 的新信息和组合',
      'V5 保留 V4 的 Random、LRU、间隔 EWMA、历史片段重放、衰减频率、新页先验、锚点签名；再加入 18 个历史间隔/上下文候选，共 25 个影子。新增核心是**已等待年龄条件下的复用分布**，不是单纯调整原七个专家的选择器。',
      '历史表限制 H=max(32,F×h)，默认 h=16；F>20 时 h=8。每个页面保存最近时间、最近两次及最多八次间隔、分组键。分组包括页面+间隔、间隔、间隔对、前驱、重复次数、双前驱、已知后继与前后邻居。模型总数最多 16H，每组最多 16 个加权间隔簇。标签到达时旧质量乘 0.98；过多簇合并相对间距最小的相邻两簇。',
      '页面实际返回后，才训练其上次访问的特征；记录被历史表淘汰时加入删失标记。对年龄 a，只累计大于 a 的有限间隔簇：分子为 Σ w(g−a) + w_c×max(1,T−a)，分母为 Σ w，其中 T=max(64,8F)。分母为零时分数为无穷。这里的删失惩罚是工程启发式，不等价于知道以后不会返回。至少观察四个标签才使用条件估计，否则退回最近间隔。',
      '后继信息严格来自已经到达的请求：收到 B 时，可以知道上一请求 A 的后继为 B，但看不到 B 之后的请求。`prepare(current)` 只填入这项已知事实；真实复用标签在所有本次淘汰决定之后更新。',
      '选择器从“最近一次复用间隔”开始。W=max(32,8F)，先完成 32 个请求，每 max(1,floor(W/8)) 次检查一次；候选的历史衰减缺页损失领先超过 max(1,W/20) 才切换。每次损失按 L←(1−1/W)L+miss 更新。选策略使用本次请求之前的损失。',
      '真实缓存缺页且已满时，只淘汰它持有、而选中影子已经不持有的一个页，再载入当前页。目标影子已处理当前页，因此至少有一个合法候选。命中时不替换，切换时不复制影子页，也不把影子命中当作真实命中。',
      '数值流式入口与 `OnlineAdaptiveV5::access(page)` 无未来数组、文件句柄或轨迹长度。真实页面内容最多 F 页，影子和模型都是页号/统计元数据；元数据 O(F)，固定专家/簇数下期望时间 O(NF)。token 标签模式另有 O(U) 字符串映射。实验 CLI 为运行 OPT 才读取完整数组。',
      '为保留历史源码哈希，V4 的 `src/context.cpp`、`src/adaptive.cpp`、`include/paging.hpp` 未修改。C++ 旧 `simulate` 默认选项仍是 V4；V5 可显式传 `{4,16,5}` 或用新流式类。两个 CLI 入口默认 V5，V1–V4 仍可显式复现。',
      '## 3. 课程数据：全部配置',
      table(['方法','20 配置平均缺页'],[[a,f'{avg[a]:,.4f}'] for a in ['opt','adaptive_v5','adaptive_v4','adaptive_v3','random','lru','second_chance','fifo','lfu']])]
    deltas=[val(d,f,'adaptive_v5')-val(d,f,'adaptive_v4') for d in ['qsort','lu','mm16','mm32'] for f in [5,10,20,50,100]]
    text += [f"相对 V4：**{sum(x<0 for x in deltas)} 改善、{sum(x==0 for x in deltas)} 持平、{sum(x>0 for x in deltas)} 退步**。V5 相比 OPT 仍高 **{100*(avg['adaptive_v5']/avg['opt']-1):.2f}%**。从 V3 到 V5 消除了 V3 与 OPT 之间约 **{100*(avg['adaptive_v3']-avg['adaptive_v5'])/(avg['adaptive_v3']-avg['opt']):.2f}%** 的缺页差距。这个差距比例不是总体缺页下降比例。"]
    keys=['random','fifo','opt','lfu','lru','second_chance','adaptive_v3','adaptive_v4','adaptive_v5']
    for ds in ['qsort','lu','mm16','mm32']:
        text += ['### '+ds,table(['F','Random','FIFO','OPT','LFU','LRU','Clock','V3','V4','V5'],[[f,*[f'{val(ds,f,a):,.2f}' for a in keys]] for f in [5,10,20,50,100]])]
    text += ['明显收益：LU/F=100 从 17,452 降到 15,954，少 1,498 次（8.58%）；mm32/F=100 从 19,604 降到 18,022，少 1,582 次（8.07%）；mm16/F=100 从 2,373 降到 2,095，少 278 次（11.72%）。不利项：LU/F=5 多 8 次，mm16/F=20 多 15 次。',
      '## 4. 开发、回归和新增验证分开报告',
      '`frozen_algorithm.json` 记录固定规则、源码 SHA-256 与冻结时间。选中原型与正式版在全部 70 个开发配置上的缺页数和切换次数完全相同；之后才生成新的十类验证。原 V4 的验证数据已经看过，本轮只称“已有回归集”。新构造验证不是老师的隐藏测试，未用于继续改参数。']
    for suite,label in [('development','已有 10 类开发数据'),('regression','已有 8 类回归数据'),('holdout','冻结后新增 10 类构造验证')]:
        rows=read(suite+'_means');sub=[]
        for ds in dict.fromkeys(r['dataset'] for r in rows):
            d={r['algorithm']:float(r['average_faults']) for r in rows if r['dataset']==ds}
            sub.append([ds,f"{d['adaptive_v4']:.2f}",f"{d['adaptive_v5']:.2f}",f"{100*(1-d['adaptive_v5']/d['adaptive_v4']):+.3f}%"])
        a,b=[statistics.mean(float(r['average_faults']) for r in rows if r['algorithm']==key) for key in ['adaptive_v4','adaptive_v5']]
        text += ['### '+label,table(['轨迹','V4','V5','相对 V4 减少（负数为退步）'],sub),f'总体：{a:.4f} → {b:.4f}，减少 **{100*(1-b/a):.3f}%**。']
    perf=json.loads((OUT/'performance.json').read_text());large=perf['unique_scan_scaling'][-1]
    text += ['## 5. 运行代价与验证',
      f"本机 Release、mm32 五档模拟的 5 次中位耗时：V3 {perf['median_milliseconds']['3']/1000:.3f}s，V4 {perf['median_milliseconds']['4']/1000:.3f}s，V5 {perf['median_milliseconds']['5']/1000:.3f}s。更多专家明显增加模拟开销；本次优先优化缺页次数。这是端到端模拟时间，不是操作系统真实缺页处理延迟。",
      f"百万行不重复页逐行输入：五档均恰好 1,000,000 次缺页，耗时 {large['elapsed_seconds']:.2f}s，峰值 RSS {large['peak_rss_kib']/1024:.2f} MiB。1 万行与 100 万行的峰值基本相同，支持数值模式空间不随输入长度增长的实现约束；不是对任意平台绝对内存的保证。",
      'Release 与 ASan/UBSan 均通过 CTest 3/3。新测试穷举 3 个页号、长度 0–7 的所有序列，4 档容量、2 个种子；以独立动态规划检查 OPT 下界。长序列逐请求检查真实驻留/淘汰、前缀不变、64 位双射重命名、流式/向量一致、历史和模型上界。CLI 覆盖 BOM、CRLF、空白、路径空格、stdin、hex/decimal/token、空文件、非法行、五档平均与无部分成绩。',
      '最终四组评测共 **20,000 次运行**，均值和标准差由原始整数重新审计；另有 **33,110 行研究/对照记录**。旧 V3 的 1,300 条记录重跑逐字节一致；本轮课程评测中的 V3/V4 与原始课程记录一致。ARC/S3-FIFO demand/SIEVE 通过每策略 39,364 组短序列/容量的合法物理内存检查。',
      'Linux 可执行文件已运行。Windows x64 文件采用 MinGW 静态交叉编译，检查系统 DLL 依赖，但没有声称在真实 Windows 上执行测试。',
      '## 6. 复现和交付',
      '```bash\nbash run.sh "老师给的文件.txt"\nbash run.sh data/mm32.txt --adaptive-version 4  # 显式复现旧演练\npython3 scripts/learned_experiments.py          # 约 20,000 次正式评测\npython3 scripts/learned_benchmark.py\npython3 scripts/build_v5_report.py\n.venv/bin/python presentation/build_v5.py\npython3 scripts/verify_v5.py\n```',
      '新默认 mm32 五档：**55006、48712、37986、19730、18022**，平均 **35891.20**。旧 V4 为 **36558.20**，仅在显式 `--adaptive-version 4` 时使用旧数字。',
      '研究配置、无效结果与原论文链接见 [RESEARCH_V5.md](RESEARCH_V5.md)。不需要现场联网、先读完整文件选择参数、文件名识别、预存答案或多次挑种子。新旧 PPT、报告和结果明确分开；PR 更新沿用原分支。',
      '## 7. 尚未解决的空间',
      'V5 仍比 OPT 有差距，条件分布也可能受模式变化和稀疏标签影响。进一步探索可考虑更强的上下文特征、低成本动态专家集合和更好的删失估计；这些方向没有被证明无收益。本次交付的是已经实现、验证、记录代价和退步的明显改进，不是“做无可做”的承诺。']
    (ROOT/'REPORT.md').write_text('\n\n'.join(text)+'\n')
    print('Generated REPORT.md from final V5 CSVs')
if __name__=='__main__':main()
