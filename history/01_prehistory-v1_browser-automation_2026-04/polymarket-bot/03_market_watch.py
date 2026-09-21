import os
import json
import time
import asyncio
import requests
import websockets
from dotenv import load_dotenv

load_dotenv()

DATA_API = "https://data-api.polymarket.com"
FUNDER = os.getenv("POLY_FUNDER")

def get_live_positions():
    positions = requests.get(
        f"{DATA_API}/positions",
        params={"user": FUNDER, "limit": 100},
        timeout=20,
    ).json()
    return [p for p in positions if float(p.get("size", 0)) > 0]

async def main():
    held = get_live_positions()
    if not held:
        print("没有活跃仓位，退出")
        return

    asset_ids = [p["asset"] for p in held]
    pos_map = {
        p["asset"]: {
            "title": p.get("title"),
            "outcome": p.get("outcome"),
            "avgPrice": float(p.get("avgPrice", 0)),
            "size": float(p.get("size", 0)),
        }
        for p in held
    }

    print(f"监控 {len(pos_map)} 个仓位...")

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
            data = json.loads(msg)

            if data.get("event_type") == "best_bid_ask":
                asset = data.get("asset_id")
                if asset in pos_map:
                    info = pos_map[asset]
                    bid = data.get("best_bid")
                    ask = data.get("best_ask")
                    print(f"[{info['title']} / {info['outcome']}] "
                          f"avg={info['avgPrice']:.4f}  bid={bid}  ask={ask}")

asyncio.run(main())