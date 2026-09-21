"""
Module C — 报告解析器
支持两种格式：
1. 扁平格式: {"slug":"xxx","mp":0.03,"tp":0.12,...}
2. 数组格式: {"new_bets":[...]}
"""

import json
import re
import logging

log = logging.getLogger("parser")


class ReportParser:

    def parse(self, raw_text: str) -> dict:
        if not raw_text:
            return None

        # 方法1: RESULT_JSON: {...}
        result = self._try_result_json(raw_text)
        if result:
            log.info("RESULT_JSON解析成功")
            return result

        # 方法2: ```json 代码块
        result = self._try_json_block(raw_text)
        if result:
            log.info("JSON代码块解析成功")
            return self._to_standard(result)

        # 方法3: JSON标记后
        result = self._try_json_after_label(raw_text)
        if result:
            log.info("JSON标记解析成功")
            return self._to_standard(result)

        # 方法4: 裸JSON
        result = self._try_bare_json(raw_text)
        if result:
            log.info("裸JSON解析成功")
            return self._to_standard(result)

        log.error("所有解析方法均失败")
        return None

    def parse_position_action(self, raw_text: str) -> dict:
        default = {"action": "hold", "reasoning": "解析失败，默认持有"}
        if not raw_text:
            return default

        # 提取JSON
        data = None
        match = re.search(r'RESULT_JSON:\s*(\{.+\})', raw_text)
        if match:
            data = self._safe_parse(match.group(1))

        if not data:
            for method in [self._try_json_block, self._try_json_after_label, self._try_bare_json]:
                data = method(raw_text)
                if data:
                    break

        if data and "action" in data:
            action = str(data["action"]).lower().strip()
            if action in ("sell", "hold", "add"):
                return {
                    "action": action,
                    "ai_true_prob": float(data.get("tp", data.get("ai_true_prob", 0))),
                    "reasoning": data.get("reason", data.get("reasoning", "无"))
                }

        text_lower = raw_text.lower()
        if any(w in text_lower for w in ["卖出", "sell", "平仓", "止损"]):
            return {"action": "sell", "reasoning": "关键词: 建议卖出"}
        if any(w in text_lower for w in ["加仓", "add", "double"]):
            return {"action": "add", "reasoning": "关键词: 建议加仓"}
        return default

    def _to_standard(self, data: dict) -> dict:
        """把任何格式的JSON转成标准格式 {"new_bets": [...], "position_actions": [...]}"""

        # 已经是标准格式
        if "new_bets" in data:
            return self._validate_bets(data)

        # 扁平格式: {"slug":"xxx","mp":0.03,...}
        if "slug" in data:
            return self._flat_to_standard(data)

        # 未知格式
        log.warning(f"未知JSON格式: {list(data.keys())}")
        return {"new_bets": [], "position_actions": []}

    def _flat_to_standard(self, data: dict) -> dict:
        """扁平格式 → 标准格式"""
        slug = data.get("slug", "")
        if slug == "none" or not slug:
            return {"new_bets": [], "position_actions": []}

        mp = float(data.get("mp", data.get("market_price", 0)))
        tp = float(data.get("tp", data.get("ai_true_prob", 0)))
        if mp > 1: mp /= 100
        if tp > 1: tp /= 100

        if not (0.001 <= mp <= 0.20):
            log.warning(f"价格 {mp} 超出范围")
            return {"new_bets": [], "position_actions": []}
        if not (0.005 <= tp <= 0.90):
            log.warning(f"概率 {tp} 超出范围")
            return {"new_bets": [], "position_actions": []}
        if mp > 0 and tp / mp < 2.5:
            log.warning(f"边际不足: tp/mp = {tp/mp:.2f}")
            return {"new_bets": [], "position_actions": []}

        return {
            "new_bets": [{
                "market_slug": slug,
                "question": data.get("q", data.get("question", "")),
                "side": str(data.get("side", "NO")).upper(),
                "market_price": mp,
                "ai_true_prob": tp,
                "ai_confidence": data.get("conf", data.get("ai_confidence", "medium")),
                "reasoning_summary": str(data.get("reason", data.get("reasoning_summary", "")))[:200],
            }],
            "position_actions": []
        }

    def _validate_bets(self, data: dict) -> dict:
        """验证new_bets数组格式"""
        cleaned = {"new_bets": [], "position_actions": []}
        for bet in data.get("new_bets", []):
            try:
                mp = float(bet.get("market_price", bet.get("mp", 0)))
                tp = float(bet.get("ai_true_prob", bet.get("tp", 0)))
                if mp > 1: mp /= 100
                if tp > 1: tp /= 100
                if not (0.001 <= mp <= 0.20): continue
                if not (0.005 <= tp <= 0.90): continue
                if mp > 0 and tp / mp < 2.5: continue
                cleaned["new_bets"].append({
                    "market_slug": str(bet.get("market_slug", bet.get("slug", ""))),
                    "question": str(bet.get("question", bet.get("q", ""))),
                    "side": str(bet.get("side", "NO")).upper(),
                    "market_price": mp,
                    "ai_true_prob": tp,
                    "ai_confidence": str(bet.get("ai_confidence", bet.get("conf", "medium"))),
                    "reasoning_summary": str(bet.get("reasoning_summary", bet.get("reason", "")))[:200],
                })
            except:
                continue
        for action in data.get("position_actions", []):
            try:
                act = str(action.get("action", "hold")).lower()
                if act not in ("sell", "hold", "add"): act = "hold"
                cleaned["position_actions"].append({
                    "market_slug": str(action.get("market_slug", "")),
                    "action": act,
                    "reasoning_summary": str(action.get("reasoning_summary", ""))[:200],
                })
            except:
                continue
        return cleaned

    def _try_result_json(self, text: str) -> dict:
        match = re.search(r'RESULT_JSON:\s*(\{.+\})', text)
        if match:
            data = self._safe_parse(match.group(1))
            if data:
                return self._to_standard(data)
        return None

    def _try_json_block(self, text: str) -> dict:
        for pattern in [r'```json\s*\n?(.*?)\n?\s*```', r'```\s*\n?(\{.*?\})\n?\s*```']:
            for match in re.findall(pattern, text, re.DOTALL):
                result = self._safe_parse(match.strip())
                if result:
                    return result
        return None

    def _try_json_after_label(self, text: str) -> dict:
        for p in [r'(?:^|\n)\s*JSON\s*\n\s*(\{.+)', r'(?:^|\n)\s*json\s*\n\s*(\{.+)']:
            match = re.search(p, text, re.DOTALL | re.IGNORECASE)
            if match:
                result = self._safe_parse(match.group(1).strip())
                if result:
                    return result
        return None

    def _try_bare_json(self, text: str) -> dict:
        depth = 0
        end = -1
        start = -1
        for i in range(len(text) - 1, -1, -1):
            if text[i] == '}':
                if end == -1: end = i
                depth += 1
            elif text[i] == '{':
                depth -= 1
                if depth == 0 and end != -1:
                    start = i
                    break
        if start != -1 and end != -1:
            return self._safe_parse(text[start:end + 1])
        return None

    def _safe_parse(self, json_text: str) -> dict:
        try:
            return json.loads(json_text)
        except:
            pass
        fixed = re.sub(r'"position_actions"\s*:\s*\}', '"position_actions": []}', json_text)
        try:
            return json.loads(fixed)
        except:
            pass
        for suffix in [']}', '}', '"]}']:
            try:
                return json.loads(json_text + suffix)
            except:
                continue
        return None
