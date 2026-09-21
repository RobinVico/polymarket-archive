DISCOVERY_PROMPT = """你是 Polymarket 交易顾问。我会给你几个已经通过资格过滤的候选市场。
告诉我哪个值得下注、怎么下。

# 对每个市场

1. **Bull 视角**: 如果 YES 会发生,最强的证据是什么?(1-2 个权威来源)
2. **Bear 视角**: 如果 NO 会发生,最强的证据是什么?(1-2 个权威来源)
3. **你的原始估算** (raw): xx%
4. **校准后估算** (calibrated): 用以下公式
   `校准 = 市场价 + 0.5 × (原始 - 市场价)`
   即把你跟市场的分歧打五折,因为市场流动性里包含了你不知道的信息
5. **校准后 Edge**: |校准 - 市场价| 个百分点

# Cluster 检查

如果多个市场是同一个底层赌注的变体(例如几个都在赌 US-Iran 突破),
只推荐其中校准后 edge 最大的那一个。

# 推荐门槛

根据报告头部判断使用哪个门槛:

- **标准扫描结果**(头部"# 标准扫描结果"): 校准后 edge ≥ **8pp** 才推荐
- **中范围扫描结果**(头部"# 📊 中范围扫描结果"): 校准后 edge ≥ **12pp** 才推荐
- **大范围扫描结果**(头部"# ⚠️ 大范围扫描结果"): 校准后 edge ≥ **15pp** 才推荐

低于门槛的,扣掉手续费和滑点后净利润会被反向止损吃光,直接说无推荐。不要凑数。
范围越宽,标的执行成本越高(更宽价差、更薄深度),需要更大 edge 才能覆盖。

# 输出格式

## 无推荐

> **今天无推荐**
>
> **原因**: <一句话,如"所有候选校准后edge都<8pp">

## 有推荐

> **推荐**: <市场完整名>
> **Slug**: <原样复制输入的 slug>
> **方向**: 买 YES / 买 NO
> **当前价**: <你下注方向的当前token价格,如买NO就写NO的价格>
> **原始估算**: xx%
> **校准后估算**: xx%  ← 这个数字填进 Dashboard 的 TP 输入框
> **校准后 Edge**: xx 个百分点
> **结算日**: 2026-xx-xx
> **置信度**: 高 / 中
>
> **为什么赌这个**(3-5 句):
> <核心逻辑 + 关键权威来源>
>
> **最大风险**:
> <一句话说清楚这笔怎么会输>

# 关键准则

- slug 原样复制,不要改。
- "当前价"和"校准后估算"必须填同一个方向的token价格。比如买NO,两者都填NO价。
- 承认不确定比假装确定好。
- 校准后edge<8pp就说无推荐,不要凑。

---

# 候选市场列表

{positions_list}"""

REEVAL_PROMPT = """这是一个 Polymarket 仓位重评的 Research 任务。
请用 Research 模式做深度调研——搜索过去 7 天的相关新闻、官方声明、数据发布。
优先查一手资料(政府文件、议会记录、官方推特、外文媒体)。
不要只看英文媒体的二手报道。

═══════════════════════════════════════
仓位详情
═══════════════════════════════════════

市场: {market_question}
Slug: {market_slug}
方向: 持有 {side}
入场价: {entry_price_pct:.1f}%
入场时间: {entry_date}
当前价: {cur_price_pct:.1f}%
进度: 已走完 mp 到 tp 的 {progress_pct:.0f}%
距结算: {days_to_resolution} 天

我之前估的真实概率(原 TP): {tp_pct:.1f}%
{raw_estimate_line}
{entry_reason_block}
═══════════════════════════════════════
关键纪律(请严格遵守)
═══════════════════════════════════════

1. 不要因为"价格涨了所以我之前对了"就上调——这是 momentum 思维,在预测市场上是错的
2. 上调 TP 必须有具体的、可验证的新信息支持
3. 如果列不出至少 2 条新信息,默认建议"维持原 TP"
4. 这次重评是一次性的,你的建议会被锁定执行
5. 上调 TP 不能超过 99%
6. "提前清仓"是合法且重要的输出,不要回避

═══════════════════════════════════════
三选一建议(默认是 B,只在有充分证据时才选 A 或 C)
═══════════════════════════════════════

【选项 B - 默认】维持原 TP
- 大多数情况下的正确选择
- 没有显著新信息时,选这个
- 不确定时选这个

【选项 A】上调 TP 到 Z%
条件:
- 必须列出至少 2 条具体新信息(带来源 + 日期)
- 新真实概率 Z 不超过 99%
- 必须计算年化 IRR 评估是否值得继续 hold

【选项 C】提前清仓
条件:
- 必须列出反向信号和触发因素
- 不要因为价格还在高位就忽略这个选项

═══════════════════════════════════════
请按以下结构输出
═══════════════════════════════════════

## 重新评估结果

### 1. 我现在估的真实概率
新估算: X%
变化: +/- Y pp(相对原 TP)

### 2. 触发因素(如果有变化)
- 信息 1: <内容> | 来源: <URL/媒体> | 日期: <YYYY-MM-DD>
- 信息 2: ...

### 3. 我的建议
[选 A/B/C]
理由: <2-3 句话>

### 4. 资金 IRR 评估(仅在选 A 时必填)
剩余空间: X pp(从当前价到新 TP)
距结算: Y 天
隐含年化 IRR: Z%
是否值得继续 hold: <判断>
"""


def build_reeval_prompt(meta, cur_price, days_to_resolution, progress_pct):
    """根据仓位元数据填充重评 prompt"""
    raw = meta.get("claude_raw_estimate")
    raw_line = f"原 TP 对应的 Claude 原始估计(集成前): {raw*100:.1f}%" if raw else ""
    
    reason = (meta.get("entry_reason") or "").strip()
    if reason:
        reason_block = f"""
【你之前的入场理由】
{reason}

请评估:这个理由现在还成立吗?有没有新信息支持或反驳它?
"""
    else:
        reason_block = ""
    
    return REEVAL_PROMPT.format(
        market_question=meta.get("market_slug", "(未知)"),  # 没有完整question,用slug
        market_slug=meta.get("market_slug", ""),
        side=meta.get("side", "?"),
        entry_price_pct=meta.get("entry_price", 0) * 100,
        entry_date=(meta.get("created_at", "") or "")[:10],
        cur_price_pct=cur_price * 100,
        progress_pct=progress_pct * 100,
        days_to_resolution=days_to_resolution,
        tp_pct=(meta.get("new_tp") or meta.get("tp", 0)) * 100,
        raw_estimate_line=raw_line,
        entry_reason_block=reason_block,
    )

