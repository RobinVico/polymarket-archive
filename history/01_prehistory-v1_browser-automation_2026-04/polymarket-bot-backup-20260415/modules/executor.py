import os
import requests
import json
import logging
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OpenOrderParams, OrderArgs
from py_clob_client.order_builder.constants import BUY, SELL
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("executor")
load_dotenv()

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY")
FUNDER = os.getenv("POLY_FUNDER")
SIGNATURE_TYPE = int(os.getenv("POLY_SIGNATURE_TYPE", "1"))

def _get_session():
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500,502,503,504])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    return s


class Executor:
    def __init__(self):
        self.client = None
        self._init_client()

    def _init_client(self):
        try:
            self.client = ClobClient(host=HOST, chain_id=CHAIN_ID, key=PRIVATE_KEY,
                                     signature_type=SIGNATURE_TYPE, funder=FUNDER)
            self.client.set_api_creds(self.client.create_or_derive_api_creds())
            log.info("CLOB client OK")
        except Exception as e:
            log.error(f"CLOB init failed: {e}")

    def get_positions(self):
        try:
            resp = _get_session().get(f"{DATA_API}/positions", params={"user": FUNDER, "limit": 100}, timeout=30).json()
            positions = []
            for p in resp:
                size = float(p.get("size", 0))
                if size <= 0: continue
                positions.append({
                    "market_slug": p.get("title", "unknown"),
                    "question": p.get("title", ""),
                    "side": p.get("outcome", ""),
                    "size": size,
                    "avg_price": float(p.get("avgPrice", 0)),
                    "current_price": float(p.get("curPrice", 0)),
                    "pnl_pct": float(p.get("percentPnl", 0)),
                    "asset": p.get("asset", ""),
                    "condition_id": p.get("conditionId", ""),
                })
            log.info(f"{len(positions)} positions")
            return positions
        except Exception as e:
            log.exception(f"get_positions failed: {e}")
            return []

    def get_balance(self):
        try:
            positions = self.get_positions()
            invested = sum(p["avg_price"] * p["size"] for p in positions)
            return max(0, 50.0 - invested)
        except:
            return 50.0

    def _resolve_token_id(self, market_slug, side):
        try:
            resp = _get_session().get(f"{GAMMA_API}/markets", params={"slug": market_slug}, timeout=30).json()
            if not resp:
                log.info(f"Slug miss, keyword search: {market_slug}")
                all_m = _get_session().get(f"{GAMMA_API}/markets",
                    params={"active":"true","closed":"false","limit":100}, timeout=30).json()
                terms = [w.lower() for w in market_slug.replace("-"," ").split() if len(w) > 2]
                matched = []
                for m in all_m:
                    q = (m.get("question","") + " " + m.get("slug","")).lower()
                    score = sum(1 for t in terms if t in q)
                    if score >= 2:
                        matched.append((score, m))
                if matched:
                    matched.sort(key=lambda x: x[0], reverse=True)
                    resp = [matched[0][1]]
                    log.info(f"Matched: {resp[0].get('question','')[:50]}")
                else:
                    log.warning(f"Not found: {market_slug}")
                    return None
            market = resp[0] if isinstance(resp, list) else resp
            tids = market.get("clobTokenIds", "")
            if isinstance(tids, str): tids = json.loads(tids)
            if not tids or len(tids) < 2: return None
            tid = tids[0] if side.upper() == "YES" else tids[1]
            log.info(f"token_id: {tid[:20]}...")
            return tid
        except Exception as e:
            log.exception(f"resolve failed: {e}")
            return None

    def place_bet(self, market_slug, side, amount, price):
        """
        跟网页一样的市价单逻辑：
        出价$0.99去吃卖方挂单，Polymarket会以卖方实际要价成交
        size = amount / price 控制花多少钱
        """
        try:
            if not self.client:
                log.error("No CLOB client")
                return False
            token_id = self._resolve_token_id(market_slug, side)
            if not token_id:
                return False

            # size = 想买多少份，用AI给的市场价算
            # 先查实际卖价，用真实价格计算size
            try:
                book = self.client.get_order_book(token_id)
                asks = getattr(book, 'asks', [])
                if asks:
                    first_ask = asks[0]
                    actual_price = float(getattr(first_ask, 'price', price))
                    log.info(f"Actual ask price: ${actual_price}")
                else:
                    actual_price = price
            except:
                actual_price = price

            # 用实际卖价计算size，确保不超预算
            size = round(amount / actual_price, 2)
            if size < 1:
                size = 1
            
            expected_cost = size * actual_price
            log.info(f"Budget: ${amount} | Actual price: ${actual_price} | Size: {size} | Expected cost: ${expected_cost:.2f}")

            buy_price = 0.99

            log.info(f"Market order: {market_slug} {side} ${amount} size={size} (sweep at $0.99)")
            order_args = OrderArgs(price=buy_price, size=size, side=BUY, token_id=token_id)
            result = self.client.create_and_post_order(order_args)
            log.info(f"Order result: {result}")
            return True
        except Exception as e:
            log.exception(f"place_bet failed: {e}")
            return False

    def close_position(self, market_slug):
        """卖出：出价$0.01扫买方挂单"""
        try:
            if not self.client: return False
            positions = self.get_positions()
            target = None
            for p in positions:
                if market_slug.lower() in p["market_slug"].lower():
                    target = p; break
            if not target:
                log.warning(f"Position not found: {market_slug}")
                return False
            token_id = target.get("asset") or self._resolve_token_id(market_slug, target["side"])
            if not token_id: return False

            # 出价$0.01扫买方，跟网页点Sell一样
            sell_price = 0.01
            log.info(f"Market sell: {market_slug} size={target['size']} (sweep at $0.01)")
            order_args = OrderArgs(price=sell_price, size=target["size"], side=SELL, token_id=token_id)
            result = self.client.create_and_post_order(order_args)
            log.info(f"Sell result: {result}")
            return True
        except Exception as e:
            log.exception(f"close_position failed: {e}")
            return False
