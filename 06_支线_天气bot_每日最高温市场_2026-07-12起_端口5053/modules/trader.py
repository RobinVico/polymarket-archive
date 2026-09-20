"""CLOB 下单 — 买入逻辑照抄 polymarket-auto 的 executor (2026-07 实测通过的版本):
FAK 限价 (best_ask 当限价) + 自动查 negRisk/tick_size + sig=3 存款钱包流 (py_clob_client_v2 1.0.2).

钱包没配 (.env 缺 POLY_PRIVATE_KEY) 时 ready=False, bot 照常跑 (只记录不下单).
"""
import logging
import math
import os
import time

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from modules.config import ROOT

load_dotenv(os.path.join(ROOT, ".env"))

log = logging.getLogger("trader")

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
DATA_API = "https://data-api.polymarket.com"

FUNDER = os.getenv("POLY_FUNDER", "").strip()
PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY", "").strip()
SIGNATURE_TYPE = int(os.getenv("POLY_SIGNATURE_TYPE", "3") or 3)


def _s():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])))
    return s


# 按 token 自动查 negRisk + tick_size (天气市场全是 negRisk, 写死 0.01/非neg 会下单必败)
_MARKET_OPT_CACHE = {}


def _order_options_for_token(token_id):
    c = _MARKET_OPT_CACHE.get(token_id)
    if c:
        return c
    neg, tick = False, "0.01"
    try:
        r = _s().get("https://gamma-api.polymarket.com/markets",
                     params={"clob_token_ids": token_id, "limit": 1}, timeout=8).json()
        if r and isinstance(r, list):
            m = r[0]
            neg = bool(m.get("negRisk"))
            t = m.get("orderPriceMinTickSize")
            if t:
                tick = ("%g" % float(t))
    except Exception as e:
        log.warning(f"order options 查询失败 (用默认 0.01/非negRisk): {e}")
        return (neg, tick)  # 失败不缓存, 下次再试
    _MARKET_OPT_CACHE[token_id] = (neg, tick)
    return neg, tick


class Trader:
    _instance = None

    def __init__(self):
        self.client = None
        self.ready = False
        self.err = ""
        if not PRIVATE_KEY or not FUNDER:
            self.err = "未配置钱包 (.env 填 POLY_PRIVATE_KEY / POLY_FUNDER 后重启)"
            log.warning(self.err)
            return
        try:
            from py_clob_client_v2 import ClobClient
            # 两步初始化: L1 拿 creds, 然后 L1+L2 重建 client (API key 自动派生, .env 不用填)
            tmp = ClobClient(host=HOST, chain_id=CHAIN_ID, key=PRIVATE_KEY,
                             signature_type=SIGNATURE_TYPE, funder=FUNDER)
            creds = tmp.create_or_derive_api_key()
            self.client = ClobClient(host=HOST, chain_id=CHAIN_ID, key=PRIVATE_KEY,
                                     signature_type=SIGNATURE_TYPE, funder=FUNDER, creds=creds)
            self.ready = True
            log.info(f"CLOB client OK (sig={SIGNATURE_TYPE}, funder={FUNDER[:8]}...)")
        except Exception as e:
            self.err = f"CLOB 初始化失败: {e}"
            log.error(self.err)

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ===== 只读 =====

    def get_cash_balance(self):
        """USDC 可用现金. 失败返回 None (跟真没钱 0.0 区分)."""
        try:
            if not self.client:
                return None
            from py_clob_client_v2 import BalanceAllowanceParams, AssetType
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            r = self.client.get_balance_allowance(params)
            bal_raw = r.get("balance") if isinstance(r, dict) else getattr(r, "balance", None)
            if bal_raw is None:
                return None
            return float(bal_raw) / 1_000_000
        except Exception as e:
            log.warning(f"get_cash_balance failed: {e}")
            return None

    def get_positions(self):
        """data-api 持仓 (专用钱包 → 全部都是天气仓). 带 30s 内存缓存."""
        cached = getattr(Trader, "_pos_cache", None)
        if cached and time.time() - cached[0] < 30:
            return cached[1]
        if not FUNDER:
            return []
        try:
            resp = _s().get(f"{DATA_API}/positions",
                            params={"user": FUNDER, "limit": 100, "sizeThreshold": 0},
                            timeout=30).json()
            if not isinstance(resp, list):
                return []
            positions = []
            for p in resp:
                size = float(p.get("size", 0))
                if size <= 0:
                    continue
                positions.append({
                    "title": p.get("title", "unknown"),
                    "side": p.get("outcome", ""),
                    "size": size,
                    "avg_price": float(p.get("avgPrice", 0)),
                    "cur_price": float(p.get("curPrice", 0)),
                    "pnl_pct": float(p.get("percentPnl", 0)),
                    "asset": p.get("asset", ""),
                    "slug": p.get("slug", ""),
                })
            Trader._pos_cache = (time.time(), positions)
            return positions
        except Exception as e:
            log.warning(f"get_positions failed: {e}")
            return []

    def _book(self, token_id):
        book = self.client.get_order_book(token_id)
        def side(name):
            v = getattr(book, name, None)
            if v is None and isinstance(book, dict):
                v = book.get(name)
            return v or []
        def price(x):
            if hasattr(x, "price"):
                return float(x.price)
            if isinstance(x, dict):
                return float(x["price"])
            if isinstance(x, (list, tuple)):
                return float(x[0])
            return None
        asks = [p for p in (price(a) for a in side("asks")) if p]
        bids = [p for p in (price(b) for b in side("bids")) if p]
        return (min(asks) if asks else None, max(bids) if bids else None)

    # ===== 下单 (抄 auto executor, FAK) =====

    def buy(self, token_id, usdc_amount, reason=""):
        """市价 FAK 买入 (best_ask 限价 + 美元金额). 返回 dict(ok, shares, usd, msg)."""
        try:
            if not self.client:
                return {"ok": False, "shares": 0, "usd": 0, "msg": "client未初始化"}
            usdc_amount = float(usdc_amount)
            if usdc_amount < 1:
                return {"ok": False, "shares": 0, "usd": 0, "msg": f"金额过小: ${usdc_amount}"}

            best_ask, _ = self._book(token_id)
            if not best_ask or best_ask <= 0:
                return {"ok": False, "shares": 0, "usd": 0, "msg": "盘口无 ask 或获取失败"}
            if best_ask >= 1.0:
                return {"ok": False, "shares": 0, "usd": 0, "msg": f"best_ask={best_ask} 异常 (>=1)"}

            # 新 CLOB 要求市价买单 maker 金额 (=size×price) 最多 2 位小数; 0.001-tick 价格还要凑步长:
            # step = 10/gcd(价格千分位, 10) ∈ {1,2,5,10}
            price_th = int(round(best_ask * 1000))
            step = 10 // math.gcd(price_th, 10)
            size = float(int(usdc_amount / best_ask))
            size -= size % step
            # 交易所最小单: 天气市场 minimum_order_size=5 股 (2026-07 实查), 且金额 ≥$1
            # (不加这条: 0.995 价位凑 step=2 会凑出 4 股 → 被交易所拒单)
            while size * best_ask < 1.0 or size < 5:
                size += step
            if size * best_ask > usdc_amount + max(2.0, usdc_amount * 0.75):
                return {"ok": False, "shares": 0, "usd": 0,
                        "msg": f"步长{step}股凑不出接近 ${usdc_amount} 的金额 (ask={best_ask})"}
            if size < 1:
                return {"ok": False, "shares": 0, "usd": 0,
                        "msg": f"size={size} 过小 (USDC={usdc_amount}, ask={best_ask})"}

            log.info(f"BUY token={str(token_id)[:20]}... usdc=${usdc_amount} "
                     f"ask=${best_ask:.4f} size={size} reason={reason}")

            from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions, Side
            neg, tick = _order_options_for_token(token_id)
            try:
                opts = PartialCreateOrderOptions(tick_size=tick, neg_risk=neg)
            except TypeError:
                opts = PartialCreateOrderOptions(tick_size=tick)
            try:
                result = self.client.create_and_post_order(
                    order_args=OrderArgs(token_id=token_id, price=best_ask,
                                         side=Side.BUY, size=size),
                    options=opts,
                    order_type=OrderType.FAK,
                )
            except Exception as e:
                log.exception(f"buy: create_and_post_order异常: {e}")
                return {"ok": False, "shares": 0, "usd": 0, "msg": f"下单异常: {e}"}

            log.info(f"buy raw result: {result}")
            if not isinstance(result, dict):
                return {"ok": False, "shares": 0, "usd": 0, "msg": f"result不是dict: {result!r}"[:200]}
            if not result.get("success", False):
                return {"ok": False, "shares": 0, "usd": 0,
                        "msg": result.get("errorMsg", "(no errorMsg)")}
            try:
                usd_spent = float(result.get("makingAmount", 0))  # v2 市价买单: making=花掉的USDC
            except (ValueError, TypeError):
                usd_spent = 0.0
            try:
                shares = float(result.get("takingAmount", 0) or 0)  # taking=拿到的股数
            except (ValueError, TypeError):
                shares = 0.0
            if usd_spent <= 0:
                return {"ok": False, "shares": 0, "usd": 0,
                        "msg": f"0成交 status={result.get('status')} order_id={result.get('orderID')}"}
            msg = f"买成功: {shares:.2f}股 @ {best_ask*100:.1f}% ≈ ${usd_spent:.2f}"
            log.info(msg)
            return {"ok": True, "shares": shares, "usd": usd_spent, "msg": msg}
        except Exception as e:
            log.exception(f"buy exception: {e}")
            return {"ok": False, "shares": 0, "usd": 0, "msg": str(e)}

    def sell(self, token_id, size, reason=""):
        """市价 FAK 卖出 (紧急手动用). 返回 (ok, msg)."""
        try:
            if not self.client:
                return False, "client未初始化"
            size = math.floor(size * 100) / 100
            if size < 0.01:
                return False, f"size={size} 过小"
            _, best_bid = self._book(token_id)
            if not best_bid or best_bid <= 0:
                return False, "盘口无 bid"
            log.info(f"SELL token={str(token_id)[:20]}... size={size} bid=${best_bid:.4f} reason={reason}")
            from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions, Side
            neg, tick = _order_options_for_token(token_id)
            try:
                opts = PartialCreateOrderOptions(tick_size=tick, neg_risk=neg)
            except TypeError:
                opts = PartialCreateOrderOptions(tick_size=tick)
            result = self.client.create_and_post_order(
                order_args=OrderArgs(token_id=token_id, price=best_bid,
                                     side=Side.SELL, size=size),
                options=opts,
                order_type=OrderType.FAK,
            )
            log.info(f"sell raw result: {result}")
            if not isinstance(result, dict) or not result.get("success", False):
                return False, str(result)[:200]
            making = float(result.get("makingAmount", 0) or 0)
            if making <= 0:
                return False, "0成交"
            return True, f"卖出 {making:.2f} 股 @ {best_bid:.3f}"
        except Exception as e:
            log.exception(f"sell exception: {e}")
            return False, str(e)
