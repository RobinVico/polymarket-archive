"""下单决策护栏 — 纯函数, 无副作用, selftest 直接喂假数据测.

护栏顺序 (任一不过就不下单):
  停止开关 → 日上限 → 有气温数据 → 当日覆盖完整 → 数据新鲜 → 现温距最高够远
  → 档位存在 → 市场共识档一致 → 接单中 → 卖一价在 [PRICE_MIN, PRICE_MAX]
返回 (ok, retryable, reason): retryable=True 的失败会在当晚继续重试
(比如现温还不够低 / 价格暂时超区间), False 的直接放弃当日.
"""
import math

from modules import config


def bucket_int_for(source, day_max):
    """把当日最高温折成市场档位整数.
    metar: 观测本来就是整数 °C (round 只是防浮点毛刺).
    hko:   官方 0.1°C 精度, 实证规则 = floor ("31°C 档" 含 31.0~31.9, 见 config)."""
    if source == "hko":
        if config.HK_ROUND == "floor":
            return int(math.floor(day_max + 1e-9))
        return int(math.floor(day_max + 0.5))
    return int(round(day_max))


def check_guards(*, now_ts, stats, coverage_deadline_ts, source, bucket, top,
                 accepting, ask, spent_today, halt):
    """全部护栏. bucket/top 是 markets.fetch_event 解析出的档 dict (或 None)."""
    if halt:
        return False, True, "紧急停止开关已开"
    if spent_today + config.ORDER_USD > config.DAILY_CAP_USD + 1e-9:
        return False, False, f"日上限 ${config.DAILY_CAP_USD:g} 已用满"
    if stats is None:
        return False, True, "无当日气温数据"
    if stats["first_ts"] > coverage_deadline_ts:
        return False, False, f"数据覆盖不全 (当日首条观测太晚, 可能漏掉午间峰值)"
    age_min = (now_ts - stats["cur_ts"]) / 60.0
    if age_min > config.MAX_OBS_AGE_MIN:
        return False, True, f"气温数据过旧 ({age_min:.0f} 分钟没更新)"
    margin = stats["max"] - stats["cur"]
    if margin < config.TEMP_MARGIN_C - 1e-9:
        return False, True, (f"现温 {stats['cur']:.1f}° 距当日最高 {stats['max']:.1f}° "
                             f"只低 {margin:.1f}° (要求 ≥{config.TEMP_MARGIN_C:g}°)")
    if config.BOUNDARY_MARGIN_C > 0 and source == "hko":
        frac = stats["max"] - math.floor(stats["max"])
        if min(frac, 1.0 - frac) < config.BOUNDARY_MARGIN_C:
            return False, False, f"最高温 {stats['max']:.1f}° 离档位边界太近"
    if bucket is None:
        return False, True, "市场里找不到对应档位"
    if top is None or top.get("label") != bucket.get("label"):
        top_label = top.get("label") if top else "?"
        return False, True, (f"市场共识档 {top_label} ≠ 我们算的 {bucket.get('label')} "
                             f"(数据口径可能有出入, 拒绝下单)")
    if not accepting:
        return False, False, "市场已停止接单"
    if ask is None:
        return False, True, "拿不到盘口卖一价"
    if ask < config.PRICE_MIN:
        return False, True, f"卖一价 {ask:.3f} < 下限 {config.PRICE_MIN:g} (市场信心不足)"
    if ask > config.PRICE_MAX:
        return False, True, f"卖一价 {ask:.3f} > 上限 {config.PRICE_MAX:g} (利润太薄)"
    return True, False, "OK"


def fee_usd(price, shares):
    """Polymarket taker 手续费 (USDC, 成交时收): 股数 × 费率 × p × (1-p).
    天气类费率 5% (config.FEE_RATE_BPS), 买在 0.97 时 ≈ 毛利的 ~5%."""
    return config.FEE_RATE_BPS / 1e4 * price * (1.0 - price) * shares
