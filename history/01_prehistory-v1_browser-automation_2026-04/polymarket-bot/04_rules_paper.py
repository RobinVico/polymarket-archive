import os
import json
import time
import asyncio
import requests
import websockets
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

DATA_API = "https://data-api.polymarket.com"
FUNDER = os.getenv("POLY_FUNDER")

# ========== 止盈止损比例 ==========
TP_PCT = 0.10   # 涨 10% 止盈
SL_PCT = 0.08   # 跌  8% 止损
# ==================================

def get_live_positions():
    positions = requests.get(
        f"{DATA_API}/positions",
        params={"user": FUNDER, "limit": 100},
        timeout=20,
    ).json()
    return [p for p in positions if float(p.get("size", 0)) > 0]

def process_event(data, pos_map):
    if not isinstance(data, dict):
        return
    asset = data.get("asset_id")
    if asset not in pos_map:
        return

    info = pos_map[asset]
    bids = data.get("bids", [])
    best_bid = float(bids[0]["price"]) if bids else 0
    if best_bid == 0:
        return

    avg = info["avgPrice"]
    now = datetime.now().strftime("%H:%M:%S")

    if best_bid >= avg * (1 + TP_PCT):
        print(f"🟢 [{now}] TAKE PROFIT  {info['title']} / {info['outcome']}  "
              f"avg={avg:.4f}  bid={best_bid:.4f}")
    elif best_bid <= avg * (1 - SL_PCT):
        print(f"🔴 [{now}] STOP LOSS  {info['title']} / {info['outcome']}  "
              f"avg={avg:.4f}  bid={best_bid:.4f}")

async def main():
    held = get_live_positions()
    if not held:
        print("没有活跃仓位")
        return

    pos_map = {
        p["asset"]: {
            "title": p.get("title"),
            "outcome": p.get("outcome"),
            "avgPrice": float(p.get("avgPrice", 0)),
            "size": float(p.get("size", 0)),
        }
        for p in held
    }

    print("=== 止盈止损线 ===")
    for asset, info in pos_map.items():
        tp = info["avgPrice"] * (1 + TP_PCT)
        sl = info["avgPrice"] * (1 - SL_PCT)
        print(f"  {info['title']} / {info['outcome']}  avg={info['avgPrice']:.4f}  TP≥{tp:.4f}  SL≤{sl:.4f}")

    asset_ids = list(pos_map.keys())
    print(f"\n监控 {len(pos_map)} 个仓位，等待触发...\n")

    uri = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "assets_ids": asset_ids,
            "type": "market",
            "custom_feature_enabled": True,
        }))

        last_ping = time.time()

        while True:
            if time.time() - last_ping > 8:
                await ws.send("PING")
                last_ping = time.time()

            msg = await ws.recv()
            try:
                parsed = json.loads(msg)
            except:
                continue

            if isinstance(parsed, list):
                for item in parsed:
                    process_event(item, pos_map)
            elif isinstance(parsed, dict):
                process_event(parsed, pos_map)

asyncio.run(main())
