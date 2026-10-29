# V5：论文调研与有效、无效的探索

本轮目标是继续压低缺页次数，允许组合、切换和有取舍的优化。没有把“所有样例都不退步”设成准入门槛。四条课程轨迹和原有十条构造轨迹用于开发；新验证集只在规则冻结后生成，未据此调参。

## 论文与本实现的关系

| 原始来源 | 与本任务有关的思想 | 本次处理 |
|---|---|---|
| [Learning Relaxed Belady for Content Distribution Network Caching，NSDI 2020](https://www.usenix.org/conference/nsdi20/presentation/song) | 根据已观察到的复用事件学习未来使用距离，训练标签延迟到达 | 借鉴标签时序与历史特征；自行实现有界条件分布，没有移植 LightGBM，也不称为 LRB 复现 |
| [LHD: Improving Cache Hit Rate by Maximizing Hit Density，NSDI 2018](https://www.usenix.org/conference/nsdi18/presentation/beckmann) | 页面存活年龄会影响其未来命中价值 | 借鉴按当前等待时间条件化的思路；本作业用等大小页、有限间隔簇和删失惩罚，公式不等同于 LHD |
| [Driving Cache Replacement with ML-based LeCaR，HotStorage 2018](https://www.usenix.org/conference/hotstorage18/presentation/vietri) | 通过在线反馈组合不同缓存策略 | 对比了动态选择和加权成员投票；最终采用实测更好的动态选择，并保留所有失败候选 |
| [Better and Simpler Learning-Augmented Online Caching，2020](https://arxiv.org/abs/2005.13716) | 预测与在线缓存算法组合 | 用于理解预测误差和组合的边界；本实现未证明或声称继承其竞争比 |
| [ARC，FAST 2003](https://www.usenix.org/legacy/event/fast03/tech/full_papers/megiddo/megiddo.pdf) | 自适应平衡近期性与频率 | 独立实现等大小页对照和物理驻留检查 |
| [FIFO Queues Are All You Need for Cache Eviction，SOSP 2023](https://jasony.me/publication/sosp23-s3fifo.pdf) | 小队列过滤与主队列频率反馈 | 实现 `s3fifo_demand`；一次物理淘汰后停止，以符合每次缺页只装入当前页的作业模型。不是原论文所有对象大小与准入语义的完整复现 |
| [SIEVE，作者的 USENIX 说明](https://www.usenix.org/publications/loginonline/sieve-cache-eviction-can-be-simple-effective-and-scalable) | FIFO 次序、访问位和淘汰游标 | 独立实现等大小页对照；没有假设 Web 缓存上的优势会直接迁移到本作业 |

## 真正有收益的变化

页面自身的间隔均值不能完整表达多峰复用。V5 同时维护按最近间隔、相邻间隔对、前驱页、两个前驱、已观察后继、前后邻居等分组的复用分布。共享分组让不同页面之间也能借用历史信息。

标签只在页面再次返回时形成。历史记录被容量限制淘汰时，只能知道“截至目前还没返回”，因此记为删失观察；不能宣称它以后绝不回来。估计分数只保留大于当前年龄的历史间隔，删失观察加入有限惩罚。这是启发式估计，不声称统计无偏。

每个分组最多保留 16 个加权间隔簇。新标签到达时旧质量乘 0.98；超过 16 簇，合并相对间隔最接近的相邻簇。这样保留多个复用尺度，而不是只留下最近 16 个样本。总分组数有界，线上不训练外部大模型。

“后继页”是上一请求之后**已经到达**的当前请求。例如刚处理过 A，现在收到 B，才把 B 记作 A 的后继。B 之后真正的下一页始终未知。

最终保留 25 个候选：原 V4 的 7 个，加上转换模型、条件分布、最近间隔、交替间隔、LRU-2 分数近似和已完成间隔模式等 18 个。每个请求都更新影子的实际命中/缺页；真实缓存通过合法淘汰逐步跟随当前获胜者。

## 尝试过但未采用的方向

| 方向 | 结论 |
|---|---|
| 单页复用间隔转换 | 有收益，但不及条件分布与上下文组合 |
| 前驱、后继、双前驱、邻居条件模型 | 有效的新信号，保留到最终候选集合 |
| 最近样本环 vs 衰减间隔簇 | 间隔簇更好，保留后者 |
| 线性、乘法、交替趋势外推；严格超时判死 | 没有成为胜出方案，保留原始结果 |
| 1–4 阶 Markov 自动延伸未来路径 | 未超过最终方案，额外开销不划算 |
| 按衰减缺页损失加权的缓存成员投票 | 不及动态跟随单个专家；并非只尝试原 V4 的 7 个专家 |
| ARC / S3-FIFO demand / SIEVE | 课程平均分别为 22,852.50 / 21,648.60 / 27,112.05，高于 V4 与 V5；不纳入默认候选 |
| 初始专家、窗口、切换门槛、专家子集 | 搜索后选用 25 个专家、最近间隔起步、W=max(32,8F)、32 次暖机 |
| 分布衰减、簇数、删失惩罚、最少标签 | 选中 0.98 / 16 / max(64,8F) / 4；参数差异和不利结果都留在 CSV |

另一位 agent 提供的实验摘要表明：延长 V4 重放、秩投票、单页间隔模式和历史 OPT 重放的收益有限。该摘要用于避免重复方向；由于没有拿到其原始记录，未把其数值并入本仓库可复现实验。这里的所有新数字来自本地保存的代码和 CSV。

## 如何复现研究

这些程序仅用于开发，不是现场入口。研究驱动会读完整输入以依次喂给在线对象；预测对象仍只收到当前页。参数搜索跨完整开发文件比较结果，**不能把这种离线搜索用于未知现场文件**。

```bash
python3 scripts/explore_v5.py --model initial --pool sweep --name controller_sweep
python3 scripts/explore_v5.py --model context --pool sweep --name context_controller_sweep
python3 scripts/explore_v5.py --model density --pool sweep --name density_controller_sweep
python3 scripts/explore_v5.py --model trend --name predictors_trend
python3 scripts/explore_v5.py --model markov --name predictors_markov
python3 scripts/explore_v5_combinations.py
python3 scripts/explore_v5_density.py
python3 scripts/explore_v5_density_refine.py
python3 scripts/reproduce_v5_baselines.py
```

`results/v5/research/*_metadata.json` 保存每次探索的源码哈希、输入哈希、专家顺序和参数。总计 33,110 行开发/对照记录，其中 70 行是正式版与选中原型的对照。部分候选重复出现，用于不同消融；不能把记录行数说成不同算法数。

研究实现不参与正式链接。默认程序仅编译 `src/`；不依赖论文代码、Python、网络、预训练权重、文件名规则、预先保存的答案或未来页面。
