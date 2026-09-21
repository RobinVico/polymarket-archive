#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AUTO 全自动版 策略 PPT — 分享版 (给熟人看, 企业风格/可打印, 16:9)。

这是 ~/polymarket-auto (全自动账户) 的分享 deck, 从老项目 ~/polymarket 的半自动
分享版 fork 改写而来。核心差别 (相对老半自动版):
  ~ 范式反转: 人工下单 → 全自动买入 (auto_trader); Claude 手动贴网页 → 智谱 GLM 自动选品/重评。
  - 删掉: edge 入场门槛整页 (用户否掉); 在线/离线大段 (永远离线自动执行); 双模型对比。
  + 新增: 规则分流页 / 每日全仓巡检 / 反向推荐触发重评 / Kelly 本金冻结 + 信心乘数 /
          白名单宇宙闸门 / 关键词黑名单→测试仓 / 来历页 (继承老项目两个月打磨的策略)。
  开源框架指向老的【公开】半自动仓 (本 AUTO 仓 private)。
数据快照: 2026-07-24 (主账户 $92.06 / 29 持仓 / 已平仓 62 笔 −$3.03 / 真单自 07-08; 另 bench 二号 + shadow 三号账户同信号三策略实验中)。
跑法: /tmp/pptenv/bin/python3 scripts/gen_strategy_ppt_share.py
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

VERSION = "8.5.5"
DATE = "2026-07-24"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   f"Polymarket_AUTO_项目分享_v{VERSION}.pptx")

PAGE_W, PAGE_H = Inches(13.333), Inches(7.5)
ML = Inches(0.55)
CW = Inches(12.233)

NAVY = '1B2A4A'; NAVY2 = '24395F'; ACCENT = '2E74B5'; GOLD = 'C9A227'
INK = '222B36'; GRAY = '66707F'; FAINT = '8A93A3'
WHITE = 'FFFFFF'; ZEBRA = 'F3F5F9'
GREEN = '1E7B4F'; GREEN_BG = 'E3F3EA'
RED = 'B3362B'; RED_BG = 'FBE7E4'
AMBER = '8F6212'; AMBER_BG = 'FFF2D9'
BLUE_BG = 'E8F0FA'; CHIP_BG = 'F5F7FA'
KICKER_C = '9FB6D9'

_page = {'n': 0}


def R(h):
    return RGBColor.from_string(h)


def _fmt(run, size=13, bold=False, color=INK, italic=False, font='Helvetica Neue'):
    f = run.font
    f.size = Pt(size); f.bold = bold; f.italic = italic
    f.name = font
    f.color.rgb = R(color)
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn('a:ea'))
    if ea is None:
        ea = rPr.makeelement(qn('a:ea'), {})
        latin = rPr.find(qn('a:latin'))
        if latin is not None:
            latin.addnext(ea)
        else:
            rPr.append(ea)
    ea.set('typeface', 'PingFang SC')


def txt(slide, x, y, w, h, paras):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = para.get('align', PP_ALIGN.LEFT)
        p.space_after = Pt(para.get('space_after', 0))
        p.space_before = Pt(para.get('space_before', 0))
        p.line_spacing = para.get('line', 1.12)
        for rr in para['runs']:
            r = p.add_run()
            r.text = rr[0]
            _fmt(r, **(rr[1] if len(rr) > 1 else {}))
    return tb


def rect(slide, x, y, w, h, fill, rounded=False, radius=0.10, line_color=None):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE, x, y, w, h)
    shp.fill.solid(); shp.fill.fore_color.rgb = R(fill)
    if line_color:
        shp.line.color.rgb = R(line_color); shp.line.width = Pt(0.75)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    if rounded:
        try:
            shp.adjustments[0] = radius
        except Exception:
            pass
    return shp


def bullets(slide, x, y, w, items, size=12.3, gap=6, line=1.16, marker='•', marker_color=ACCENT):
    paras = []
    for it in items:
        pre = None; mk = marker; mkc = marker_color; sz = size
        if isinstance(it, str):
            body = it
        elif isinstance(it, tuple):
            pre, body = it
        else:
            pre = it.get('b'); body = it['t']
            mk = it.get('m', marker); mkc = it.get('mc', marker_color); sz = it.get('size', size)
        runs = [(mk + '  ', {'size': sz, 'bold': True, 'color': mkc})]
        if pre:
            runs.append((pre, {'size': sz, 'bold': True, 'color': INK}))
        runs.append((body, {'size': sz, 'color': INK}))
        paras.append({'runs': runs, 'space_after': gap, 'line': line})
    return txt(slide, x, y, w, Inches(0.4), paras)


def table(slide, x, y, w, col_ws, data, fs=11.5, header_fs=None, row_h=0.5, header_h=0.42,
          col_align=None, header_fill=NAVY, first_col_bold=True, cell_over=None):
    rows = len(data); cols = len(data[0])
    gf = slide.shapes.add_table(rows, cols, x, y, w, Inches(header_h + row_h * (rows - 1)))
    t = gf.table
    t.first_row = False; t.horz_banding = False
    for ci, cw_in in enumerate(col_ws):
        t.columns[ci].width = Inches(cw_in)
    t.rows[0].height = Inches(header_h)
    for ri in range(1, rows):
        t.rows[ri].height = Inches(row_h)
    for ri, row in enumerate(data):
        for ci, val in enumerate(row):
            c = t.cell(ri, ci)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.margin_left = Inches(0.1); c.margin_right = Inches(0.07)
            c.margin_top = Inches(0.03); c.margin_bottom = Inches(0.03)
            c.fill.solid()
            c.fill.fore_color.rgb = R(header_fill if ri == 0 else (WHITE if ri % 2 == 1 else ZEBRA))
            tf = c.text_frame; tf.word_wrap = True
            if isinstance(val, dict):
                lines = val['lines']
            else:
                lines = [(s, None) for s in val.split('\n')]
            for li, (text, opts) in enumerate(lines):
                p = tf.paragraphs[0] if li == 0 else tf.add_paragraph()
                p.alignment = (col_align[ci] if col_align else PP_ALIGN.LEFT)
                p.line_spacing = 1.05
                r = p.add_run(); r.text = text
                if opts is not None:
                    _fmt(r, **opts)
                elif ri == 0:
                    _fmt(r, size=header_fs or fs, bold=True, color=WHITE)
                else:
                    o = {'size': fs if li == 0 else fs - 1.5,
                         'bold': first_col_bold and ci == 0 and li == 0,
                         'color': INK if li == 0 else GRAY}
                    if cell_over and (ri, ci) in cell_over:
                        o.update(cell_over[(ri, ci)])
                    _fmt(r, **o)
    return gf


def callout(slide, x, y, w, h, title, body, bar=RED, bg=RED_BG, body_size=11.3, title_size=12.3):
    rect(slide, x, y, w, h, bg, rounded=True, radius=0.08)
    rect(slide, x, y + Inches(0.09), Inches(0.075), h - Inches(0.18), bar)
    paras = [{'runs': [(title, {'size': title_size, 'bold': True, 'color': bar})], 'space_after': 3, 'line': 1.1}]
    for ln in body.split('\n'):
        paras.append({'runs': [(ln, {'size': body_size, 'color': INK})], 'line': 1.18, 'space_after': 1})
    txt(slide, x + Inches(0.24), y + Inches(0.1), w - Inches(0.42), h - Inches(0.2), paras)


def chips(slide, x, y, w, items, h=1.0, gap=0.24, num_size=19, cap_size=10.5,
          fill=CHIP_BG, num_color=NAVY, cap_color=GRAY, line_color='DDE3EC'):
    n = len(items)
    bw = (w - Inches(gap) * (n - 1)) / n
    for i, (num, cap) in enumerate(items):
        bx = x + i * (bw + Inches(gap))
        rect(slide, bx, y, bw, h, fill, rounded=True, radius=0.12, line_color=line_color)
        txt(slide, bx + Inches(0.08), y + Inches(0.16), bw - Inches(0.16), Inches(0.4), [
            {'runs': [(num, {'size': num_size, 'bold': True, 'color': num_color})], 'align': PP_ALIGN.CENTER}])
        txt(slide, bx + Inches(0.08), y + h - Inches(0.42), bw - Inches(0.16), Inches(0.3), [
            {'runs': [(cap, {'size': cap_size, 'color': cap_color})], 'align': PP_ALIGN.CENTER}])


def flow(slide, x, y, w, h, steps, fill=NAVY2, head_size=12, sub_size=9.5,
         head_color=WHITE, sub_color='C9D6EC', arrow_zone=0.34):
    n = len(steps)
    bw = (w - Inches(arrow_zone) * (n - 1)) / n
    for i, (head, sub) in enumerate(steps):
        bx = x + i * (bw + Inches(arrow_zone))
        rect(slide, bx, y, bw, h, fill, rounded=True, radius=0.1)
        paras = [{'runs': [(head, {'size': head_size, 'bold': True, 'color': head_color})],
                  'align': PP_ALIGN.CENTER, 'space_after': 3, 'line': 1.05}]
        for ln in sub.split('\n'):
            paras.append({'runs': [(ln, {'size': sub_size, 'color': sub_color})],
                          'align': PP_ALIGN.CENTER, 'line': 1.1})
        txt(slide, bx + Inches(0.06), y + Inches(0.13), bw - Inches(0.12), h - Inches(0.26), paras)
        if i < n - 1:
            txt(slide, bx + bw, y + h / 2 - Inches(0.16), Inches(arrow_zone), Inches(0.32), [
                {'runs': [('➜', {'size': 13, 'bold': True, 'color': ACCENT})], 'align': PP_ALIGN.CENTER}])


def new_slide(prs, kicker, title):
    _page['n'] += 1
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, PAGE_W, Inches(1.02), NAVY)
    rect(s, ML, Inches(0.30), Inches(0.085), Inches(0.46), GOLD)
    txt(s, ML + Inches(0.22), Inches(0.12), CW, Inches(0.28), [
        {'runs': [(kicker, {'size': 10.5, 'bold': True, 'color': KICKER_C})]}])
    txt(s, ML + Inches(0.22), Inches(0.36), CW, Inches(0.5), [
        {'runs': [(title, {'size': 21.5, 'bold': True, 'color': WHITE})]}])
    rect(s, ML, Inches(7.05), CW, Inches(0.014), 'D5DAE3')
    txt(s, ML, Inches(7.12), Inches(8), Inches(0.25), [
        {'runs': [(f'Polymarket AUTO 全自动交易 · 项目分享 v{VERSION} · {DATE}', {'size': 8.5, 'color': FAINT})]}])
    txt(s, PAGE_W - Inches(3.55), Inches(7.12), Inches(3), Inches(0.25), [
        {'runs': [(f'第 {_page["n"]:02d} 页', {'size': 8.5, 'color': FAINT})],
         'align': PP_ALIGN.RIGHT}])
    return s


# ==================================================================
prs = Presentation()
prs.slide_width = PAGE_W
prs.slide_height = PAGE_H
prs.core_properties.title = f'Polymarket AUTO 全自动交易 · 项目分享 v{VERSION}'
prs.core_properties.author = 'Polymarket AUTO Bot'

# ---------- 1. 封面 ----------
s = prs.slides.add_slide(prs.slide_layouts[6]); _page['n'] += 1
rect(s, 0, 0, PAGE_W, PAGE_H, NAVY)
rect(s, 0, Inches(4.92), PAGE_W, Inches(0.02), GOLD)
txt(s, ML, Inches(0.42), Inches(6), Inches(0.3), [
    {'runs': [('项目分享 · 可打印', {'size': 10.5, 'color': KICKER_C})]}])
rect(s, PAGE_W - Inches(1.9), Inches(0.38), Inches(1.35), Inches(0.44), GOLD, rounded=True, radius=0.5)
txt(s, PAGE_W - Inches(1.9), Inches(0.45), Inches(1.35), Inches(0.3), [
    {'runs': [(f'v{VERSION}', {'size': 13, 'bold': True, 'color': NAVY})], 'align': PP_ALIGN.CENTER}])
txt(s, ML, Inches(1.75), CW, Inches(0.9), [
    {'runs': [('Polymarket 全自动交易机器人', {'size': 38, 'bold': True, 'color': WHITE})]}])
txt(s, ML, Inches(2.68), CW, Inches(0.6), [
    {'runs': [('AI 选仓、程序全自动下单盯盘的真钱实验', {'size': 24, 'bold': True, 'color': GOLD})]}])
txt(s, ML, Inches(3.34), CW, Inches(0.4), [
    {'runs': [('预测市场 · 智谱 GLM 当分析师 · 定时自动扫描/选品/下单/盯盘/出场 · 零人工 · 半自动老项目的私有 fork',
               {'size': 13.5, 'color': KICKER_C})]}])
txt(s, ML, Inches(3.98), CW, Inches(0.35), [
    {'runs': [(f'生成于 2026 年 7 月 20 日 · 封面数据为生成时刻实时快照 · 不构成任何投资建议',
               {'size': 11, 'color': '8DA3C6'})]}])
chips(s, ML, Inches(5.35), CW, [
    ('$92.06', '主账户总值 (实时)'),
    ('29 个', '当前持仓 · 浮盈 +$5.08'),
    ('62 笔', '已平仓 · 合计 −$3.03'),
    ('v8.5 三账户实验', '同信号跑三种策略'),
], h=Inches(1.05), fill=NAVY2, num_color=WHITE, cap_color=KICKER_C, line_color=None)

# ---------- 2. 目录 ----------
s = new_slide(prs, 'CONTENTS', '目录')
toc = [
    ('01', '这是个什么项目', 3),
    ('02', '上线两周的真实运行', 4),
    ('03', '系统总览 — 全自动一条龙', 5),
    ('04', '止盈 — 什么时候锁定利润', 6),
    ('05', '止损 — 什么时候认输离场', 7),
    ('06', '其他出场 & 每 40 秒的决策顺序', 8),
    ('07', '找新仓 — 全自动 GLM 选品', 9),
    ('08', '分流规则 — 真买还是进测试仓', 10),
    ('09', '新仓金额 — 一笔下多少钱', 11),
    ('10', '自动重评 ① 什么时候触发', 12),
    ('11', '自动重评 ② 怎么决定、谁执行', 13),
    ('12', '用哪个 AI — GLM 主 / Claude 兜底', 14),
    ('13', '钱的总规矩 — 风控红线', 15),
    ('14', '测试仓 — 不花钱的模拟盘', 16),
    ('15', '来历 & 版本演进', 17),
    ('16', '踩过的坑 & 诚实的现状', 18),
]
for half, x0 in ((toc[:8], ML), (toc[8:], Inches(7.0))):
    paras = []
    for num, title_, pg in half:
        paras.append({'runs': [
            (num, {'size': 13, 'bold': True, 'color': GOLD, 'font': 'Menlo'}),
            ('   ' + title_, {'size': 13, 'color': INK}),
            (f'   ·  P{pg}', {'size': 10.5, 'color': FAINT}),
        ], 'space_after': 13})
    txt(s, x0, Inches(1.5), Inches(5.9), Inches(5), paras)
callout(s, Inches(7.0), Inches(5.75), Inches(5.78), Inches(1.1),
        '快速读法',
        '只想看结论 → P4 运行 + P18 踩坑与现状; 想懂机制 → P5–P14 流水线与出场重评;\n想自己跑 → P19 (公开的是它的半自动前身, 同一套策略内核)。',
        bar=ACCENT, bg=BLUE_BG)

# ---------- 3. 这是个什么项目 ----------
s = new_slide(prs, '01 · 项目', '这是个什么项目')
callout(s, ML, Inches(1.2), CW, Inches(1.28),
        '先说 Polymarket 是什么',
        '一个用真钱给现实事件下注的预测市场。每道题是一张 $0–1 的合约: 事件发生 = $1, 没发生 = $0;\n现价就是市场眼里的概率 — 一张 $0.72 的"星舰 7 月发射成功?" = 市场认为 72% 会发射。\n题目包罗万象: 地缘政治、选举、公司大事、加密、甚至"某城市今天最高温是不是 33°C"。',
        bar=ACCENT, bg=BLUE_BG, body_size=11.8)
txt(s, ML, Inches(2.72), CW, Inches(0.3), [
    {'runs': [('这个实验: 让 AI 找"市场标错概率的题", 用写死的纪律全自动把认知差变成钱 — 人不插手', {'size': 13.5, 'bold': True, 'color': NAVY})]}])
chips(s, ML, Inches(3.14), CW, [
    ('AI (智谱 GLM)', '分析师 — 联网搜新闻, 估真实胜率 q'),
    ('程序 (bot)', '交易员 — 自动扫描/下单/每40秒盯盘/出场'),
    ('人', '定规则的 — 只设死规矩, 偶尔看盘, 不下单'),
], h=Inches(1.0), num_size=16, cap_size=10.5)
bullets(s, ML, Inches(4.5), CW, [
    ('思路: ', '市场价 = 人群的概率判断, 会系统性出错 (冷门被高估、新闻消化慢)。GLM 读盘面+搜新闻给出自己的胜率 q, 跟市场价差得够大才下手'),
    ('全自动: ', '定时扫描 → GLM 选品 → 写死规则分流 → 自动买入 → 盯盘 → 定时/大跌自动重评 → 自动出场, 全程零人工 (老半自动版是人工下单, 这个把最后那步也交给了程序)'),
    ('规模: ', '小资金实验 (账户 ~$51, 单仓 $1–15) — 目的是验证"全自动闭环"和纪律, 不是发财'),
    ('来历: ', '2026-07-06 从一个跑了两个月、久经踩坑打磨的半自动项目 fork 而来, 继承其成熟出场策略 (P17)'),
], size=12.6, gap=10)

# ---------- 4. 上线首周真实运行 ----------
s = new_slide(prs, '02 · 运行', '上线 16 天的真实运行 (截至 2026-07-24)')
chips(s, ML, Inches(1.2), CW, [
    ('16 天', '全自动真单 (自 07-08)'),
    ('62 笔', '已平仓 · 合计 −$3.03'),
    ('止盈 +$12.9', '被止损/重评 −$15.9 抵掉'),
    ('29 个', '当前持仓 · 浮盈 +$5.08'),
], h=Inches(0.95))
table(s, ML, Inches(2.4), CW, [4.7, 1.5, 2.0, 4.03], [
    ['已平仓 62 笔 · 挑几笔真实记录', '方向', '结果', '出场方式'],
    ['Gemini 发布 (两笔 NO 各卖半)', 'NO', '+$2.22 ×2', '事件型 0.92 卖一半 / 半仓保护'],
    ['Gemini 发布 (反方向 YES 那笔)', 'YES', '−$2.60', '自动重评判 exit → 离线自动卖'],
    ['美国宣布封锁 (US blockade)', 'NO', '−$1.99', '止损: 一路跌到地板 $0.05'],
    ['Elon 身价区间 (收敛型)', 'NO', '−$0.85', '收敛移动止损 → 直接平仓 (v8.3)'],
], fs=11.2, row_h=0.46)
callout(s, ML, Inches(4.78), CW, Inches(1.3),
        '过去两天, 规则真的在自己开火 (bot 日志原文)',
        '07-20 13:35  事件型止盈 — 美国解除 CAATSA 制裁 No 涨到 best_bid ≥ $0.92 → 自动卖一半留一半\n07-20 09:50  收敛移动止损 — Elon 身价 No 从峰值回撤够 → 直接平仓 (v8.3 收敛也不再交重评)\n07-19 07:08  自动重评判 exit — 下个 Claude Opus 发布 判 exit → 离线自动清仓 (无人确认)',
        bar=GREEN, bg=GREEN_BG, body_size=11.3)
bullets(s, ML, Inches(6.28), CW, [
    ('诚实提醒: ', '16 天、62 笔平仓合计 −$3.03 (止盈 +$12.9 被止损/重评 −$15.9 抵掉) = 目前小幅亏损。样本仍小、别当业绩; 这页真正证明的是"全自动闭环在无人干预下自己跑通了", 且已扩成三账户同信号实验 (主策略/bench基准/低价拿到底) 用真钱找最优出场 (P18 讲现状)'),
], size=11.5, gap=6)

# ---------- 5. 系统总览 ----------
s = new_slide(prs, '03 · 系统总览', '一页看懂: 全自动一条龙')
flow(s, ML, Inches(1.28), CW, Inches(1.2), [
    ('① 定时扫描', '09:00 / 21:00\n中范围 · 26 tag'),
    ('② GLM 选品', '多轮自主搜索\n出 JSON 推荐'),
    ('③ 规则分流', '0.40<p<0.85\n→真买 / 否则测试仓'),
    ('④ 自动买入', 'sizing 公式金额\n无需人工下单'),
    ('⑤ 盯盘', '每 ~40 秒\n该卖自动卖'),
    ('⑥ 自动重评', '每日15:00 / 大跌\n/ 反向推荐'),
], head_size=11, sub_size=8.8, arrow_zone=0.24)
bullets(s, ML, Inches(2.82), CW, [
    ('分工: ', 'GLM 出主意 (选品+重评) · bot 全自动扫描/下单/盯盘/出场 · 人只定死规则和偶尔看盘 — 买入卖出都不需要人'),
    ('买入也自动了: ', '这是相对老半自动版最大的变化 — auto_trader 按写死规则自动下单; 老版本这一步是人工去 Polymarket 手动买'),
    ('节奏: ', '扫描每天 2 次 · 盯盘睡 30 秒+干活约 10 秒 ≈ 实际 40 秒过一遍每仓 · 全仓巡检重评每天 1 次 (15:00) · 资产快照 30 分钟一次'),
    ('每个仓位买入时定好三件事, bot 全靠它们盯盘: ', '胜率 q · 止损档 (三选一, 见下) · 主题簇 (防同类扎堆)'),
    ('几块屏: ', '新首页看板 (按天战报+实时持仓) · /auto 选品清单 · /paper 测试仓 · /m 手机只读 · /history 往期复盘'),
], size=12.5, gap=8)
callout(s, ML, Inches(5.62), CW, Inches(1.22),
        '三种止损档 (买入时 GLM 分类, 决定这个仓后面怎么止盈止损)',
        '收敛型 convergent = 真相会自己收敛的题 (数据/汇率/比分) · 混合型 hybrid = 民调+政治混合 (选举/加密)\n事件型 event_driven = 政治/外交/谈判 — 价格天天震荡但震荡≠真相变化, 所以规则对它最宽容',
        bar=NAVY, bg=CHIP_BG, body_size=11.6)

# ---------- 6. 止盈 ----------
s = new_slide(prs, '04 · 出场策略', '止盈 — 什么时候锁定利润')
table(s, ML, Inches(1.26), CW, [3.5, 4.0, 4.73], [
    ['仓位类型', '触发条件 (按"真能卖到的价")', '动作'],
    ['事件型 · 翻倍先到', '卖价 ≥ 2×成本 (且早于 $0.92)', '全部卖出锁翻倍 (低价入场时先到)'],
    ['事件型 · 到 $0.92', '卖价 ≥ $0.92 (还没翻倍)', '卖一半留一半; 后半跌破 $0.78 再全卖'],
    ['收敛型 · 距结算 ≤3 天', '卖价 ≥ $0.88', '全部卖出 (提前落袋, 留出滑点)'],
    ['收敛型 >3 天 / 混合型', '卖价 ≥ $0.90 或 浮盈 ≥ +100%', '全部卖出'],
], fs=12, row_h=0.46)
bullets(s, ML, Inches(3.95), CW, [
    ('为什么看"卖价"? ', '触发用盘口买一价 best_bid (真能成交的价), 不用参考价 — 防"显示 $0.90 实际只能卖 $0.60"的假止盈'),
    ('事件型这套怎么跑? ', '论点没破常一路涨到底。低价捡的、翻倍(≥2×成本)先到 → 全卖落袋; 高价的到 $0.92 → 卖一半留一半博结算, 但留的半仓从 0.92 跌 15%(<$0.78)就把后半也卖了锁利润, 不让它坐过山车吐回去'),
    ('这套是继承老项目的: ', '出场策略从老半自动项目原样同步 (v7.4.5), AUTO 一个字没改 — 久经真金实测'),
], size=12.2, gap=8)
callout(s, ML, Inches(5.62), CW, Inches(1.18),
        '这两条 07-12 凌晨都真触发了 (AUTO 自己的单)',
        '00:23 Trump 骂人 (事件型) best_bid 跳到 $0.99 → 自动卖一半留一半; 37 分钟后价格回落, 01:00 留的\n后半跌到 $0.64 触发"半仓保护"全卖 — 前半 0.99、后半 0.64 都落了袋, 没坐过山车吐回成本。',
        bar=GREEN, bg=GREEN_BG)

# ---------- 7. 止损 ----------
s = new_slide(prs, '05 · 出场策略', '止损 — 什么时候认输离场')
table(s, ML, Inches(1.26), CW, [2.9, 4.6, 4.73], [
    ['仓位类型', '止损方式', '触发线'],
    ['收敛型 convergent', '移动止损: 从"持有期最高价"回撤 → 直接平仓 (v8.3, 不再交重评)', '回撤 ≥20% (距结算 ≤3 天收紧到 12%)\n且连续 6 次心跳 ≈3 分钟确认, 防一抖卖飞'],
    ['混合型 hybrid', '移动止损: 从峰值回撤; 砸穿→直接平仓 (v7.4.5, 不走重评)', '回撤 ≥35% 且连续 6 次心跳确认'],
    ['事件型 event_driven', '-50% 强行止损【直接平仓】+ $0.05 地板 (AUTO 2026-07-18)', '亏 ≥50% → 直接平仓 (不走重评) 或 < $0.05'],
    ['未分类 (少见)', '默认当"混合型"处理 (不再有 -25% 老仓档)', '回撤 ≥35% (同混合型移动止损)'],
], fs=12, row_h=0.52)
callout(s, ML, Inches(4.14), CW, Inches(0.95),
        '砸穿止损线怎么处理 (AUTO v8.3 起: 三档一律直接平仓)',
        '收敛 / 混合 / 事件 砸穿止损线【直接平仓, 不走重评】(收敛=回撤20%、混合=回撤35%、事件=亏50%; 收敛 v8.3 从"先交重评"改成直接卖, 「⏸ 等重评」状态退役)。任何仓跌破 $0.05 地板 / 没档案 / 重评没配置 也直接卖。事件型的盘中重评改由"从最好点回撤 5pp"单独触发 (P10), 跟止损平仓是两条路。',
        bar=RED, bg=RED_BG)
bullets(s, ML, Inches(5.32), CW, [
    ('两种止损口径: ', '收敛型 + 混合型盯"持有期最高价"回撤 (移动止损); 事件型盯"成本价"(实时加权均价, 加仓自动摊平) 亏 50% 强行平仓。成本价永远用实时均价, 不用第一次入场价'),
    ('事件型为什么改成 -50% 硬止损: ', '原来给很松的 -60%+交重评 (政治题先砸后弹); 但回撤数据显示跌破约 -50% 基本"回不来"(不归点), 所以 2026-07-18 (用户最高指令) 改成 -50% 强行直接平仓, 任何东西越不过'),
    ('AUTO 现在的持仓里就有: ', '俄乌战线、美伊外交、莫斯科空管这些事件型; Trump 进世界杯冠军赛是收敛型; bitcoin 到 $1M 是混合型 — 各按各档盯'),
], size=12.2, gap=8)

# ---------- 8. 其他出场 + 优先级 ----------
s = new_slide(prs, '06 · 出场策略', '其他出场 & 每 40 秒的决策顺序')
txt(s, ML, Inches(1.22), Inches(6.2), Inches(0.35), [
    {'runs': [('每一轮 (约 40 秒) 对每个仓从上往下过一遍, 第一个命中的执行:', {'size': 12.4, 'bold': True, 'color': NAVY})]}])
bullets(s, ML, Inches(1.66), Inches(6.15), [
    {'m': '①', 'mc': GOLD, 'b': '没档案', 't': ' → NO_META; AUTO 一律不重评、不动仓, 主页 🔴 红警等人手动补档案 (方向/q 无从谈起, 绝不瞎猜)'},
    {'m': '②', 'mc': GOLD, 'b': '止盈', 't': ' (P6) — 含事件型 翻倍先到全卖 / 0.92 卖一半'},
    {'m': '③', 'mc': GOLD, 'b': '止损 / 移动止损', 't': ' (P7) — 三档砸穿都直接平仓 (收敛回撤20% / 混合35% / 事件亏50%); 收敛 v8.3 起也不再交重评'},
    {'m': '④', 'mc': GOLD, 'b': '时间止损: ', 't': '距结算 ≤2 天且价格离入场价没挪动 (<5 个点) → 自动全卖 — 快结算了还在原地 = 论点没兑现, 别让钱陪跑到最后一刻'},
    {'m': '⑤', 'mc': GOLD, 'b': '状态灯', 't': ' (只亮灯提示, 不自动卖) — 见右表'},
], size=12.3, gap=10)
table(s, Inches(7.05), Inches(1.32), Inches(5.73), [1.85, 2.05, 1.83], [
    ['状态灯', '胜率 q − 现价', '意思'],
    ['HOLD', '> +2 点', '继续拿'],
    ['MARGINAL', '−3 ～ +2 点', '边缘, 别加仓'],
    ['AT_TARGET', '< −3 点 (没重评过)', '已到目标价, 考虑落袋'],
    ['SOFT_NEGATIVE', '< −3 点 (重评过)', 'AI 也偏空, 留意'],
], fs=10.8, row_h=0.5, header_h=0.38)
bullets(s, Inches(7.05), Inches(4.1), Inches(5.73), [
    '状态灯每轮刷新, 显示在首页看板每仓的「决策状态」一行 (只提示, 从不自动卖)',
    ('心跳到底多快: ', '睡 30 秒 + 每轮拉盘口/算止盈止损约 10 秒 ≈ 实际 40 秒过一遍每个仓; 价格跳空(如 0.9- 直接跳 0.99)时会在下一轮才抓到'),
], size=11.3, gap=7)
callout(s, ML, Inches(5.62), CW, Inches(1.18),
        '记住一条: 触发价口径不对称 (防假信号的关键设计)',
        '止盈看 best_bid (真能卖到的价) — 防流动性差的假胜利; 止损/时间止损看参考价 cur_price — 防盘口瞬时蒸发误触发。\nbest_bid 拉不到时自动退回参考价, 不会卡死。',
        bar=NAVY, bg=CHIP_BG)

# ---------- 9. 找新仓 — 全自动 GLM 选品 ----------
s = new_slide(prs, '07 · 选品', '找新仓 — 全自动 GLM 选品')
callout(s, ML, Inches(1.16), CW, Inches(1.0),
        '一句话: 定时扫市场 → GLM 像人一样多轮搜新闻 → 自动出 JSON 推荐 → 自动分流入库',
        '老半自动版这一步是"手动把提示词贴到 Claude.ai 网页"; AUTO 全交给智谱 GLM 自动跑, 没有人工复制粘贴。',
        bar=ACCENT, bg=BLUE_BG, body_size=11.5)
flow(s, ML, Inches(2.36), CW, Inches(0.95), [
    ('① 定时全扫', '09:00/21:00\n中范围·26 tag'),
    ('② 筛候选', '单 tag ≥5 个\n才送 (省 API)'),
    ('③ GLM 搜', '多轮自主搜索\nweb_search 循环'),
    ('④ 回 JSON', '方向/胜率q\n信心/理由'),
    ('⑤ 校验入库', '归一/白名单\n剔坏数据'),
    ('⑥ 自动分流', '真买 / 测试仓\n(见 P10)'),
], head_size=11, sub_size=8.8, arrow_zone=0.26)
bullets(s, ML, Inches(3.62), CW, [
    ('主题从哪来: ', '26 个固定白名单 tag (modules/tags.py; 动态热门榜功能已整个删除, 改 tag 只能人工改文件) — 宇宙铁律: 只交易"白名单 tag 扫描报告里真实出现"的市场, 双重闸门'),
    ('多轮自主搜索 (v8 升级): ', 'GLM 不再一次性喂搜索结果, 而是自己决定搜什么、看完再搜 (web_search 做成函数工具循环, 上限 8 轮) — 像人一样搜→想→再搜; 任何失败自动回退老的一次性注入搜索'),
    ('省钱闸: ', '一个 tag 扫出的候选 < 5 个 → 该 tag 本轮不送 GLM (跳过记日志不静默); 扫得严的日子可能大半 tag 都不触发 = 少花 API'),
    ('两把 GLM key 分工: ', '选品搜索用一把、重评用另一把, 绝不混用 — 智谱后台按 key 分开记账, 花销看得清'),
    ('只列清单不越权: ', '选品阶段只把推荐写进 /auto 候选库 (带"真买/测试仓"预演标签), 真正下不下单由分流规则 (P10) 在执行时刻按新鲜盘口再定'),
], size=12.2, gap=8)

# ---------- 10. 分流规则 (替换老 edge 门槛页) ----------
s = new_slide(prs, '08 · 选品', '分流规则 — 真买还是进测试仓')
callout(s, ML, Inches(1.16), CW, Inches(1.16),
        '故意做得极简 — 一条价格线定生死, 没有别的闸门',
        'GLM 推荐的市场, 按【执行时刻的新鲜盘口现价 p】一刀切:\n    0.40 < p < 0.85  →  真买 (按 sizing 公式金额, P11)\n    其余 (含恰好等于 0.40 / 0.85)  →  自动进测试仓, 零成本模拟验证',
        bar=NAVY, bg=CHIP_BG, body_size=12.2, title_size=12.8)
bullets(s, ML, Inches(2.62), CW, [
    ('为什么这么简单: ', '用户明确否掉了 edge 门槛、双跑取一致、信心分流、流动性检查那套复杂闸门 — 规则简单写死, 让机器少犯"自作聪明"的错; 想加任何保护先问过人'),
    ('黑名单命中 → 强制测试仓: ', '关键词黑名单命中标题/slug 的市场 (如 bitcoin-GTA) 永远不真买, 无视价格强制只进测试仓 (背景: 曾有黑名单市场挂着白名单 tag 被放行买成真仓)'),
    ('临下单漂移容差: ', '真买前最后复核一次盘口 — 相对算金额那次的价漂移 > 3pp, 或漂出 40–85 区间 → 这单不追, 点名跳过 (流程是秒级的, 正常动不了多少)'),
    ('防对锁: ', '已持有同一市场对面方向 → 拒买 (不左右手互搏); 同时立刻触发那个持仓一次重评 (P10 反向推荐)'),
    ('跳过都点名: ', '已持有 / 公式算出 <$1 / 无盘口 / 已关闭 / gamma 查不到 … 每种跳过都记状态, 不许静默'),
], size=12.3, gap=9)
callout(s, ML, Inches(5.95), CW, Inches(0.95),
        '和老半自动版的区别',
        '老版靠"edge (胜率−现价) 要大过一个按扫描档/价位算的门槛"才允许推荐 — 一整页规则。AUTO 把它整个拆了,\n换成这条 40–85 价格线。够不够便宜交给 sizing 公式去缩金额 (edge≤0 时公式自然给 $0), 不再单设入场闸。',
        bar=AMBER, bg=AMBER_BG)

# ---------- 11. 新仓金额 ----------
s = new_slide(prs, '09 · 仓位管理', '新仓金额 — 一笔下多少钱')
bullets(s, ML, Inches(1.2), CW, [
    {'m': '①', 'mc': GOLD, 'b': '凯利公式打 2.5 折: ', 't': '金额 = 参考本金 × [edge ÷ (1−p)] × 25%; edge = GLM 胜率 q − 现价 p, edge ≤ 0 → 自然给 $0'},
    {'m': '②', 'mc': GOLD, 'b': '本金冻结 $50 (v8 新): ', 't': '凯利里的"参考本金"锁死在 $50 — 以后往账户加钱 → 多开几个仓, 而不是把单仓放大 (加现金不加单注)'},
    {'m': '③', 'mc': GOLD, 'b': '信心乘数 (v8 新): ', 't': 'GLM 给的信心 high ×1.25 / medium ×1.0 / low ×0.75, 只缩放凯利那步的下注本金 (老版本信心只记录、不进公式 — 这里反过来了)'},
    {'m': '④', 'mc': GOLD, 'b': '再打两个折扣: ', 't': '结算太远 (>21 天) 按平方根比例减、最低 4 折; 冷门低价盘 (p<$0.15) 最多打对折'},
    {'m': '⑤', 'mc': GOLD, 'b': '主题簇帽子 + 硬边界: ', 't': '同主题簇 ≤ 真实本金 20% · 最终金额压回 $1 – $15 (原"月回撤预算闸"v8.0.6 已删 — 18 仓时被打满拒了所有新单)'},
], size=12.6, gap=12)
callout(s, ML, Inches(4.15), CW, Inches(1.12),
        '算一笔现成的 (数字照真实公式)',
        '参考本金 $50 (冻结) · GLM 胜率 60% · 现价 $0.50 · 信心 high · 24 天后结算 →\nedge 10 点 → 凯利 $50 × 0.2 × 25% = $2.5 → ×1.25 信心 ≈ $3.1 → 天数打 94 折 ≈ $2.9 → 各帽子没碰到 → 下 ~$2.9',
        bar=ACCENT, bg=BLUE_BG)
bullets(s, ML, Inches(5.5), CW, [
    ('为什么冻结本金: ', '不想因为账户涨了就放大每一注 (单次判断错的伤害跟着涨); 加的现金拿去多开仓、分散, 更稳'),
    ('为什么帽子这么多: ', '凯利假设概率估得准 — GLM 估不准的部分全靠这些帽子兜着; 单仓最多 $15, 单次判断错也伤不了本'),
    ('每次算的建议都落库 (sizing_log): ', '和实际下的金额对比, 攒数据回头调参'),
], size=12.1, gap=8)

# ---------- 12. 自动重评 ① 触发 ----------
s = new_slide(prs, '10 · 自动重评', '自动重评 ① — 什么时候触发')
callout(s, ML, Inches(1.18), CW, Inches(0.82),
        '一句话: 不盲卖也不护短 — 定期 + 出事时, 让 GLM 联网重查一遍再决定',
        'AUTO 有三条触发路 (都经 inflight 锁互斥防重复烧钱; 反向推荐那路另有 6 小时同类去重):',
        bar=ACCENT, bg=BLUE_BG)
table(s, ML, Inches(2.18), CW, [3.1, 4.0, 5.13], [
    ['触发路', '什么时候', '备注'],
    ['① 每日全仓巡检 (v8 新)', '每天 15:00, 4 路并发工作队列', '所有【有档案】持仓逐个重评 (含盈利/止损OFF仓)'],
    ['② 事件型盘中大跌 (v8.3 改)', '从"持有期最好点"回撤 ≥5pp', '任何盈亏水平触发1次; 单次暴跌只算1次; 无时间冷却 (收敛/混合改直接平仓, 不走这路)'],
    ['③ 反向推荐触发 (v8 新)', '选品推荐了已持仓的反方向', '拒买之余, 立刻重评该仓 + 注入反向理由'],
], fs=11.6, row_h=0.56)
bullets(s, ML, Inches(4.75), CW, [
    ('无档案仓一律不重评 (硬规矩): ', '方向/q/tier 无从谈起, 挡在重评入口, 主页 🔴 红警等人补档案 — 绝不默认成 YES 反着评'),
    ('反向推荐为什么要联动: ', '选品刚看空一个我持有的方向 = 有新信息, "既不盲从也不护短", 把反向理由原文喂给重评模型, 让它重新判一次'),
    ('4 路并发怎么来的: ', '串行一个一个评太慢 (GLM 深搜单仓能 30–60 分钟), 学选品改成工作队列, 一个评完下一个顶上; 配套放宽了"判死线"防误杀'),
    ('哪里看: ', '首页看板每仓的重评卡 — 显示触发原因 (如"反向推荐触发: …")、决策、信源'),
], size=12.1, gap=8)

# ---------- 13. 自动重评 ② 决策与执行 ----------
s = new_slide(prs, '11 · 自动重评', '自动重评 ② — 怎么决定、谁执行')
txt(s, ML, Inches(1.14), CW, Inches(0.3), [
    {'runs': [('GLM 联网搜完新闻后必须三选一 (v8.3 删掉了原第四项 cancel_autostop):', {'size': 12.5, 'bold': True, 'color': NAVY})]}])
flow(s, ML, Inches(1.5), CW, Inches(0.76), [
    ('hold', '继续拿'), ('update_q', '改胜率, 继续拿'), ('exit', '立刻卖掉 (护栏已删, 说卖就卖)'),
], fill=NAVY2, head_size=12.5, sub_size=10, arrow_zone=0.4)
callout(s, ML, Inches(2.5), Inches(6.0), Inches(1.55),
        '永远离线自动执行 (AUTO 的默认)',
        'AUTO_FORCE_OFFLINE=1: 重评决策直接自动执行, exit 会真的卖 —\n没有人工确认这一步 (老半自动版分"在线只建议 / 离线才执行",\nAUTO 把它简化成永远自动)。打开页面看盘也不暂停自动化。',
        bar=AMBER, bg=AMBER_BG, body_size=11)
callout(s, Inches(6.78), Inches(2.5), Inches(6.0), Inches(1.55),
        '方向纠错两道闸 (防 GLM 把数字填反)',
        '① 新胜率疑似镜像翻转 (持 NO 却填了 YES 的数) → 反问 GLM 本人\n要"持有方向的 q", 确认不了 = 本轮放弃不动仓。\n② 数字被更正过且原决定是 exit → 再追问一次最终动作, 按最终答案走。',
        bar=GREEN, bg=GREEN_BG, body_size=11)
bullets(s, ML, Inches(4.28), CW, [
    ('反锚定 (治"坑底卖飞"): ', '提示词里喂给 GLM「大跌前中枢价」(排除最近几小时), 不许拿砸盘后的坑底现价当"合理价"锚 — 老项目曾在坑底被卖飞 ~$16, 病根就是这个'),
    ('事件型 exit 不再拦 (v8.1.0): ', '原来那道"论点被重大新闻推翻 或 新胜率比现价低≥8点才放行卖"的护栏删了 — GLM 一判 exit 立刻执行; 只保留方向纠错闸 (防 GLM 把胜率数字填反卖错边)'),
    ('安全底线: ', 'GLM 给的决策不合法 → 直接丢弃, 绝不进执行; 模型失败 → 不动仓位'),
], size=12.1, gap=8)

# ---------- 14. 用哪个 AI ----------
s = new_slide(prs, '12 · 自动重评', '用哪个 AI — GLM 主 / Claude 兜底')
table(s, ML, Inches(1.3), CW, [2.5, 3.2, 6.53], [
    ['角色', '模型', '说明'],
    ['主用 (说了算)', '智谱 GLM-5.2', '选品 + 重评全走它; search_pro 专业搜索 + thinking 拉满 + 多轮自主搜索; 解析带正则兜底'],
    ['兜底 (备用)', 'Claude', '仅"GLM 那次失败"才顶上, 平时零 Claude 花费 (AUTO_REEVAL_PRIMARY=glm, 不双跑)'],
], fs=12, row_h=0.56)
bullets(s, ML, Inches(3.25), CW, [
    ('为什么反过来 (老版是 Claude 主): ', '这个全自动账户全程用智谱 GLM 跑 (两把 key 分工); Claude 只做"GLM 挂了那一次"的兜底, 不主动花钱 — 平时账单只有 GLM'),
    ('不双跑: ', '用户明确否掉"两家并行跑取交集"— 省钱、也省得两套结论打架; 主用 GLM 给合法决策就执行'),
    ('紧急暂停: ', '编排配错 (比如兜底 key 没配) 启动时会大声告警; 决策不合法一律丢弃, 不会退回盲卖'),
    ('提示词同源: ', '自动重评用的就是当初手动那份提示词内核, 改一处两边同时生效, 只是各自附加决策指令'),
], size=12.3, gap=10)
callout(s, ML, Inches(5.7), CW, Inches(1.08),
        '钱花在哪',
        '选品 (每个够门槛的 tag 一次 GLM) 和自动重评 (每日巡检/大跌/反向推荐) 会调 GLM 付费 API — 这是 AUTO 的主要开销。\n测试仓全程零 API (只读行情)。两把 key 分开记账, 选品花多少、重评花多少一目了然。',
        bar=GOLD, bg=AMBER_BG)

# ---------- 15. 钱的总规矩 ----------
s = new_slide(prs, '13 · 资金风控', '钱的总规矩 — 风控红线一页')
chips(s, ML, Inches(1.24), CW, [
    ('$1 – 15', '单仓上下限'),
    ('≤ 20%', '单主题簇上限'),
    ('$0.05', '绝对地板价'),
    ('sig = 3', '存款钱包新架构'),
], h=Inches(0.95))
bullets(s, ML, Inches(2.5), CW, [
    ('买入全自动 (与老版相反): ', 'auto_trader 按写死的 40–85 分流规则自动下单; 老半自动版反复强调"bot 没有自动买入", AUTO 恰恰把这步交给了程序'),
    ('无日限额、无仓位数上限: ', '用户拍板不设限 (判断逻辑保留, 以后要限改一行 env); 单仓金额天然由 sizing 公式 + $15 硬顶管住'),
    ('宇宙铁律: ', '只交易"白名单 tag 的扫描报告里真实出现"的市场 (双重闸门: tag 在白名单 + slug 在该 tag 报告里); 关键词黑名单命中 → 强制只进测试仓'),
    ('自动卖出的口: ', '止盈到线 / 移动止损确认 / 时间止损 / 跌破 $0.05 地板 / 自动重评判 exit — 每笔卖出都落账进已平仓表'),
    ('账户与隔离: ', 'Polymarket 新架构存款钱包 (必须 sig=3 签名), 端口 5052, 独立 .env / 数据库 / git, 与老账户零关联; 密钥只在本机 (永不进 git)'),
    ('数据保底: ', '每 30 分钟资产快照; 已平仓账目与 Polymarket 官方逐笔成交对齐; SQLite WAL, 时区一律 UTC'),
], size=12.5, gap=13)

# ---------- 16. 测试仓 ----------
s = new_slide(prs, '14 · 测试仓', '测试仓 /paper — 不花钱的模拟盘')
bullets(s, ML, Inches(1.28), CW, [
    ('干嘛用: ', 'GLM 推荐里价格漂到 40–85 之外的、或命中黑名单的, 一律先丢这, 一分钱不花, 跑和真仓完全同一套盯盘算法, 验证 GLM 到底准不准'),
    ('自动进 (v8): ', '分流规则判定"测试仓"的候选自动录入 (金额用真仓同款公式算, 兜底 $5); 黑名单命中的会标"paper:黑名单强制"'),
    ('它做什么: ', '每轮同真仓一起盯 → 算法一"卖"(命中卖出条件)就移到「往期测试仓」→ 继续盯到结算给最终对错。像真仓一样有生命周期'),
    ('零操作省钱: ', '测试仓进去后不重评、不提醒、无任何后续 API 操作 (省钱); 只保留免费盯价 + 模拟卖点记录 (走公开行情)'),
    ('往期 + 统计: ', '每条: 预测准不准 + 模拟盈亏 + 📈最高点 (本可赚多少); 顶部: 模拟总盈亏 / 赚钱率 / 结算对率 — 一眼看这套 GLM 准不准'),
    ('AUTO 现在: ', '已经攒了 21 条在跑 (共 24 条, 多是价格漂出区间、或黑名单被拦下来的推荐)'),
], size=12.6, gap=12)
callout(s, ML, Inches(5.5), CW, Inches(1.12),
        '🔒 铁律 (代码层隔离, 不是口头约定)',
        '测试仓永不碰钱: 不下单、不卖、不调付费 API, 只允许只读拉行情。\n真仓的自动重评天生够不到它 (独立表 + 独立代码路径)。',
        bar=RED, bg=RED_BG)

# ---------- 17. 来历 & 版本演进 ----------
s = new_slide(prs, '15 · 项目历程', '来历 & 版本演进')
callout(s, ML, Inches(1.18), CW, Inches(1.28),
        '来历: 站在两个月踩坑的肩膀上',
        '本项目 2026-07-06 从一个跑了两个月、从 v4 迭代到 v7.4 的半自动老项目 fork 而来。那两个月把每一笔真金亏损\n都变成了规则 —— 三档移动止损、反锚定重评、凯利 sizing、best_bid 防假止盈, 全是坑教出来的。AUTO 直接\n继承这套久经实测的策略内核, 只把"人工分析 + 人工下单"那两步换成"GLM 自动选品 + 程序自动下单"。',
        bar=ACCENT, bg=BLUE_BG, body_size=11.6)
table(s, ML, Inches(2.72), CW, [1.9, 5.6, 4.73], [
    ['时间', 'AUTO 自己干了什么', '被什么逼出来的'],
    ['07-06', '从半自动老项目 fork 出独立副本 (独立账户/库/端口 5052)', '要一个专门跑全自动、跟老号彻底隔离的新账户'],
    ['07-08', '全自动 5 步全上线 (扫→选→分流→真买→巡检) + 真钱闭环跑通', '把"人工下单"最后一步也交给程序; 踩了 sig=3 一下午'],
    ['07-09~10', 'GLM 多轮自主搜索 + 4 路并发全仓巡检 + 反向推荐触发重评', '一次性搜索不够深; 串行评仓太慢; 选品看空已持仓要联动'],
    ['07-11~12', 'Kelly 本金冻结 + 信心乘数 + 黑名单→测试仓 → 收成 v8.0.0 独立版本线', '加现金别放大单注; 黑名单市场绝不真买'],
    ['07-18~20', '止损收紧 (v8.1→8.3): 事件 -50% 硬止损·删 exit 护栏·收敛也直接平仓·事件盘中 5pp 触发重评·删 cancel_autostop; q 校准移 Python; 选品硬超时熔断', '事件型深亏仓扛着不卖 = 最大亏损源 (Gemini −$2.6); GLM 调用挂死冻结整轮'],
], fs=10.3, row_h=0.6, header_h=0.36)
bullets(s, ML, Inches(6.35), CW, [
    ('两条版本线分家: ', 'AUTO 从 v8.0.0 起走自己的号 (现 v8.3.2), 跟老项目 7.x 彻底分开 — 老项目再加东西不自动进这边'),
], size=11.6, gap=6)

# ---------- 18. 踩过的坑 & 诚实的现状 ----------
s = new_slide(prs, '16 · 复盘', '踩过的坑 & 诚实的现状')
bullets(s, ML, Inches(1.2), CW, [
    {'m': '①', 'mc': RED, 'b': '[AUTO] 体育误买事故: ', 't': '一次 E2E 测试手动往系统注入了"法国进世界杯"市场, 被当真仓买了进去 → 立即清仓 + 加"白名单宇宙闸门"(只交易扫描报告里真实出现的市场, 永不为测试注入宇宙外市场)'},
    {'m': '②', 'mc': RED, 'b': '[AUTO] sig=3 折腾一下午: ', 't': '新架构存款钱包账户, 签名类型用 1/2/0 一律余额 $0 + 下单报错 → 最终定位到必须 sig=3 (POLY_1271); 老账户是老架构 sig=1, 经验不能照搬'},
    {'m': '③', 'mc': RED, 'b': '[AUTO] bitcoin-GTA 黑名单漏网: ', 't': '一个黑名单市场挂着白名单 tag 被放行买成真仓 → 关键词黑名单改成永远生效, 命中即强制进测试仓'},
    {'m': '④', 'mc': RED, 'b': '[继承] 假止盈差点锁假胜利: ', 't': '参考价显示 $0.905, 盘口真实只能卖 $0.60 → 止盈一律看真实卖价 best_bid'},
    {'m': '⑤', 'mc': RED, 'b': '[继承] DNS 污染无声瘫痪: ', 't': '系统 DNS 把 polymarket 域名解析到假 IP, 全 bot 安静挂掉 → 进程内自带加密 DNS 兜底 (这段守卫永不删)'},
], size=12.3, gap=11)
callout(s, ML, Inches(4.9), CW, Inches(1.55),
        '诚实的现状 (给熟人看就说实话)',
        '① 全自动真单跑了 16 天 (自 07-08), 62 笔平仓合计 −$3.03 (止盈 +$12.9 被止损/重评 −$15.9 抵掉) — 样本仍小、别当业绩, 证明的是"闭环无人干预跑通了"。\n② 最大的教训: 事件型深亏仓扛着不卖 (Gemini 0.68 烂到 0.16 才卖 −$2.6) → 07-18 收紧止损 (事件 -50% 硬止损、删 exit 护栏、收敛也直接平仓) 就是为治这个。\n③ 现已扩成【三账户同信号实验】: 主策略 (全套止盈止损重评) / bench 二号 (裸预测: $2/仓 -30%即卖 无重评) / shadow 三号 (低价≤0.40 拿到结算: $2/仓 -60%止损 不止盈) — 用真钱对照找最优出场。\n④ 出场阈值还在拿真单攒数据校准、不是精调结果; 最值钱的产出可能不是这点钱, 是这套方法和一路踩坑的记录。',
        bar=AMBER, bg=AMBER_BG, body_size=11.4)

# ---------- 19. 结尾 (开源指向老公开半自动仓) ----------
s = prs.slides.add_slide(prs.slide_layouts[6]); _page['n'] += 1
rect(s, 0, 0, PAGE_W, PAGE_H, NAVY)
rect(s, 0, Inches(4.6), PAGE_W, Inches(0.02), GOLD)
txt(s, ML, Inches(1.4), CW, Inches(0.6), [
    {'runs': [('想自己跑? 公开的半自动前身在这', {'size': 32, 'bold': True, 'color': WHITE})]}])
txt(s, ML, Inches(2.35), CW, Inches(0.5), [
    {'runs': [('github.com/RobinVico/polymarket-llm-trading-bot', {'size': 20, 'bold': True, 'color': GOLD, 'font': 'Menlo'})]}])
txt(s, ML, Inches(3.1), CW, Inches(0.9), [
    {'runs': [('这份 deck 讲的"全自动版"是私有 fork; 公开可跑的是它的半自动前身 — 同一套策略内核 (出场/重评/sizing)。\n含中英双语技术报告 (完整踩坑史) · README 一步步教装 · MIT 协议\n密钥/数据库/真实账目都不在仓库里 — 填自己的钱包和密码就能跑起来',
               {'size': 12.5, 'color': KICKER_C})], 'line': 1.5}])
chips(s, ML, Inches(5.0), CW, [
    ('别用输不起的钱', '预测市场有法律与资金风险'),
    ('先跑测试仓', '零成本验证 AI 靠不靠谱'),
    ('AI 是分析师, 不是神', '纪律和风控才是主角'),
], h=Inches(1.05), fill=NAVY2, num_size=15, num_color=WHITE, cap_color=KICKER_C, line_color=None)
txt(s, ML, Inches(6.6), CW, Inches(0.4), [
    {'runs': [(f'谢谢观看 · {DATE} · AUTO v{VERSION}', {'size': 12, 'color': '8DA3C6'})]}])

prs.save(OUT)
print(f'OK -> {OUT}')
print('slides:', len(prs.slides._sldIdLst))
