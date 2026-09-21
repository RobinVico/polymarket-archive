"""AUTO q 校准 —— 单一来源 (2026-07-18 用户拍板, 取代旧的 prompt 内"打五折")。

背景 / 规则:
  旧做法 = DISCOVERY / REEVAL prompt 里让 GLM 自己算 q_校准 = 市场价 + 0.5×(q_raw − 市场价),
           把"你跟市场的分歧"收到 50% (打五折)。GLM 做算术, 后端直接用。
  新做法 (用户) = prompt 不再让 GLM 校准; 自动链路把机器指令覆盖成"直接给原始真实判断 q_raw",
           校准挪到 Python 这一处**确定性地**做一次, 系数 0.8 (信自己八成, 比旧的 0.5 更信自己):
                q_用 = 市场价 + AUTO_Q_TRUST × (q_raw − 市场价)
  选品 (auto_discovery._normalize) 和重评 (auto_reeval._run_one, 方向纠错闸之后) 都调这一个函数。

⚠️ prompts.py 一个字没改 —— 它跟"手动贴 Claude"那条流程共用 (dashboard.py 的 /api/reeval_prompt 等还活着),
   手动流程没有 Python 这一步、靠 prompt 内校准, 删了它手动那条就彻底没校准了。所以自动链路是在各自的
   机器指令 (auto_discovery.JSON_APPEND / auto_reeval.GLM_JSON_INSTRUCTION) 里**覆盖**成"给原始值",
   防止 GLM 的 0.5 校准值再被 Python 打一次 0.8 = 双重打折。

AUTO_Q_TRUST: 1.0 → 完全信自己 (不校准); 0.0 → 完全跟市场价; 默认 0.8。改这一个 env 就调信任度。
"""
import os

AUTO_Q_TRUST = float(os.environ.get("AUTO_Q_TRUST", "0.8"))


def calibrate_q(q_raw, market_price):
    """q_用 = 市场价 + AUTO_Q_TRUST × (q_raw − 市场价)。

    - 入参非法 → 原样返回 q_raw (调用方兜底);
    - 没有有效市场价 (0<mp<1 不成立) → 无从往市场收敛, 返回原始 q_raw;
    - 结果夹到 (0.001, 0.999) 开区间 (q_raw、mp 都在 (0,1) 时天然就在区间内, 夹只是保险)。
    """
    try:
        qr = float(q_raw)
        mp = float(market_price)
    except (TypeError, ValueError):
        return q_raw
    if not (0.0 < mp < 1.0):
        return qr
    q = mp + AUTO_Q_TRUST * (qr - mp)
    return min(0.999, max(0.001, q))
