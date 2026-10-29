#!/usr/bin/env python3
"""Build the current 15-slide deck from the recorded V5 results."""
import csv,json,statistics
from pathlib import Path
import build_v4 as style
from build_v4 import textbox,table,bullets,chart,prs,notes,TEAL,PURPLE,GRAY,INK
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/v5'
def read(name):
    with (OUT/(name+'.csv')).open() as f:return list(csv.DictReader(f))
def slide(title,script,source='REPORT.md',seconds=40):
    s=style.slide(title,script,source,seconds)
    for shape in s.shapes:
        if shape.has_text_frame:
            for p in shape.text_frame.paragraphs:
                for run in p.runs:run.text=run.text.replace('Adaptive V4','Adaptive V5')
    return s
def main():
    course=read('course_summary');means=read('course_means')
    avg={a:statistics.mean(float(r['average_faults']) for r in means if r['algorithm']==a) for a in dict.fromkeys(r['algorithm'] for r in means)}
    val=lambda d,f,a:float(next(r['faults_mean'] for r in course if r['dataset']==d and int(r['frames'])==f and r['algorithm']==a))
    gain=100*(1-avg['adaptive_v5']/avg['adaptive_v4'])
    s=slide('更进一步：学习复用分布，动态组合策略','V5 在已有 V4 上加入新的预测信号。今天报告的数字全部来自正式程序，四条课程数据参与了开发，额外构造验证与开发结果分开呈现。',seconds=25)
    textbox(s,f"课程平均缺页  {avg['adaptive_v5']:,.2f}\n相对 V4 进一步减少  {gain:.2f}%\n相对队友 V3 减少  {100*(1-avg['adaptive_v5']/avg['adaptive_v3']):.2f}%",.85,1.8,11.6,3.5,30,TEAL,True)
    textbox(s,'每行一个页号 · 五档页框与平均值 · 当前页逐行输入',.85,6.1,11.6,.6,21,GRAY)
    s=slide('评分不变；增加可利用的历史信息','输入格式和评分保持不变。仅靠一页的间隔均值可能无法表达多种访问模式。相同页面可能在不同程序路径下出现，所以同时考虑间隔、前驱页、已观察到的后继页。',seconds=40)
    bullets(s,['每档从空内存开始：5、10、20、50、100 页框。','平均缺页次数 = 五档整数缺页次数相加 ÷ 5。','新信号：间隔分布、连续两次间隔、前后访问上下文。','训练标签：页面实际返回后，才记录本次复用间隔。','在线接口只收到当前页号，没有未来数组和文件句柄。'])
    s=slide('论文提供方向；本作业重新实现与验证','参考 LRB 的延迟标签和复用预测、LHD 的条件存活思想，以及在线缓存组合方法。这里不是 LightGBM 版 LRB，也没有声称复现论文得分或继承竞争比。ARC、S3-FIFO、SIEVE 另做了适配本作业的对照。',source='RESEARCH_V5.md；原论文链接',seconds=45)
    table(s,['来源','借鉴的思想'],[['LRB · NSDI 2020','只用已经发生的返回事件形成训练标签'],['LHD · NSDI 2018','页面已经存活多久，会改变其后续价值'],['LeCaR · HotStorage 2018','根据在线反馈组合策略'],['ARC / S3-FIFO / SIEVE','实测对照；不直接假设新论文一定更好']],size=20)
    s=slide('条件复用分布：等待时间本身就是信息','举例只是解释条件化，不是本机测量。若过去间隔主要为 10 与 100，而页面已等待 20，那么短间隔那一类已经不适合直接预测当前返回时间。实现把已结束的间隔合并为最多 16 个加权簇，并以 0.98 衰减旧标签。',source='src/reuse_model.hpp',seconds=55)
    textbox(s,'历史间隔：10、100；当前已等待：20',.85,1.6,11.7,.7,28,PURPLE,True)
    bullets(s,['仅平均：可能把两种模式混成一个不常出现的值。','条件估计：只保留间隔大于当前等待时间的历史质量。','最多 16 个间隔簇；旧证据乘 0.98，适应访问变化。','被历史表淘汰的页面记为删失观察，加有限惩罚。','分别按间隔、间隔对、前驱、后继等上下文学习。'],y=2.7,size=21)
    s=slide('25 个专家竞争；真实缓存仍只有 F 页','25 个专家中包括 V4 的七个；其余是间隔转换和条件估计。选择器依据完成请求的衰减损失，真实缺页只从实际驻留页中淘汰一个不被目标影子保留的页面。只装当前请求页。已知后继是上一请求的后继，也就是此刻已到达的当前页，不是偷看下一页。',source='src/learned.cpp；include/learned.hpp',seconds=60)
    bullets(s,['候选：LRU、频率、片段重放、间隔预测、上下文条件分布等。','损失 L ← (1 − 1/W)L + 本次影子缺页；W = max(32, 8F)。','先完成 32 次请求，再每 W/8 次比较；领先超过 max(1, W/20) 才切换。','选择只用已完成请求；初始策略为最近一次复用间隔。','真实页框逐次合法替换；影子仅保存页号和统计。'],size=20)
    s=slide('课程总体：正式程序的完整对照','四条课程轨迹乘五档页框等权平均；Random 和三个 Adaptive 版本都保留 0 到 29 相同种子。OPT 是读取真实未来的离线参照。',source='results/v5/course_means.csv',seconds=45)
    keys=['opt','adaptive_v5','adaptive_v4','adaptive_v3','random','lru','second_chance','fifo','lfu']
    chart(s,['OPT','V5','V4','V3','Random','LRU','Clock','FIFO','LFU'],[('Mean faults',[avg[k] for k in keys])],.7,1.4,12,4.8)
    textbox(s,f"V4 → V5：{avg['adaptive_v4']:,.2f} → {avg['adaptive_v5']:,.2f}；降低 {gain:.2f}%",.85,6.25,11.7,.5,22,TEAL,True)
    s=slide('收益集中在哪里：逐轨迹均值','这些轨迹参与开发，不能称为盲测。大页框下的 LU 和矩阵轨迹有更多可利用的复用信息；小幅退化也保留。完整五档数字在附录，现场不能先跑一遍再挑最优算法。',source='results/v5/course_summary.csv',seconds=45)
    rows=[]
    for ds in ['qsort','lu','mm16','mm32']:
        values=[statistics.mean(val(ds,f,a) for f in [5,10,20,50,100]) for a in ['opt','adaptive_v3','adaptive_v4','adaptive_v5']]
        rows.append([ds,*[f'{v:,.2f}' for v in values],f'{100*(1-values[3]/values[2]):.2f}%'])
    table(s,['Trace','OPT','V3','V4','V5','较 V4 减少'],rows,size=18)
    s=slide('没有收益的方向也保留','论文算法适用负载不同。这里的 S3-FIFO 为满足一次缺页只换入一个页面而做了 demand paging 适配，不能当作论文原版排行榜。加权投票、线性趋势外推、Markov 自动延伸都没有成为最终胜出方案。',source='results/v5/research/；RESEARCH_V5.md',seconds=45)
    baseline=list(csv.DictReader((OUT/'research/literature_baselines.csv').open()))
    rows=[[a,f'{statistics.mean(int(r["faults"]) for r in baseline if r["algorithm"]==a and r["dataset"].startswith("data/")):,.2f}'] for a in ['arc','s3fifo_demand','sieve']]
    table(s,['研究对照','课程平均缺页'],rows,y=1.4,size=20)
    textbox(s,'组合方式也实测：加权投票未超过最终的动态切换。\n最终参数依据课程与开发数据选择；没有万能最优结论。',.85,4.7,11.6,1.4,21,GRAY)
    s=slide('冻结后验证：与开发结果分开','冻结源代码后生成十类新构造轨迹，不依据它们继续调参。原来 V4 的八类验证已经看过，因此此次明确称为回归集。它们都不是老师的隐藏文件。各类别退化记录在报告中。',source='results/v5/*_means.csv；frozen_algorithm.json',seconds=50)
    rows=[]
    for suite,label in [('development','10 类已有开发'),('regression','8 类已有回归'),('holdout','10 类新构造验证')]:
        m=read(suite+'_means');values=[statistics.mean(float(r['average_faults']) for r in m if r['algorithm']==a) for a in ['adaptive_v4','adaptive_v5']]
        rows.append([label,*[f'{v:,.2f}' for v in values],f'{100*(1-values[1]/values[0]):.2f}%'])
    table(s,['集合','V4','V5','较 V4 减少'],rows,size=21)
    s=slide('代价与验证：用计算换更少缺页','25 个影子和条件分布增加了模拟时间。结果是本机 Release 程序解析与五档模拟的端到端耗时，不是操作系统真实缺页延迟。数值模式内存随页框数有界；字符串模式另有标签映射。',source='results/v5/performance.json；tests/test_learned.cpp',seconds=45)
    perf=json.loads((OUT/'performance.json').read_text());large=perf['unique_scan_scaling'][-1]
    bullets(s,[f"mm32 五档中位耗时：V4 {perf['median_milliseconds']['4']/1000:.2f}s；V5 {perf['median_milliseconds']['5']/1000:.2f}s。",f"百万行纯扫描：每档恰好 1,000,000 次缺页；峰值 RSS {large['peak_rss_kib']/1024:.1f} MiB。",'Release、ASan、UBSan：真实驻留、命中、淘汰与均值检查。','穷举短序列对照精确 OPT；前缀、页号重命名、流式与向量一致。','保留 V1–V4；V4 算法源文件及既有计数均可复现。'],size=21)
    s=slide('现场只换文件路径，默认使用 V5','运行前先用课程数据演练。新二进制默认为 V5；如果展示旧版结果，必须显式加 adaptive-version 4。不要把新旧课件数字混在一起。未知输入可能不符合学习到的模式，不能保证第一。',source='QUICKSTART.md',seconds=35)
    textbox(s,'bash run.sh "老师给的文件.txt"',.85,1.6,11.7,.7,28,PURPLE,True)
    mm=[val('mm32',f,'adaptive_v5') for f in [5,10,20,50,100]]
    textbox(s,'mm32：'+' · '.join(f'{x:,.0f}' for x in mm)+f'\n平均：{statistics.mean(mm):,.2f}',.85,2.9,11.7,1.4,24,TEAL)
    textbox(s,'旧版对照：bash run.sh test.txt --adaptive-version 4\n默认十六进制；十进制加 --page-format decimal\n文档、逐种子记录、论文出处、源码哈希均随仓库提供。',.85,4.8,11.7,1.5,20,GRAY)
    keys=['random','fifo','opt','lfu','lru','second_chance','adaptive_v3','adaptive_v4','adaptive_v5']
    for ds in ['qsort','lu','mm16','mm32']:
        s=slide('附录：'+ds+' 完整缺页计数','所有值来自正式程序的逐种子结果汇总。Random 与 Adaptive 都使用相同的 0–29 种子。均值显示两位小数；原始每次运行都是整数。',source='results/v5/course_summary.csv',seconds=0)
        table(s,['Frames','Random','FIFO','OPT','LFU','LRU','Clock','V3','V4','V5'],[[f,*[f'{val(ds,f,a):,.2f}' for a in keys]] for f in [5,10,20,50,100]],y=1.8,size=12)
        textbox(s,'四条课程轨迹参与了开发与参数选择，不能作为独立验证。',.8,6.25,11.8,.5,18,GRAY)
    prs.save(ROOT/'presentation/contest-v5.pptx')
    text=['# V5 汇报讲稿','前 11 页约 8 分钟，后 4 页为完整结果附录。']
    for i,(title,seconds,script,source) in enumerate(notes,1):text += [f'## {i}. {title}（{seconds} 秒）',script,'数据与实现来源：'+source]
    (ROOT/'presentation/V5_SPEAKER_NOTES.md').write_text('\n\n'.join(text)+'\n')
    print('Saved 15 slides with notes and native chart/table data')
if __name__=='__main__':main()
