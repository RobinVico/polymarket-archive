"""天气 bot 配置 — 城市/护栏/金额. 所有参数可用环境变量覆盖 (不改代码调参).

策略 (2026-07-12 用户定, 激进档):
  日落即下单; 现温比当日最高低 >=1.0°C; 买价 0.90~0.995; 档位边界不设限;
  $5/市场, 日上限 $30; 只跑中国+香港区域城市.
"""
import os

from dotenv import load_dotenv

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))

ROOT = _ROOT


def _f(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _i(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# 本项目所有城市都在 UTC+8; 以后加美欧城市时改成 per-city tz
TZ_OFFSET_H = 8

# source: 'metar' = aviationweather.gov 机场报文 (结算源 Wunderground 机场站 = 同一份数据, 整数°C)
#         'hko'   = 香港天文台总部 1 分钟数据 (结算源 = HKO Daily Extract, 0.1°C 精度)
# lat/lon 用于算日落 (站点坐标)
CITIES = {
    "shanghai": dict(name="上海", slug_city="shanghai", source="metar", station="ZSPD",
                     lat=31.146, lon=121.800, enabled=True),
    "beijing":  dict(name="北京", slug_city="beijing", source="metar", station="ZBAA",
                     lat=40.082, lon=116.603, enabled=True),
    "shenzhen": dict(name="深圳", slug_city="shenzhen", source="metar", station="ZGSZ",
                     lat=22.639, lon=113.803, enabled=True),
    "chengdu":  dict(name="成都", slug_city="chengdu", source="metar", station="ZUUU",
                     lat=30.576, lon=103.950, enabled=True),
    "wuhan":    dict(name="武汉", slug_city="wuhan", source="metar", station="ZHHH",
                     lat=30.783, lon=114.205, enabled=True),
    "hongkong": dict(name="香港", slug_city="hong-kong", source="hko", station="HK Observatory",
                     lat=22.302, lon=114.174, enabled=True),
    # 台北市场存在 (RCSS 松山), 但用户圈定"中国+香港+澳门", 台北未点头 → 默认关, 要开改 True 重启
    "taipei":   dict(name="台北", slug_city="taipei", source="metar", station="RCSS",
                     lat=25.069, lon=121.552, enabled=False),
}

# ===== 金额 (用户 2026-07-12 定: $5/市场) =====
ORDER_USD = _f("WEATHER_ORDER_USD", 5.0)
DAILY_CAP_USD = _f("WEATHER_DAILY_CAP_USD", 30.0)

# ===== 护栏 (激进档) =====
PRICE_MIN = _f("WEATHER_PRICE_MIN", 0.90)          # 卖一价低于这个 = 市场不认同我们的档, 不买
PRICE_MAX = _f("WEATHER_PRICE_MAX", 0.995)         # 高于这个利润太薄, 不买
TEMP_MARGIN_C = _f("WEATHER_TEMP_MARGIN_C", 1.0)   # 现温必须比当日最高低这么多才下单
ENTRY_DELAY_MIN = _i("WEATHER_ENTRY_DELAY_MIN", 0)  # 日落后再等几分钟 (激进=0)
BOUNDARY_MARGIN_C = _f("WEATHER_BOUNDARY_MARGIN_C", 0.0)  # 最高温离档位边界太近不下单 (0=关, 用户选激进)

# ===== 数据质量守卫 =====
MAX_OBS_AGE_MIN = _i("WEATHER_MAX_OBS_AGE_MIN", 100)   # 最新观测超过这个分钟数没更新 = 数据断了, 不下单
COVERAGE_BY_H = _i("WEATHER_COVERAGE_BY_H", 11)        # 当日首条观测必须在当地几点前 (防漏午间峰值)

# ===== 市场窗口 =====
# 名义 endDate = 当地 20:00; 若日落在 endDate 之后 (如成都夏至前后), 提前到 endDate 前这几分钟决策
PRE_CUTOFF_MIN = _i("WEATHER_PRE_CUTOFF_MIN", 10)
DEADLINE_LOCAL_H = _i("WEATHER_DEADLINE_LOCAL_H", 23)  # 当地这个点后放弃当日重试 (23 = 23:30 见 main)

# ===== 轮询节奏 =====
POLL_METAR_MIN = _i("WEATHER_POLL_METAR_MIN", 10)
POLL_HK_MIN = _i("WEATHER_POLL_HK_MIN", 3)
HEARTBEAT_SEC = _i("WEATHER_HEARTBEAT_SEC", 30)
RESOLUTION_SWEEP_MIN = _i("WEATHER_RESOLUTION_SWEEP_MIN", 30)

# ===== 香港取整规则 (实证, 别乱改) =====
# HKO 官方日最高精确到 0.1°C, 市场档位是整数。2026-07 已结算 11 天实证:
#   7/1 官方 33.5° → 赢家 33 档; 7/4 官方 32.6° → 32 档; 7/6 官方 31.6° → 31 档
# 三个小数>=0.5 的样本全部 floor (去掉小数), 即 "31°C 档" = [31.0, 31.9]。
# scripts/selftest.py 每次跑都会用全月数据复验这条规则。
HK_ROUND = os.getenv("WEATHER_HK_ROUND", "floor")   # 'floor' | 'nearest'

# ===== 手续费 (2026-07-12 官方核实: help.polymarket.com "Trading Fees") =====
# 天气类只收 taker 5% (500bps), maker 免费; 公式 fee = 股数 × 费率 × p × (1-p),
# USDC 计、成交时收; 结算/赢钱/提现零费。买在 0.9~0.995 时手续费 ≈ 毛利的 ~5%。
# 注: CLOB 市场对象 taker_base_fee=1000 只是签名授权上限, 实收按 5% 档;
# 下单库 py_clob_client_v2 1.0.2 会自动按市场费率签单 (__resolve_fee_rate_bps)。
FEE_RATE_BPS = _f("WEATHER_FEE_RATE_BPS", 500.0)

# ===== 模式 =====
PAPER = os.getenv("PAPER", "0") == "1"   # 1 = 配了钱包也不真下单
PORT = _i("WEATHER_PORT", 5053)

MAX_BUY_ATTEMPTS = _i("WEATHER_MAX_BUY_ATTEMPTS", 5)
