import fs from 'node:fs/promises';
import path from 'node:path';
import {PresentationFile,FileBlob} from '@oai/artifact-tool';
function applyPresentationChartFont(c,{fontFamily}) { for (const st of [c.legend.textStyle,c.dataLabels.textStyle,c.xAxis.textStyle,c.yAxis.textStyle,c.titleTextStyle]) if(st) st.typeface=fontFamily; }
const R=path.resolve(process.env.PAGING_PRESENTATION_BUILD || 'build/presentation');
const REF=process.env.PAGING_PRESENTATION_TEMPLATE;
if(!REF) throw new Error('Set PAGING_PRESENTATION_TEMPLATE to the user-supplied v22 template.');
const FONT='Microsoft YaHei', P='#6B4A82', D='#29203A', G='#69717A', T='#238A91', PALE='#E3DFFF';
const cols={random:'#69717A',fifo:'#B39945',opt:'#238A91',lfu:'#D0634F',lru:'#376D9A',second_chance:'#AAA0BA',adaptive:P};
const names={random:'Random',fifo:'FIFO',opt:'OPT',lfu:'LFU',lru:'LRU',second_chance:'Clock',adaptive:'Adaptive V3'};
const algs=Object.keys(names), frames=[5,10,20,50,100], datasets=['qsort','lu','mm16','mm32'];
const fmt=(v,d=0)=>Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const mean=a=>a.reduce((s,x)=>s+x,0)/a.length;
try{
const data=JSON.parse(await fs.readFile(R+'/data.json','utf8'));
const get=(ds,f,a)=>Number(data.summary.find(r=>r.dataset===ds&&+r.frames===f&&r.algorithm===a).faults_mean);
const overall=a=>Number(data.overall.find(r=>r.algorithm===a).mean_faults);
const p=await PresentationFile.importPptx(await FileBlob.load(REF));
p.slides.keep([0,3]);
const cover=p.slides.items[0], body=p.slides.items[1];
const shot=await p.inspect({kind:'shape,textbox,image,table,chart',maxChars:100000});
const remove=shot.records.filter(r=>r.slideIndex===1 && r.position?.top>95 && r.position?.top<690).map(r=>r.id);
p.delete(remove);
function txt(s,text,x,y,w,h,size=30,color=D,bold=false,font=FONT){
 const a=s.shapes.add({geometry:'textbox',name:text.slice(0,35),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 a.text=text;a.text.style={fontSize:size,typeface:font,color,bold,verticalAlignment:'top',wrap:true};a.text.insets=0;return a;
}
function foot(s,n){
 for(const a of s.shapes.items){
  if(a.name==='矩形 3'){a.text='操作系统课程实验  自适应页面替换';a.text.style={fontSize:10.667,typeface:FONT,color:P};}
  if(a.name==='矩形 4'){a.text=String(n);a.text.style={fontSize:10.667,typeface:FONT,color:P};}
 }
}
function heading(s,title,n){
 const a=s.shapes.items.find(x=>x.name==='矩形 1');a.text=title;a.text.style={fontSize:36,typeface:FONT,color:P,bold:true};a.text.insets=0;
 foot(s,n);
}
function note(s,text,sources='results/summary.csv'){s.speakerNotes.text=text+'\n\n数据与实现来源： https://github.com/CHiSwsz/os-page-replacement\n'+sources+'\n课件要求：OS-页面替换-更新.pptx，第 8 页图例。';}
cover.shapes.items.find(x=>x.name==='Text 100').text='自适应页面替换算法';
const sub=cover.shapes.items.find(x=>x.name==='Text 101');sub.text='容量与历史访问驱动的策略选择';sub.text.style={fontSize:32,typeface:FONT,color:G};
txt(cover,'算法设计、优化与实验',95,480,1000,50,25,T);
foot(cover,1);note(cover,'开场约 20 秒。我们实现六种参照算法，并设计只使用过去访问的 Adaptive。重点解释如何利用访问特征，以及这轮优化修复了什么问题。');
if(process.argv.includes('--cover')){
 p.slides.keep([0]);await (await PresentationFile.exportPptx(p)).save(R+'/cover.pptx');console.log('Cover exported');
}else{
const slides=[cover,body];for(let i=2;i<21;i++)slides.push(body.duplicate());
const order=(await p.inspect({kind:'slide',maxChars:100000})).records;
p.slides.reorder(slides.map(s=>order.find(r=>p.resolve(r.id).id===s.id).id));
function table(s,headers,rows,{x=90,y=160,w=1100,h=360,size=25,widths}={}){
 const values=[headers,...rows].map(row=>row.map(String));
 const t=s.tables.add({rows:values.length,columns:headers.length,left:x,top:y,width:w,height:h,values,columnWidths:widths||Array(headers.length).fill(w/headers.length)});
 t.borders.assign({fill:'#E8E3EF',width:.7,style:'solid'});
 for(let r=0;r<values.length;r++)for(let c=0;c<headers.length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?PALE:'#FFFFFF';cell.text.style={fontSize:size,typeface:FONT,color:r===0?P:D,bold:r===0,alignment:c===0?'left':'center'};
 }
 t.cells.block({row:0,column:0,rowCount:values.length,columnCount:headers.length}).assign({margins:{left:12,right:10,top:12,bottom:10},anchor:'center'});
 return t;
}
function chart(s,categories,series,{x=90,y=150,w=1100,h=420,labels=false,legend=true,title='',format='#,##0',max,size=21}={}){
 // Eight decimals retain much more precision than displayed while keeping
 // native Excel chart workbook values within its 15 significant digits.
 const c=s.charts.add('bar',{position:{left:x,top:y,width:w,height:h},categories,series:series.map(v=>({...v,values:v.values.map(x=>Number(x.toFixed(8))),line:{fill:'none',width:0}})),title:title||undefined,
 titlePlacement:title?'aboveChart':'none',titleTextStyle:{fontSize:25,fill:P,bold:true},barOptions:{direction:'column',grouping:'clustered',gapWidth:90},hasLegend:legend,
 legend:{position:'bottom',overlay:false,textStyle:{fontSize:size,fill:D}},
 xAxis:{textStyle:{fontSize:size,fill:D},majorGridlines:null,line:{fill:'#CEC6D8',width:1}},
 yAxis:{min:0,max,numberFormatCode:format,textStyle:{fontSize:size,fill:G},majorGridlines:{fill:'#E8E3EF',width:1}},
 dataLabels:{showValue:labels,position:'outEnd',numberFormatCode:format,textStyle:{fontSize:size,fill:D}},chartFill:'#FFFFFF',plotAreaFill:'#FFFFFF',chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0}});
 applyPresentationChartFont(c,{fontFamily:FONT});return c;
}
let s=slides[1];heading(s,'任务：固定容量下，尽量减少缺页',2);
txt(s,'Demand paging：访问时才装入页面',90,135,1100,55,34,P,true);
txt(s,'命中：继续使用驻留页。\n缺页：使用空页框，或淘汰一个页后装入当前页。',90,215,1100,110,31);
table(s,['输入','内存容量','评价指标'],[['十六进制虚拟页号序列','5、10、20、50、100','缺页次数，越少越好']],{y:360,h:140,size:26,widths:[460,330,310]});
txt(s,'统一虚拟地址空间，空内存启动，不预取。自设算法只使用已发生的访问。',90,575,1100,70,26,T);
note(s,'约 35 秒。trace 里的数字已经是虚拟页号，无需再除以页大小。每个 frame 存一页，缺页时只能装入当前访问页。这里以一个统一虚拟页号空间建模，忽略 TLB、脏页写回和多进程调度。OPT 单独作为允许读取未来的离线参照。','data/manifest.json; src/main.cpp; src/paging.cpp');
s=slides[2];heading(s,'四条轨迹的规模和访问特点',3);
table(s,['轨迹','访问次数','不同页数','实测特点'],[
 ['qsort','524','192','短轨迹；50 页框后 LRU 为 199'],
 ['lu','41,832','531','较长复用距离多，100 页框仍缺页多'],
 ['mm16','9,075','515','LRU 在 50 / 100 页框均为 2,964'],
 ['mm32','67,235','1,667','50 到 100 页框，LRU 从 51,860 降至 19,604']],{y:145,h:360,size:25,widths:[150,180,180,590]});
txt(s,'共同点：重复访问的最小重用距离为 20。',90,555,1100,50,31,T,true);
txt(s,'重用距离 = 同一页两次访问之间出现的不同页数。',90,617,1100,45,25,G);
note(s,'约 45 秒。程序名提示来源，但设计依据是实际测得的复用，而不是文件名。qsort 很短，冷启动占比较大；lu 的远距离重用多；两种矩阵轨迹表现出明显容量阈值。四条轨迹都没有小于 20 的重用距离，因此 LRU 在 5、10、20 页框时全部缺页。','results/trace_diagnostics.json; data/manifest.json; results/summary.csv');
s=slides[3];heading(s,'小容量下，最近使用不等于很快再用',4);
txt(s,'当重用距离 ≥ F，LRU 在再次访问前已经淘汰该页。',90,135,1100,50,31);
chart(s,datasets,[{name:'LRU 缺页率',values:datasets.map(()=>1),fill:'#A7ADB4'},{name:'Adaptive V3 缺页率',values:datasets.map(d=>get(d,20,'adaptive')/+data.summary.find(r=>r.dataset===d).references),fill:P}],{y:215,h:345,format:'0%',max:1.1,labels:true});
txt(s,'例：20 页框时，四条轨迹的 LRU 缺页率均为 100%。',90,610,1100,45,26,T);
note(s,'约 40 秒。这里取 20 个页框。重复访问发生得比缓存能保留的范围更晚，LRU 会产生循环淘汰。随机替换有机会留下部分页面，历史间隔预测还能尝试辨别哪些页更快重用。这是引入多策略的动机，不能推出所有新轨迹也有这种规律。');
s=slides[4];heading(s,'六种参照算法分别利用什么信息',5);
table(s,['方法','淘汰依据','主要局限'],[
 ['Random','均匀随机选驻留页','不利用访问规律'],['FIFO','最早装入','命中不更新顺序'],['OPT / MIN','下一次访问最远','需要未来轨迹，只作下界'],['LFU','驻留期间频次最低','历史热度可能过时'],['LRU','最近一次访问最早','长循环容易全部缺页'],['Second chance','Clock 指针 + 访问位','只粗略近似最近性']],{y:130,h:470,size:26,widths:[250,420,430]});
txt(s,'LFU 重载后频次归 1，并列按 LRU；Clock 新装入与命中均置访问位为 1。',90,627,1100,42,22,G);
note(s,'约 35 秒。五种基础算法是 Random、FIFO、OPT、LFU、LRU，我们额外补齐课件里的 Second chance。OPT 在相同模型下给出理论最少缺页数。它与在线算法的信息条件不同，作为下界而非可部署竞争者。','include/paging.hpp; src/paging.cpp');
s=slides[5];heading(s,'Adaptive：用过去的表现选择策略',6);
table(s,['候选策略','适合利用的特征'],[['Random','弱局部性、循环淘汰时保留部分页面'],['LRU','近期访问集中，近期页还会被访问'],['历史间隔预测','重复访问存在相对稳定的间隔']],{y:145,h:275,size:28,widths:[360,740]});
txt(s,'三个影子模拟器记录页号和缺页数，真实缓存只执行当前选中的策略。',90,465,1100,90,30);
txt(s,'F ≤ 20 从 Random 起步；F > 20 从 LRU 起步，随后在线调整。',90,590,1100,65,27,T);
note(s,'约 45 秒。影子缓存只是反事实的元数据模拟，用已发生的访问比较三个候选。切换只改变今后的淘汰依据，真实内存中的驻留页不会凭空变化。一个程序以 F 为参数，不依赖轨迹文件名、具体页号或预先知道的最优策略。','src/adaptive.cpp');
s=slides[6];heading(s,'V3 历史间隔预测：更快适应变化',7);
txt(s,'每页保留上次访问位置与平滑间隔 g。Δ 是两次访问的间隔。',90,130,1100,80,29);
txt(s,'g ← 0.5g + 0.5Δ',115,235,1050,75,43,P,false,'Consolas');
txt(s,'未到预计时刻：评分 = g − 已等待时间。\n已经逾期：评分 = 已等待时间。淘汰评分最大者。',90,355,1100,115,30);
txt(s,'相较 V2：新样本权重从 0.25 提高到 0.5，移除间隔波动附加项。',90,510,1100,85,29,T);
txt(s,'例：g = 20，已等待 15，剩余评分为 5；仅出现过一次的页优先淘汰。',90,625,1100,45,24,G);
note(s,'约 50 秒。首次重复时直接令 g 等于实际间隔，后续用 0.5 权重更新。V2 用 g 加间隔波动做参考，V3 只用 g，减少旧长间隔的持续影响。更快更新也可能放大短期扰动，新增循环压力测试出现了退化。未重复或已忘记的页评分为无穷大，并列按 LRU。只估计未来，不读取未来。','src/adaptive.cpp; results/v3_search.csv');
s=slides[7];heading(s,'容量规则与影子策略比较',8);
txt(s,'V3 在较大容量缩短历史，保留 V2 的窗口与影子对齐机制。',90,130,1100,85,30);
table(s,['容量','历史页号上限 H','比较窗口 W','切换门槛'],[['F ≤ 20','max(32,16F)','max(32,4F)','超过 max(1,⌊W/50⌋)'],['F > 20','max(32,8F)','2 × max(32,4F)','超过 max(1,⌊W/20⌋)']],{y:270,h:210,size:25,widths:[185,305,305,305]});
txt(s,'F > 20 时，每 W 次从实际缓存复制页号状态到三个影子缓存。',90,535,1100,65,28,T,true);
txt(s,'每 W/4 次比较一次，只使用已完成的访问；真实物理页框始终为 F 个。',90,620,1100,45,25,G);
note(s,'约 50 秒。大容量下历史从 16F 缩到 8F，减少陈旧统计。小容量保持 16F，因为统一缩短会损害已有收益。F=5、10、20、50、100 对应 H=80、160、320、400、800。影子对齐方向只有实际到影子，不会把影子页装进真实内存。切换后仍可能有状态偏差，窗口也有滞后。所有轨迹共用这套规则。','src/adaptive.cpp; results/v3_search.csv');
s=slides[8];heading(s,'实验设置与总体缺页次数',9);
chart(s,algs.map(a=>names[a]),[{name:'平均缺页次数',values:algs.map(overall),fill:P,points:algs.map((a,idx)=>({idx,fill:cols[a]}))}],{y:145,h:380,legend:false,labels:true,size:20});
txt(s,`Adaptive V3：${fmt(overall('adaptive'),2)}，比 Random 少 ${(100*(1-overall('adaptive')/overall('random'))).toFixed(2)}%，比 LRU 少 ${(100*(1-overall('adaptive')/overall('lru'))).toFixed(2)}%。`,90,565,1120,50,27,T,true);
txt(s,'4 条轨迹 × 5 档容量；Random / Adaptive 用种子 0～29，其余方法确定性运行。',90,630,1100,40,23,G);
note(s,'约 40 秒。共 140 组配置，保存 1,300 次正式运行。先平均同配置的 30 个种子，再对 20 个配置等权平均缺页次数。长轨迹数值更大，所以另报告宏平均缺页率：V3 为 58.23%。OPT 平均 16,309.80，V3 仍比它多约 4.85%。均值小数不表示一次运行有小数次缺页。','results/raw.csv; results/overall.csv; results/metadata.json');
for(const [index,pair] of [[9,['qsort','lu']],[10,['mm16','mm32']]]){
 s=slides[index];heading(s,`${pair.join(' 与 ')}：不同容量下的缺页次数`,index+1);
 pair.forEach((ds,j)=>chart(s,frames.map(String),algs.map(a=>({name:names[a],values:frames.map(f=>get(ds,f,a)),fill:cols[a]})),{x:55+j*620,y:150,w:590,h:430,title:ds,size:17}));
 txt(s,'横轴：页框数   纵轴：缺页次数。随机算法显示 30 次均值，完整整数与波动见原始表。',90,625,1100,40,23,G);
 note(s,index===9?'约 35 秒。qsort 只有 524 次访问，大容量提升空间小，50 和 100 页框都停在 199。lu 在所有容量下均优于所测在线基线，尤其 50 页框本轮进一步改善。':'约 40 秒。mm16 在 100 页框由 V2 的 2,964 降到 V3 的 2,714.17。mm32 在 50 页框，LRU 为 51,860，V3 为 21,179；100 页框仍与 LRU 相同。');
}
s=slides[11];heading(s,'按课件示例归一化：LRU = 1',12);
datasets.forEach((ds,i)=>chart(s,frames.map(String),[{name:'LRU',values:frames.map(()=>1),fill:'#A7ADB4',dataLabels:{showValue:false}},{name:'Adaptive V3',values:frames.map(f=>get(ds,f,'adaptive')/get(ds,f,'lru')),fill:P}],{x:65+(i%2)*610,y:120+Math.floor(i/2)*263,w:575,h:252,title:ds,labels:true,format:'0.00',max:1.2,size:15}));
txt(s,'低于 1 表示缺页更少。此次 20 个配置均不差于 LRU；未知轨迹仍需验证。',90,658,1100,30,21,T);
note(s,'约 35 秒。每个柱子是同一轨迹、同一容量下，Adaptive 缺页数除以 LRU 缺页数。灰柱固定为 1，与课件示例一致。比 LRU 好并不等于比所有算法都好，例如 qsort/100 的 Random 均值更低。','results/summary.csv; OS-页面替换-更新.pptx 第 8 页');
s=slides[12];heading(s,'V3 对比 V2：9 个改善，6 个不变，5 个退化',13);
const selectedChanges=[['lu',50],['lu',100],['mm32',20],['mm32',50],['mm16',100],['lu',5],['qsort',20]];
const changes=selectedChanges.map(([d,f])=>data.version_comparison.find(r=>r.dataset===d&&+r.frames===f));
table(s,['轨迹 / 页框','V2','V3','变化'],changes.map(r=>[`${r.dataset} / ${r.frames}`,fmt(r.v2,2),fmt(r.v3,2),`${+r.difference>0?'+':''}${fmt(r.difference,2)}`]),{y:130,h:435,size:25,widths:[320,260,260,260]});
txt(s,'总体平均再降 1.46%。这里列出主要变化，全部 20 项见实验报告。',90,608,1100,65,27,T);
note(s,'约 50 秒。15 个候选在课程轨迹和种子 0～4 上初筛，按 20 个配置平均缺页数选择，再固定规则用 30 种子复测。因此属于已知数据优化。lu/50 改善 8.09%，lu/100 改善 6.09%，mm16/100 改善 8.43%。lu/5 多 57.17 次，qsort/20 多 4.43 次，其余退化为 qsort/5、qsort/10 与 mm32/10。V1/V2 的 1,200 条旧结果逐字段复现。','results/version_comparison.csv; results/versions_raw.csv; results/v3_search.csv');
s=slides[13];heading(s,'新增压力测试：扰动循环出现退化',14);
txt(s,'纵轴：五档容量平均缺页次数，V2 / V3 均使用 30 个种子。',90,112,1100,30,21,G);
const synNames=['rotating_hotsets','jittered_cycle_97','returning_sets_560','hot8_scan70'];
const sm=(ds,a)=>mean(data.fresh_summary.filter(r=>r.dataset===ds&&r.algorithm===a).map(r=>+r.faults_mean));
chart(s,['轮换热点','扰动循环 97','交替回访','热点 + 长扫描'],[{name:'V2',values:synNames.map(d=>sm(d,'adaptive_v2')),fill:'#A7ADB4'},{name:'V3',values:synNames.map(d=>sm(d,'adaptive')),fill:P}],{y:145,h:400,labels:true,format:'#,##0',size:22});
txt(s,'扰动循环平均多 0.94% 缺页。快速更新也会更容易受短期波动影响。',90,575,1100,70,28,T);
txt(s,'算法固定后首次评测，未据此调参；构造轨迹不代表老师的隐藏测试。',90,650,1100,35,23,G);
note(s,'约 45 秒。先平均五档容量，V2 与 V3 都使用相同的 30 个种子。四类新构造轨迹在评测前定义。轮换热点整体改善约 0.038%，扰动循环退化 0.938%，交替回访不变，热点长扫描退化 0.015%。扰动循环在 10/20/50 页框分别多 70.77、128.43、38 次。课程平均提升不能保证新轨迹也提升。旧的六类构造回归测试也已重跑，完整结果放在报告。','results/fresh_summary.csv; scripts/fresh_stress.py');
s=slides[14];heading(s,'结论与代价',15);
txt(s,'利用访问特征',90,140,500,55,34,P,true);
txt(s,'小容量避免循环淘汰。\n有稳定间隔时尝试预测。\n局部性强时保留 LRU。',90,220,505,180,31);
txt(s,'明确的代价',680,140,500,55,34,T,true);
txt(s,`额外元数据 O(F)，模拟时间 O(NF)。\nmm32 / 100：Adaptive ${fmt(data.timing_summary.find(r=>r.algorithm==='adaptive').median_ms,2)} ms，\nLRU ${fmt(data.timing_summary.find(r=>r.algorithm==='lru').median_ms,2)} ms。`,680,220,520,180,29);
txt(s,'本次 16 个配置优于最强在线基线，3 个持平，1 个落后于 Random。',90,460,1100,90,29,P,true);
txt(s,'新轨迹按同一规则顺序运行，保留 OPT 下界和全部基线，继续报告成功与失败。',90,590,1100,65,28,T);
note(s,'约 40 秒。缺页更少不代表模拟器运行更快。耗时是同环境 10 次端到端进程测量的中位数，包含启动、输入解析和模拟，并非真实 OS 缺页延迟。落后于 Random 的配置是 qsort/100：199 对 196.30。新压力测试也出现 V3 比 V2 差的配置。优势来自已知轨迹规律，没有任意输入上胜过全部在线算法的保证。参数选择使用了课程轨迹，所以课堂新数据是后续真正需要验证的对象。到此正文约 10 分钟。','results/timing_summary.csv; REPORT.md');
for(const [j,ds] of datasets.entries()){
 s=slides[15+j];heading(s,`附录：${ds} 各容量的详细缺页次数`,16+j);
 table(s,['页框','Random','FIFO','OPT','LFU','LRU','Clock','V3'],frames.map(f=>[f,...algs.map(a=>fmt(get(ds,f,a),['random','adaptive'].includes(a)?2:0))]),{x:55,y:170,w:1170,h:355,size:23,widths:[95,155,150,145,150,150,150,175]});
 txt(s,'Random / V3：种子 0～29 的平均值；其余为精确整数。',90,580,1100,45,26,T);
 txt(s,'原始逐次整数、标准差、最小值、最大值以及 seed=0 整数表均已保存。',90,635,1100,40,23,G);
 note(s,'附录，答疑时使用。强调随机算法列为均值，小数只是统计结果。所有数据由 CSV 直接导入，没有人工录入缺页次数。','results/summary.csv; results/raw.csv; results/fault_counts_seed0.csv');
}
s=slides[19];heading(s,'附录：窗口和历史长度的参数敏感性',20);
const variants=[[2,16],[4,16],[8,16],[4,8],[4,32]];
table(s,['窗口因子','历史因子',...datasets,'总体平均'],variants.map(([w,h])=>{
 const r=data.parameters_summary.filter(r=>+r.window_factor===w&&+r.history_factor===h);
 return [w,h,...datasets.map(ds=>fmt(mean(r.filter(x=>x.dataset===ds).map(x=>+x.faults_mean)),2)),fmt(mean(r.map(x=>+x.faults_mean)),2)];
}),{x:65,y:170,w:1150,h:350,size:23,widths:[120,120,160,185,170,185,210]});
txt(s,'默认因子 4 / 16；F > 20 时窗口乘 2，历史因子减半。',90,580,1100,45,26,T);
txt(s,'已知课程轨迹参与选择参数；本表是敏感性分析，不能证明对新轨迹最优。',90,630,1100,50,24,G);
note(s,'附录。每个数据集先平均五档容量，再对四条轨迹等权平均。参数研究共有 3,000 条原始记录，默认配置的 600 条复用正式结果。更长历史并非越好，也可能保留过时信息。','results/parameters_summary.csv; results/parameters_raw.csv');
s=slides[20];heading(s,'附录：复现与提交',21);
txt(s,'公开仓库',90,140,1100,50,32,P,true);
txt(s,'github.com/CHiSwsz/os-page-replacement',90,205,1100,55,30,T);
txt(s,'新轨迹测试',90,310,1100,50,32,P,true);
txt(s,'./build/pager --trace new.txt --algorithm all\n              --frames 5,10,20,50,100 --seed 0',90,380,1100,100,27,D,false,'Consolas');
txt(s,'旧版对照：--algorithm adaptive --adaptive-version 2\n详细结果：REPORT.md、results/fault_counts_table.csv\n验证：Release、ASan / UBSan、前缀不变性、容量约束与数据校验。',90,530,1100,125,26);
note(s,'附录。实际运行将示例命令的两行合并成一行，或在 shell 使用续行。默认 Adaptive 版本为 3，可通过参数复现 V1 和 V2。代码、实验与 PPT 同步提交到公开仓库。模板来源为用户指定的第三讲_反向传播_修订版_v22.pptx，沿用其布局、字体、配色与页脚。','README.md; results/metadata.json; tests/test_paging.cpp; tests/test_cli.py');
await (await PresentationFile.exportPptx(p)).save(R+'/candidate.pptx');
await fs.writeFile(R+'/deck-inspect.json',JSON.stringify(await p.inspect({kind:'slide,textbox,table,chart',maxChars:300000}),null,2));
console.log('Exported',p.slides.items.length,'slides');
}
}catch(e){console.error(e.message,e.stack?.split('\n').slice(1,4).join('\n'));process.exitCode=1}
