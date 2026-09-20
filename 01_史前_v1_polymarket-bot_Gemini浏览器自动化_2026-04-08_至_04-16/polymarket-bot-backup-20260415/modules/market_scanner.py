"""
Module A - Prompt Builder
Gemini: scout, Claude: extract JSON with real slug matching
"""
import logging
import requests
import json as _json

log = logging.getLogger("scanner")


class MarketScanner:

    def build_gemini_prompt(self, positions=None, balance=50.0):
        prompt = f"""你是一个顶级的预测市场分析师。请前往 Polymarket (https://polymarket.com) 进行深度搜索研究。

【任务】
搜索Polymarket上当前所有活跃市场，找出1个被大众情绪严重错误定价的小概率长尾事件。只推荐你最有把握的那1个。

【搜索标准】
- 关注定价在1%到15%之间的低概率选项
- 该市场需要有足够交易量（日交易量>$5,000）
- 距结算日至少7天以上
- 你评估的真实概率必须是市场定价的至少2.5倍以上

【分析方法】
1. 只依赖权威信息源（官方数据、SEC文件、政府公告、顶级科研机构），过滤社交媒体噪音
2. 查找历史基准率（Base Rate）：类似事件历史上的客观发生频率
3. 识别催化剂：结算日前是否有可能剧烈改变赔率的关键事件
4. 做魔鬼代言人反向测试：攻击你自己的逻辑，找黑天鹅因素
5. 给出独立于市场价格的真实概率评估

【背景信息】
- 73.4%的Polymarket事件最终结算为No（散户存在Yes Bias）
- 我的资金极小（${balance:.2f}），通过情绪波动差价获利，不一定持有到结算

"""
        prompt += "【已持有的市场，请排除】\n"
        if positions:
            for p in positions:
                prompt += f"- {p.get('market_slug', 'unknown')}: {p.get('side', '?')}\n"
        else:
            prompt += "- 无\n"

        prompt += """
【输出要求】
只推荐1个你最有把握的标的，详细写出：
- 市场名称、Polymarket URL中的slug、当前定价
- 你建议买入的方向（YES还是NO）
- 你找到的权威信息和Base Rate
- 催化剂事件及日期
- 魔鬼代言人的反驳及你的回应
- 你评估的真实概率

如果没有找到符合条件的，直接说没有，不要勉强推荐。"""
        return prompt

    def build_claude_prompt(self, balance=50.0, max_picks=1, market_list=None):
        prompt = "你有两个任务：\n"
        prompt += "1. 阅读Gemini Deep Research报告，提取推荐的标的信息\n"
        prompt += "2. 从下面的Polymarket真实市场列表中找到最匹配的市场，使用真实slug\n\n"
        prompt += "Gemini给的名称可能不准，你必须从列表中找最匹配的slug，不要编造。\n\n"

        if market_list:
            prompt += "=== Polymarket真实市场列表 ===\n"
            for m in market_list[:80]:
                prompt += f"slug={m['slug']} | q={m['question'][:60]} | price={m.get('price','?')}\n"
            prompt += "\n"

        prompt += '从列表中找匹配市场，只输出一行JSON，不要其他文字：\n'
        prompt += '{"slug":"列表中的真实slug","q":"完整问题","side":"YES或NO","mp":0.03,"tp":0.12,"conf":"medium","catalyst":"催化剂","reason":"50字理由"}\n\n'
        prompt += '如果找不到匹配，输出：{"slug":"none"}\n'
        prompt += '只输出一行JSON。'
        return prompt

    def build_position_review_gemini_prompt(self, position_info):
        alert_type = "盈利" if position_info["type"] == "profit" else "亏损"
        return f"""请搜索以下Polymarket市场的最新新闻和权威数据：

市场: {position_info.get('question', position_info.get('market_slug', 'unknown'))}
方向: {position_info['side']}
买入价: ${position_info['avg_price']:.3f}
当前价: ${position_info['current_price']:.3f}
当前{alert_type}: {abs(position_info['pct_change']):.1f}%

请分析：
1. 近期有什么新消息影响这个市场？
2. 基本面是否发生了根本变化？
3. 有没有即将到来的催化剂事件？
4. 当前价格波动是暂时的情绪还是基本面驱动的？
5. 你建议继续持有、卖出、还是加仓？

详细写出你的发现。"""

    def build_position_review_claude_prompt(self):
        return '阅读Gemini报告，提取持仓建议。只输出一行JSON：{"action":"sell或hold或add","tp":0.xx,"reason":"50字理由"}'

    def fetch_active_markets(self, limit=80):
        try:
            resp = requests.get(
                "https://gamma-api.polymarket.com/markets",
                params={"active": "true", "closed": "false", "limit": 200, "order": "volume24hr", "ascending": "false"},
                timeout=30,
            ).json()
            markets = []
            for m in resp:
                outcomes = m.get("outcomePrices", "")
                if isinstance(outcomes, str) and outcomes:
                    prices = _json.loads(outcomes)
                elif isinstance(outcomes, list):
                    prices = outcomes
                else:
                    continue
                has_low = any(0.001 <= float(p) <= 0.20 for p in prices)
                slug = m.get("slug", "")
                if slug and has_low:
                    markets.append({
                        "slug": slug,
                        "question": m.get("question", ""),
                        "price": ", ".join(f"{float(p):.3f}" for p in prices),
                    })
            return markets[:limit]
        except Exception as ex:
            log.warning(f"fetch markets failed: {ex}")
            return []
