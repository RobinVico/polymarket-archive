import os
import requests
from dotenv import load_dotenv
from py_clob_client.client import ClobClient

load_dotenv()

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137

PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY")
FUNDER = os.getenv("POLY_FUNDER")
SIGNATURE_TYPE = int(os.getenv("POLY_SIGNATURE_TYPE", "1"))

def main():
    # 1) 地理封锁检查
    print("=== Geoblock Check ===")
    try:
        geo = requests.get("https://polymarket.com/api/geoblock", timeout=10).json()
        print(geo)
    except Exception as e:
        print(f"geoblock check failed: {e}")

    # 2) 派生 API 凭证
    print("\n=== Derive API Creds ===")
    client = ClobClient(
        host=HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        signature_type=SIGNATURE_TYPE,
        funder=FUNDER,
    )
    creds = client.create_or_derive_api_creds()
    print(creds)
    print("\n✅ 把上面的 apiKey / secret / passphrase 填回 .env")

if __name__ == "__main__":
    main()