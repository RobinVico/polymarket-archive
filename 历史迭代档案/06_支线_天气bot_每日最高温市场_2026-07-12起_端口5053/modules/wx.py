"""气温数据源 — 两个适配器, 都跟各自市场的结算源同数据:

1) METAR (aviationweather.gov): 中国大陆机场站. Wunderground 机场页就是 METAR 观测,
   整数 °C, 逐小时/半小时一报. hours=30 一次拉回全天 → bot 中途重启也能自愈补全当日历史.
2) HKO 1 分钟数据 (data.weather.gov.hk): 香港天文台总部站, 0.1°C 精度, 1 分钟一更.
   只给"最新一条" → 必须持续轮询自己攒当日历史 (存 obs 表), 半路启动会缺前半天 (守卫会拦).
"""
import csv
import io
import logging
from datetime import datetime, timedelta, timezone

import requests

from modules import db
from modules.config import TZ_OFFSET_H

log = logging.getLogger("wx")

TZ = timezone(timedelta(hours=TZ_OFFSET_H))
AWC_URL = "https://aviationweather.gov/api/data/metar"
HKO_1MIN_URL = "https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/latest_1min_temperature.csv"
_UA = {"User-Agent": "tianqi-bot/0.1 (personal weather-market monitor)"}


def poll_metar(station_to_city):
    """station_to_city: {'ZSPD': 'shanghai', ...}. 一次请求拉全部站. 返回写入条数."""
    if not station_to_city:
        return 0
    ids = ",".join(sorted(station_to_city))
    r = requests.get(AWC_URL, params={"ids": ids, "format": "json", "hours": 30},
                     timeout=25, headers=_UA)
    r.raise_for_status()
    n = 0
    for o in r.json():
        icao = o.get("icaoId")
        t = o.get("temp")
        ts = o.get("obsTime")
        if icao in station_to_city and t is not None and ts:
            db.save_obs(station_to_city[icao], int(ts), float(t))
            n += 1
    return n


def poll_hko(city_key="hongkong", station_name="HK Observatory"):
    """香港天文台总部 1 分钟气温 (0.1°C). CSV 行: 202607121640,HK Observatory,34.2 (时间是当地时间)."""
    r = requests.get(HKO_1MIN_URL, timeout=20, headers=_UA)
    r.raise_for_status()
    text = r.content.decode("utf-8-sig", "replace")
    n = 0
    for row in csv.reader(io.StringIO(text)):
        if len(row) >= 3 and row[1].strip() == station_name:
            try:
                lt = datetime.strptime(row[0].strip(), "%Y%m%d%H%M").replace(tzinfo=TZ)
                temp = float(row[2])
            except ValueError:
                continue
            db.save_obs(city_key, int(lt.timestamp()), temp)
            n += 1
    return n


def local_day_bounds(local_date):
    start = datetime(local_date.year, local_date.month, local_date.day, tzinfo=TZ)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def day_stats(city_key, local_date):
    """当地日期 local_date 的观测统计 (max/cur/first_ts...), 无数据返回 None."""
    s, e = local_day_bounds(local_date)
    return db.day_obs_stats(city_key, s, e)
