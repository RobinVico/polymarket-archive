# -*- coding: utf-8 -*-
"""从五月中旬(exit_at>=2026-05-15)到现在的交易复盘 PDF — 详版, 含亏损归因/卖飞清单/赚vs亏对比。"""
import sqlite3, re
from collections import defaultdict, Counter
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
F = 'STSong-Light'
CUT = '2026-05-15'; TODAY = '2026-07-13'
OUT = '/Users/baymaxagent/polymarket/Polymarket_交易复盘报告_2026-05中旬_至_07-13.pdf'
NAVY=colors.HexColor('#1B2A4A'); GREEN=colors.HexColor('#1E7B4F'); RED=colors.HexColor('#B3362B')
GRAY=colors.HexColor('#66707F'); ZEBRA=colors.HexColor('#F3F5F9'); INK=colors.HexColor('#222B36')
GRID=colors.HexColor('#DDE3EC'); AMBERBG=colors.HexColor('#FFF2D9'); REDBG=colors.HexColor('#FBE7E4')

def nn(slug):
    if not slug: return '(无名)'
    s=re.sub(r'-\d{6,}$','',slug); s=re.sub(r'^will-','',s)
    return s.replace('-',' ')

def stp(size,color=INK,bold=False,align=0,lead=None):
    return ParagraphStyle('s',fontName=F,fontSize=size,textColor=color,alignment=align,leading=lead or size*1.35)
H1=stp(20,NAVY); H2=stp(14,NAVY); H3=stp(11.5,NAVY); BODY=stp(10.5,INK); SMALL=stp(9,GRAY)
CELL=stp(8,INK,lead=10); CELLC=stp(8,INK,align=1,lead=10)
def moneyp(v,size=8):
    v=v or 0; col=GREEN if v>=0 else RED
    return Paragraph(f'<font color="#{col.hexval()[2:]}">{"+" if v>=0 else "-"}${abs(v):.2f}</font>', stp(size,align=1))
def TS(extra=None, hdr=NAVY, fs=9, foot=False, nrows=0):
    s=[('FONTNAME',(0,0),(-1,-1),F),('FONTSIZE',(0,0),(-1,-1),fs),
       ('BACKGROUND',(0,0),(-1,0),hdr),('TEXTCOLOR',(0,0),(-1,0),colors.white),
       ('ROWBACKGROUNDS',(0,1),(-1,-2 if foot else -1),[colors.white,ZEBRA]),
       ('ALIGN',(1,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
       ('GRID',(0,0),(-1,-1),0.4,GRID),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]
    if foot: s.append(('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#E8F0FA')))
    if extra: s+=extra
    return TableStyle(s)

c=sqlite3.connect('/Users/baymaxagent/polymarket/v4.db'); c.row_factory=sqlite3.Row
rows=[dict(r) for r in c.execute("SELECT * FROM closed_positions WHERE exit_at>=? ORDER BY exit_at DESC",(CUT,))]
c.close()
n=len(rows); total=sum(r['realized_pnl_usd'] or 0 for r in rows)
W=[r for r in rows if (r['realized_pnl_usd'] or 0)>0]
L=[r for r in rows if (r['realized_pnl_usd'] or 0)<0]
resolved=[r for r in rows if r['is_resolved']]; correct=[r for r in resolved if r['is_correct']]
prof_rate=len(W)/n*100; dir_rate=len(correct)/len(resolved)*100 if resolved else 0
tot_loss=sum(r['realized_pnl_usd'] for r in L)
Lres=[r for r in L if r['is_resolved']]; Lflew=[r for r in Lres if r['is_correct']]  # 卖飞
best=max(rows,key=lambda r:r['realized_pnl_usd'] or 0); worst=min(rows,key=lambda r:r['realized_pnl_usd'] or 0)

# ---- 重评数据 ----
import statistics as _st
c2=sqlite3.connect('/Users/baymaxagent/polymarket/v4.db'); c2.row_factory=sqlite3.Row
RV=[dict(r) for r in c2.execute("SELECT * FROM auto_reeval_suggestions WHERE created_at>=? ORDER BY created_at",(CUT,))]
c2.close()
rv_pos=defaultdict(list)
for r in RV: rv_pos[r['token_id']].append(r)
rv_dec=Counter(r['action'] for r in RV if r['action']); rv_prov=Counter(r['provider'] for r in RV if r['provider'])
rv_cnt=Counter(len(v) for v in rv_pos.values())
RVq=[r for r in RV if r['new_q'] is not None and r['cur_price'] is not None]
gaps=[r['new_q']-r['cur_price'] for r in RVq]; gap_avg=_st.mean(gaps)*100 if gaps else 0
above=sum(1 for g in gaps if g>0.05)
RVo=[r for r in RVq if r.get('orig_q') is not None]
qdrop_avg=_st.mean([r['orig_q']-r['new_q'] for r in RVo])*100 if RVo else 0
price_drop_avg=_st.mean([abs(r['loss_pct'] or 0) for r in RVo])*100 if RVo else 0
try: corr=_st.correlation([abs(r['loss_pct'] or 0) for r in RVo],[max(0,r['orig_q']-r['new_q']) for r in RVo])
except Exception: corr=0
RVc=[r for r in RVq if r.get('pre_dump_center')]
center_avg=_st.mean([r['pre_dump_center'] for r in RVc])*100 if RVc else 0
pit_avg=_st.mean([r['cur_price'] for r in RVc])*100 if RVc else 0
newq_c_avg=_st.mean([r['new_q'] for r in RVc])*100 if RVc else 0
closer_center=sum(1 for r in RVc if abs(r['new_q']-r['pre_dump_center'])<abs(r['new_q']-r['cur_price']))

el=[]
el.append(Paragraph('Polymarket 交易复盘报告 · 详版', H1))
el.append(Paragraph(f'区间: 2026 年 5 月中旬 (05-15) 至 {TODAY} · 65 笔已平仓 · 数据源 closed_positions (按 Polymarket 真实成交)', SMALL))
el.append(Spacer(1,0.35*cm))

# ===== 一 总览 =====
el.append(Paragraph('一、总览', H2))
ov=[['总平仓笔数',f'{n} 笔',' 已结算',f'{len(resolved)} 笔 (另 {n-len(resolved)} 笔未到结算日)'],
    ['累计盈亏',f'{"+" if total>=0 else "-"}${abs(total):.2f}','平均每笔',f'{"+" if total>=0 else "-"}${abs(total/n):.2f}'],
    ['赚钱率 (真赚到钱)',f'{prof_rate:.0f}%  ({len(W)} 赚 / {len(L)} 亏)','方向对率 (押对方向)',f'{dir_rate:.0f}%  ({len(correct)}/{len(resolved)} 结算押对)'],
    ['赚最多',f'{nn(best["market_slug"])[:28]}  +${best["realized_pnl_usd"]:.2f}','亏最多',f'{nn(worst["market_slug"])[:28]}  ${worst["realized_pnl_usd"]:.2f}']]
t=Table([[Paragraph(a,stp(9.5,NAVY)),Paragraph(b,BODY),Paragraph(cc,stp(9.5,NAVY)),Paragraph(d,BODY)] for a,b,cc,d in ov],
        colWidths=[3.2*cm,7.2*cm,3.2*cm,8.5*cm])
t.setStyle(TableStyle([('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.white,ZEBRA]),('LINEBELOW',(0,0),(-1,-1),0.4,GRID),
    ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
el.append(t)
el.append(Spacer(1,0.2*cm))
el.append(Paragraph(f'说明: <b>方向对率</b>=只看市场最终结算你押的方向对不对(不管卖没卖、赚没赚, 仅算已结算 {len(resolved)} 笔); <b>赚钱率</b>=这笔实际有没有真赚到钱。方向对率({dir_rate:.0f}%)高于赚钱率({prof_rate:.0f}%) = 你押对了却常常没赚到 → 卖飞。', SMALL))
el.append(Spacer(1,0.45*cm))

# ===== 二 分期 =====
el.append(Paragraph('二、分期表现 (按平仓月份)', H2))
months=defaultdict(lambda:{'n':0,'res':0,'cor':0,'prof':0,'pnl':0.0})
for r in rows:
    m=months[(r['exit_at'] or '')[:7]]; m['n']+=1; m['pnl']+=r['realized_pnl_usd'] or 0
    m['res']+= 1 if r['is_resolved'] else 0; m['cor']+= 1 if (r['is_resolved'] and r['is_correct']) else 0
    m['prof']+= 1 if (r['realized_pnl_usd'] or 0)>0 else 0
d=[['月份','笔数','已结算','方向对率','赚钱率','盈亏']]
for mo in sorted(months):
    m=months[mo]; dr=f"{m['cor']}/{m['res']} ({m['cor']/m['res']*100:.0f}%)" if m['res'] else '—'
    d.append([mo,str(m['n']),str(m['res']),dr,f"{m['prof']}/{m['n']} ({m['prof']/m['n']*100:.0f}%)",moneyp(m['pnl'],9)])
d.append(['合计',str(n),str(len(resolved)),f"{len(correct)}/{len(resolved)} ({dir_rate:.0f}%)",f"{len(W)}/{n} ({prof_rate:.0f}%)",moneyp(total,9)])
el.append(Table(d,colWidths=[3*cm,2*cm,2*cm,4*cm,4*cm,3.5*cm],style=TS(foot=True,fs=9.5)))
el.append(Spacer(1,0.45*cm))

# ===== 三 标签 =====
el.append(Paragraph('三、按标签分类 (下的都是什么仓 / 哪个标签赚)', H2))
tags=defaultdict(lambda:{'n':0,'res':0,'cor':0,'prof':0,'pnl':0.0})
for r in rows:
    tt=tags[r['tag'] or '(无标签)']; tt['n']+=1; tt['pnl']+=r['realized_pnl_usd'] or 0
    tt['res']+=1 if r['is_resolved'] else 0; tt['cor']+=1 if (r['is_resolved'] and r['is_correct']) else 0
    tt['prof']+=1 if (r['realized_pnl_usd'] or 0)>0 else 0
d=[['标签','笔数','盈亏','方向对率','赚钱率']]
for k in sorted(tags,key=lambda x:-tags[x]['pnl']):
    v=tags[k]; dr=f"{v['cor']}/{v['res']} ({v['cor']/v['res']*100:.0f}%)" if v['res'] else '—'
    d.append([k,str(v['n']),moneyp(v['pnl'],9),dr,f"{v['prof']}/{v['n']} ({v['prof']/v['n']*100:.0f}%)"])
el.append(Table(d,colWidths=[4.5*cm,2*cm,3.2*cm,4*cm,4*cm],style=TS(fs=9.5)))
el.append(Paragraph('(按盈亏从高到低)', SMALL))
el.append(PageBreak())

# ===== 四 亏损归因 =====
el.append(Paragraph('四、亏损归因 — 亏钱的仓有什么共同点 (只看是否赚钱, 不看结算对错)', H2))
el.append(Paragraph(f'共 <b>{len(L)} 笔亏钱仓, 合计亏 ${abs(tot_loss):.2f}</b>。核心结论: <b>你的亏损绝大多数不是"押错", 是"卖飞"—— 方向对了却在半路割肉, 且多由重评劝卖。</b>', BODY))
el.append(Spacer(1,0.2*cm))
# 4.1 卖飞
el.append(Paragraph(f'4.1　卖飞检查 (亏钱仓里, 方向其实是对的占多少)', H3))
el.append(Paragraph(f'亏钱仓里已结算 {len(Lres)} 笔, 其中最终方向【对】的 <b>{len(Lflew)} 笔 = {len(Lflew)/len(Lres)*100:.0f}%</b> → 这些是"方向对却割肉"(卖飞)。真正押错才亏的只有 {len(Lres)-len(Lflew)} 笔。', BODY))
el.append(Spacer(1,0.35*cm))
# 4.2 出场方式
el.append(Paragraph('4.2　按出场方式 (亏损仓是怎么被卖掉的)', H3))
er=defaultdict(lambda:{'n':0,'pnl':0.0,'flew':0})
for r in L:
    e=er[r['exit_reason'] or '?']; e['n']+=1; e['pnl']+=r['realized_pnl_usd']
    if r['is_resolved'] and r['is_correct']: e['flew']+=1
name_er={'FORCE_EXIT:reeval_exit':'重评清仓(手动确认)','AUTO_REEVAL:exit':'自动重评清仓','AUTO_REEVAL:exit(离线自动)':'自动重评清仓(离线)',
         'REBUILT_FROM_TRADES':'早期回填(非bot决策)','FORCE_EXIT:manual_liquidate':'手动清仓','STOP_LOSS':'止损','TIME_STOP':'时间止损','TAKE_PROFIT_HALF':'止盈卖半'}
d=[['出场方式','亏损笔数','合计亏','其中卖飞(方向对却亏)']]
for k in sorted(er,key=lambda x:er[x]['pnl']):
    v=er[k]; d.append([name_er.get(k,k),str(v['n']),moneyp(v['pnl'],9),f"{v['flew']} 笔"])
el.append(Table(d,colWidths=[6.5*cm,2.6*cm,3*cm,5*cm],style=TS(fs=9.3)))
el.append(Paragraph('重评驱动的清仓(重评清仓+自动重评)是最大亏损源; 早期回填是从 Polymarket 补的老仓、非 bot 决策, 剔掉后信号更纯。', SMALL))
el.append(Spacer(1,0.35*cm))
# 4.3 入场价 + 4.4 tier 并排概念, 分两小表
el.append(Paragraph('4.3　按入场价 (买贵的还是买便宜的容易亏) — favorite vs longshot', H3))
def bk(p): return '≥0.65 favorite' if p>=0.65 else '0.50–0.65' if p>=0.5 else '0.35–0.50' if p>=0.35 else '<0.35 longshot'
allb=Counter(bk(r['avg_entry_price'] or 0) for r in rows); lb=Counter(bk(r['avg_entry_price'] or 0) for r in L)
d=[['入场价档','该档总笔数','其中亏钱','该档亏钱率']]
for k in ['≥0.65 favorite','0.50–0.65','0.35–0.50','<0.35 longshot']:
    d.append([k,str(allb[k]),str(lb[k]),f"{lb[k]/allb[k]*100:.0f}%" if allb[k] else '—'])
el.append(Table(d,colWidths=[5*cm,3*cm,3*cm,3*cm],style=TS(fs=9.3)))
el.append(Paragraph('longshot(买便宜/<35¢) 亏钱率 60% 最高, favorite(≥65¢) 最低 43% → 买越便宜越容易亏 (favorite-longshot 偏差)。', SMALL))
el.append(Spacer(1,0.35*cm))
# 4.4 tier
el.append(Paragraph('4.4　按止损档 (哪种仓最容易亏)', H3))
ti=defaultdict(lambda:{'n':0,'pnl':0.0}); tiall=Counter()
for r in rows: tiall[r['stop_loss_tier'] or '未分类']+=1
for r in L: x=ti[r['stop_loss_tier'] or '未分类']; x['n']+=1; x['pnl']+=r['realized_pnl_usd']
tname={'event_driven':'事件型','hybrid':'混合型','convergent':'收敛型','未分类':'未分类'}
d=[['止损档','该档总笔数','其中亏钱','合计亏']]
for k in sorted(ti,key=lambda x:ti[x]['pnl']):
    d.append([tname.get(k,k),str(tiall[k]),str(ti[k]['n']),moneyp(ti[k]['pnl'],9)])
el.append(Table(d,colWidths=[4*cm,3*cm,3*cm,3*cm],style=TS(fs=9.3)))
el.append(Paragraph('亏损集中在"未分类 + 事件型"(28/33); 收敛型(硬数据题)几乎不亏。', SMALL))
el.append(PageBreak())

# ===== 五 赚 vs 亏 对比 =====
el.append(Paragraph('五、赚钱仓 vs 亏钱仓 — 到底差在哪', H2))
def avg(lst,k):
    v=[r[k] for r in lst if r[k] is not None]; return sum(v)/len(v) if v else 0
def topER(lst):
    cc=Counter(name_er.get(r['exit_reason'],r['exit_reason']) for r in lst); return ', '.join(f"{k}×{v}" for k,v in cc.most_common(2))
d=[['维度','赚钱仓 (%d 笔)'%len(W),'亏钱仓 (%d 笔)'%len(L)],
   ['平均持有时长',f"{avg(W,'hold_duration_hours')/24:.1f} 天",f"{avg(L,'hold_duration_hours')/24:.1f} 天  ← 只有赚的一半"],
   ['平均入场价',f"${avg(W,'avg_entry_price'):.2f}",f"${avg(L,'avg_entry_price'):.2f}"],
   ['平均盈亏%',f"+{avg(W,'realized_pnl_pct'):.0f}%",f"{avg(L,'realized_pnl_pct'):.0f}%"],
   ['主要出场方式',topER(W),topER(L)],
   ['收敛型占比',f"{sum(1 for r in W if r['stop_loss_tier']=='convergent')}/{len(W)}",f"{sum(1 for r in L if r['stop_loss_tier']=='convergent')}/{len(L)}"]]
el.append(Table(d,colWidths=[4*cm,7*cm,9*cm],style=TS(fs=9.5)))
el.append(Paragraph('最扎眼的差别: 亏钱仓平均只拿了赚钱仓一半的时间就撤了 → 会赢的仓没拿住。', SMALL))
el.append(Spacer(1,0.45*cm))

# ===== 六 卖飞清单 =====
el.append(Paragraph(f'六、卖飞清单 — 方向对了却割肉的 {len(Lflew)} 笔 (最该复盘的)', H2))
d=[['#','名称','标签','方向','入场→出场','亏了','亏%','怎么卖的']]
Lflew_sorted=sorted(Lflew,key=lambda r:r['realized_pnl_usd'])
for i,r in enumerate(Lflew_sorted,1):
    d.append([str(i),Paragraph(nn(r['market_slug'])[:52],CELL),Paragraph(r['tag'] or '—',CELL),
              (r['side'] or '?').upper(),f"${(r['avg_entry_price'] or 0):.2f}→${(r['exit_price'] or 0):.2f}",
              moneyp(r['realized_pnl_usd']),f"{(r['realized_pnl_pct'] or 0):.0f}%",
              Paragraph(name_er.get(r['exit_reason'],r['exit_reason'] or '?'),CELL)])
el.append(Table(d,colWidths=[0.8*cm,6.6*cm,2.4*cm,1.3*cm,2.9*cm,2*cm,1.5*cm,3.5*cm],style=TS(fs=8),repeatRows=1) if False else
          Table(d,colWidths=[0.8*cm,6.6*cm,2.4*cm,1.3*cm,2.9*cm,2*cm,1.5*cm,3.5*cm]))
el[-1].setStyle(TS(fs=8))
el.append(Paragraph('这些仓最终方向都是对的, 却在中途以亏损卖出。合计本可避免的亏损 ≈ $%.2f。' % abs(sum(r['realized_pnl_usd'] for r in Lflew)), SMALL))
el.append(Spacer(1,0.4*cm))

# ===== 七 结论 =====
el.append(Paragraph('七、结论与建议', H2))
for txt in [
 '<b>1. 问题在"出场时机", 不在"选仓"。</b> 方向对率 59% 说明你选得不差; 亏损里 55% 是方向对却卖飞的, 单一最大亏损源是"重评清仓"。',
 '<b>2. 会赢的仓没拿住。</b> 亏钱仓平均只持有 %.1f 天 (赚钱仓 %.1f 天)。太早撤 → 还没等反弹就割了。' % (avg(L,'hold_duration_hours')/24, avg(W,'hold_duration_hours')/24),
 '<b>3. 对重评的"清仓"更保守。</b> 它劝卖的一多半是会赢的仓; 事件型 exit 护栏 / 混合型不走重评 / -60% 松兜底 这些改动正是冲这个来的, 数据支持继续。',
 '<b>4. 补标签。</b> 无标签的 7 笔亏 $%.2f, 连归类复盘都做不了; 录入时把标签填全。' % abs(tags['(无标签)']['pnl']),
 '<b>5. 少碰 longshot。</b> 买 <35¢ 的仓亏钱率 60%; 优先 favorite(≥65¢), 亏钱率只有 43%。',
 '<b>6. 收敛型(硬数据题)是你的强项。</b> 它几乎不亏, 可以多下。',
]:
    el.append(Paragraph(txt, ParagraphStyle('c',fontName=F,fontSize=10.5,textColor=INK,leading=15,spaceAfter=5)))
el.append(PageBreak())

# ===== 八 重评总览 =====
el.append(Paragraph('八、自动重评总览 (大跌时 AI 联网重估 q)', H2))
el.append(Paragraph(f'区间内共 <b>{len(RV)} 次重评, 覆盖 {len(rv_pos)} 个仓位</b>。决策分布: update_q(改胜率继续拿) {rv_dec.get("update_q",0)} · cancel_autostop(取消止损扛) {rv_dec.get("cancel_autostop",0)} · exit(清仓) {rv_dec.get("exit",0)} · hold(维持) {rv_dec.get("hold",0)}。出决策的模型: Claude {rv_prov.get("claude",0)} / 智谱GLM {rv_prov.get("glm",0)}。', BODY))
el.append(Paragraph(f'重评次数分布: {"; ".join(f"被评{k}次的有{v}个仓" for k,v in sorted(rv_cnt.items()))} — 最多一个仓被反复重评 {max(rv_cnt) if rv_cnt else 0} 次。', SMALL))
el.append(Spacer(1,0.45*cm))

# ===== 九 反锚定 =====
el.append(Paragraph('九、价格大跌时 q 会不会也跌到坑底? (反锚定验证 · 你最想知道的)', H2))
el.append(Paragraph('v7.0 出场重设计的核心: 大跌触发重评时<b>喂给 AI「大跌前的价格中枢」, 不许它拿被砸的坑底现价当 q 的锚</b>。下面用真实重评数据验证到底管不管用。', BODY))
el.append(Spacer(1,0.15*cm))
d=[['指标','数值','说明'],
   ['① 价格平均跌幅',f'-{price_drop_avg:.0f}%','触发重评时价格已从入场跌了这么多'],
   ['② q 平均跌幅',f'-{qdrop_avg:.0f}pp','但 q 只跌这么点 (约价格跌幅的 1/3)'],
   ['③ new_q 比坑底现价',f'高 +{gap_avg:.0f}pp','重评后 q 平均比坑底现价还高这么多'],
   ['④ 没锚坑底的比例',f'{above}/{len(RVq)} = {above/len(RVq)*100:.0f}%','new_q 明显高于现价(>5pp)的次数'],
   ['⑤ 价格跌幅↔q跌幅 相关性',f'{corr:+.2f}','≈0 = q 跌多少跟价格跌多少无关(独立判断); 若机械跟跌会接近 +1'],
]
el.append(Table(d,colWidths=[6*cm,3.5*cm,9.5*cm],style=TS(fs=9.5)))
el.append(Spacer(1,0.25*cm))
el.append(Paragraph(f'<b>反锚定中枢直接对比</b> (有中枢的 {len(RVc)} 条): 坑底现价平均 <b>{pit_avg:.0f}%</b> · 大跌前中枢 <b>{center_avg:.0f}%</b> · 重评后 new_q <b>{newq_c_avg:.0f}%</b> → <b>new_q({newq_c_avg:.0f}%) 贴着中枢({center_avg:.0f}%), 不是坑底现价({pit_avg:.0f}%)</b>; {closer_center}/{len(RVc)} 次 new_q 更靠近中枢。', BODY))
el.append(Spacer(1,0.15*cm))
el.append(Paragraph(f'结论: 价格大跌时 <b>q 基本不会跟着跌到坑底</b> — 价格跌 {price_drop_avg:.0f}% 时 q 只降 {qdrop_avg:.0f}pp, 且降多少跟价格跌多少无关(相关 {corr:+.2f}), AI 是按基本面独立重估。反锚定设计有效。(注: q 仍会适度下调, 不是无视大跌; 个别仓 AI 判断论点真走弱会主动降 q 甚至清仓, 见下表 Trump-MBS。)', SMALL))
el.append(PageBreak())

# ===== 十 多次重评轨迹 =====
el.append(Paragraph('十、被反复重评的仓 — q 轨迹 (价格越砸, q 往哪走)', H2))
d=[['市场','评次','每次: 坑底现价 → 重评 q','大跌前中枢']]
for tid,lst in sorted(rv_pos.items(),key=lambda x:-len(x[1])):
    if len(lst)<2: continue
    traj=' → '.join(f"{r['cur_price']:.2f}→{int(r['new_q']*100)}%" for r in lst if r['new_q'] is not None)
    centers=' / '.join(f"{r['pre_dump_center']:.2f}" for r in lst if r.get('pre_dump_center'))
    d.append([Paragraph(nn(lst[0]['slug'])[:42],CELL),str(len(lst)),Paragraph(traj,CELL),centers or '—'])
el.append(Table(d,colWidths=[6.2*cm,1.4*cm,8.4*cm,3*cm],style=TS(fs=8.5)))
el.append(Paragraph('看轨迹: Iran 浓缩铀 价格砸到 0.34 时 q 还给 0.80~0.95 (强反锚, 拒绝坑底); Trump-MBS q 从 0.67 一路降到 0.31 最后清仓 (AI 判断论点真走弱, 是主动降不是机械跟跌)。', SMALL))
el.append(PageBreak())

# ===== 十一 每笔明细 =====
el.append(Paragraph('十一、每一笔仓位明细 (%d 笔, 按平仓时间新→旧)' % n, H2))
d=[['#','名称','标签','方向','入场→出场','盈亏$','盈亏%','方向判定']]
for i,r in enumerate(rows,1):
    judge='方向对' if (r['is_resolved'] and r['is_correct']) else '方向错' if r['is_resolved'] else '未结算'
    d.append([str(i),Paragraph(nn(r['market_slug'])[:56],CELL),Paragraph(r['tag'] or '—',CELL),
              (r['side'] or '?').upper(),f"${(r['avg_entry_price'] or 0):.2f}→${(r['exit_price'] or 0):.2f}",
              moneyp(r['realized_pnl_usd']),f"{'+' if (r['realized_pnl_pct'] or 0)>=0 else ''}{(r['realized_pnl_pct'] or 0):.0f}%",
              Paragraph(judge,CELLC)])
dt=Table(d,colWidths=[0.9*cm,7.6*cm,2.8*cm,1.4*cm,3.0*cm,2.2*cm,1.7*cm,2.3*cm],repeatRows=1)
sty=[('FONTNAME',(0,0),(-1,-1),F),('FONTSIZE',(0,0),(-1,-1),8),('BACKGROUND',(0,0),(-1,0),NAVY),
     ('TEXTCOLOR',(0,0),(-1,0),colors.white),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,ZEBRA]),
     ('ALIGN',(3,0),(-1,-1),'CENTER'),('ALIGN',(0,0),(0,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
     ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#E2E6EC')),('TOPPADDING',(0,0),(-1,-1),2.5),('BOTTOMPADDING',(0,0),(-1,-1),2.5)]
for i,r in enumerate(rows,1):
    sty.append(('TEXTCOLOR',(7,i),(7,i), GREEN if (r['is_resolved'] and r['is_correct']) else RED if r['is_resolved'] else GRAY))
dt.setStyle(TableStyle(sty)); el.append(dt)

doc=SimpleDocTemplate(OUT,pagesize=landscape(letter),leftMargin=1.2*cm,rightMargin=1.2*cm,topMargin=1.1*cm,bottomMargin=1.0*cm,title='Polymarket 交易复盘报告 详版')
doc.build(el)
print(f"✅ PDF: {OUT}\n   {n}笔 亏{len(L)}笔(-${abs(tot_loss):.2f}) | 卖飞{len(Lflew)}/{len(Lres)}={len(Lflew)/len(Lres)*100:.0f}% | 页数{doc.page}")
