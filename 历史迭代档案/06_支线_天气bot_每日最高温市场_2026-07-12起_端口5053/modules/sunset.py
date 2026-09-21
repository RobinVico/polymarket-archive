"""日落时间计算 — 经典 Almanac for Computers (NOAA) 算法, 纯本地零依赖, 误差 ±2 分钟.

用天文公式而不是调外部 API: 离线可用/无限速/永不挂。selftest 会跟
api.sunrise-sunset.org 对一次以防手滑写错公式。
"""
import math
from datetime import datetime, timedelta, timezone

ZENITH = 90.833  # 官方日落定义 (太阳中心低于地平线 50', 含大气折射)


def sunset_utc(lat, lon, local_date, tz_offset_h=8):
    """给定纬度/经度/当地日期, 返回该日的日落时刻 (aware UTC datetime).
    极昼/极夜返回 None (本项目城市不会发生)."""
    N = local_date.timetuple().tm_yday
    lng_hour = lon / 15.0
    t = N + ((18.0 - lng_hour) / 24.0)

    M = (0.9856 * t) - 3.289
    L = M + (1.916 * math.sin(math.radians(M))) + (0.020 * math.sin(math.radians(2 * M))) + 282.634
    L %= 360.0

    RA = math.degrees(math.atan(0.91764 * math.tan(math.radians(L)))) % 360.0
    # RA 要跟 L 落在同一象限
    l_quadrant = math.floor(L / 90.0) * 90.0
    ra_quadrant = math.floor(RA / 90.0) * 90.0
    RA = (RA + (l_quadrant - ra_quadrant)) / 15.0  # 转小时

    sin_dec = 0.39782 * math.sin(math.radians(L))
    cos_dec = math.cos(math.asin(sin_dec))

    cos_h = (math.cos(math.radians(ZENITH)) - (sin_dec * math.sin(math.radians(lat)))) / \
            (cos_dec * math.cos(math.radians(lat)))
    if cos_h > 1 or cos_h < -1:
        return None

    H = math.degrees(math.acos(cos_h)) / 15.0
    T = H + RA - (0.06571 * t) - 6.622
    UT = (T - lng_hour) % 24.0

    base = datetime(local_date.year, local_date.month, local_date.day, tzinfo=timezone.utc)
    dt = base + timedelta(hours=UT)

    # UT mod 24 可能落错 UTC 日期: 校正到"当地日期 == local_date"的那次日落
    tz = timezone(timedelta(hours=tz_offset_h))
    for shift in (0, -1, 1):
        cand = dt + timedelta(days=shift)
        if cand.astimezone(tz).date() == local_date:
            return cand
    return dt
