import os
import requests
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OpenOrderParams

load_dotenv()

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
DATA_API = "https://data-api.polymarket.com"

PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY")
FUNDER = os.getenv("POLY_FUNDER")
SIGNATURE_TYPE = int(os.getenv("POLY_SIGNATURE_TYPE", "1"))

def main():
    client = ClobClient(
        host=HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        signature_type=SIGNATURE_TYPE,
        funder=FUNDER,
    )
    client.set_api_creds(client.create_or_derive_api_creds())

    # 当前挂单
    print("=== OPEN ORDERS ===")
    open_orders = client.get_orders(OpenOrderParams())
    print(f"共 {len(open_orders)} 个挂单")
    for o in open_orders[:10]:
        print({
            "id": o.get("id"),
            "market": o.get("market"),
            "side": o.get("side"),
            "price": o.get("price"),
            "status": o.get("status"),
        })

    # 当前持仓
    print("\n=== POSITIONS ===")
    positions = requests.get(
        f"{DATA_API}/positions",
        params={"user": FUNDER, "limit": 100},
        timeout=20,
    ).json()

    live = [p for p in positions if float(p.get("size", 0)) > 0]
    print(f"共 {len(live)} 个活跃仓位")
    for p in live[:20]:
        print({
            "title": p.get("title"),
            "outcome": p.get("outcome"),
            "size": p.get("size"),
            "avgPrice": p.get("avgPrice"),
            "curPrice": p.get("curPrice"),
            "percentPnl": p.get("percentPnl"),
            "asset": p.get("asset"),
            "conditionId": p.get("conditionId"),
        })

if __name__ == "__main__":
    main()