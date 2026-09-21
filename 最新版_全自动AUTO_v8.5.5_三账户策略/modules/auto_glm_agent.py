"""AUTO: GLM 多轮自主搜索 agent (用户 2026-07-09 拍板: 像 Claude 一样 "搜→想→再搜→再想")。

老路径的问题: 一次性把 N 条搜索结果注入 prompt 再生成 —— 模型想到一半想再查点什么, 查不了。
本模块把 web_search 做成模型**可反复调用的函数工具**, 循环执行:
  发问 → 模型 tool_calls(query) → 打智谱 Web Search API 拿结果喂回 → 模型继续想/再搜 → … → 最终文本。

- 搜索走智谱独立 Web Search API (REST /paas/v4/web_search, search_pro), 跟 chat 注入式同源。
- 搜索次数上限 AUTO_GLM_AGENT_MAX_SEARCHES (默认 8); 用完强制"停止搜索, 输出最终答案"。
- 每次搜索取 AUTO_GLM_AGENT_SEARCH_COUNT 条 (默认 15), content_size=high。
- 任何一步失败 → 抛 AgentError; 调用方 (auto_discovery / auto_reeval) 自行回退老的一次性注入路径,
  保证定时链路永不因新路径瘫痪。AUTO_GLM_AGENTIC=0 可整体关闭回老路。
- 纯新增文件, 不改同步模块。
"""
import os
import json
import logging

import requests as rq

log = logging.getLogger("glm_agent")

AGENTIC_ON = os.environ.get("AUTO_GLM_AGENTIC", "1") not in ("0", "false", "False", "")
MAX_SEARCHES = int(os.environ.get("AUTO_GLM_AGENT_MAX_SEARCHES", "8"))
SEARCH_COUNT = int(os.environ.get("AUTO_GLM_AGENT_SEARCH_COUNT", "15"))
SEARCH_ENGINE = os.environ.get("AUTO_GLM_AGENT_SEARCH_ENGINE", "search_pro")
PER_RESULT_CHARS = int(os.environ.get("AUTO_GLM_AGENT_RESULT_CHARS", "2000"))
WEB_SEARCH_URL = "https://open.bigmodel.cn/api/paas/v4/web_search"


class AgentError(Exception):
    """agent 路径失败 (调用方应回退一次性注入搜索)。"""


TOOL_SPEC = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": ("联网搜索最新信息。一次一个查询词 (中英文都行, 越具体越好), 返回若干条带"
                        "标题/链接/正文摘录/日期的结果。可以反复调用: 先广撒网, 再对有苗头的深挖。"),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询词 (一次一个, ≤78字符)"},
            },
            "required": ["query"],
        },
    },
}]


def _rest_web_search(api_key, query, count=None, engine=None, timeout=45):
    """智谱独立 Web Search API。返回 (compact_results, urls)。失败抛异常 (由 agent 循环处理)。"""
    payload = {
        "search_engine": engine or SEARCH_ENGINE,
        "search_query": str(query or "")[:78],
        "count": int(count or SEARCH_COUNT),
        "content_size": "high",
    }
    r = rq.post(WEB_SEARCH_URL, json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=timeout)
    r.raise_for_status()
    data = r.json()
    items = data.get("search_result") or []
    compact, urls = [], []
    for it in items:
        if not isinstance(it, dict):
            continue
        link = it.get("link") or it.get("url") or ""
        if link:
            urls.append(str(link))
        compact.append({
            "title": str(it.get("title") or "")[:200],
            "url": str(link)[:300],
            "date": str(it.get("publish_date") or "")[:20],
            "content": str(it.get("content") or "")[:PER_RESULT_CHARS],
        })
    return compact, urls


def _create_tolerant(client, **kwargs):
    """SDK 不认某高级参数 (TypeError) 就按序去掉重试 (跟 auto_discovery/_reeval 同款, 复制而非 import)。"""
    optional = ["extra_body", "thinking", "temperature", "max_tokens", "tools"]
    while True:
        try:
            return client.chat.completions.create(**kwargs)
        except TypeError:
            for k in optional:
                if k in kwargs:
                    log.warning(f"[glm-agent] SDK 不认参数 {k}, 去掉重试")
                    kwargs.pop(k)
                    break
            else:
                raise


def _msg_text(msg):
    t = (getattr(msg, "content", None) or "")
    if not str(t).strip():
        t = (getattr(msg, "reasoning_content", None) or "")
    return str(t)


def _usage_of(resp):
    try:
        u = getattr(resp, "usage", None)
        return int(getattr(u, "prompt_tokens", 0) or 0), int(getattr(u, "completion_tokens", 0) or 0)
    except Exception:
        return 0, 0


def agentic_analyze(api_key, model, system_msg, user_prompt,
                    max_tokens=65536, temperature=0.3, reasoning="max",
                    max_searches=None, per_search_count=None, log_prefix="[glm-agent]"):
    """多轮自主搜索分析。返回 {"text", "tp", "tc", "sources", "n_searches"}。失败抛 AgentError。"""
    from zhipuai import ZhipuAI
    max_searches = int(max_searches or MAX_SEARCHES)
    per_search_count = int(per_search_count or SEARCH_COUNT)
    try:
        client = ZhipuAI(api_key=api_key, timeout=600.0)
    except TypeError:
        client = ZhipuAI(api_key=api_key)
    messages = [{"role": "system", "content": system_msg},
                {"role": "user", "content": user_prompt}]
    tp = tc = 0
    searches_used = 0
    sources = []
    forced_final = False
    try:
        for _round in range(max_searches + 4):   # 每轮=一次 chat 调用; +4 给"想而不搜"的中间轮留余量
            kwargs = dict(model=model, messages=messages,
                          max_tokens=max_tokens, temperature=temperature,
                          thinking={"type": "enabled"},
                          extra_body={"reasoning_effort": reasoning})
            if not forced_final:
                kwargs["tools"] = TOOL_SPEC   # 最终强制轮不给工具 → 模型只能输出答案
            resp = _create_tolerant(client, **kwargs)
            a, b = _usage_of(resp)
            tp += a
            tc += b
            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None) or []
            if not tool_calls:
                text = _msg_text(msg)
                if text.strip():
                    return {"text": text, "tp": tp, "tc": tc,
                            "sources": list(dict.fromkeys(sources))[:20], "n_searches": searches_used}
                if forced_final:
                    raise AgentError("强制最终轮仍无文本输出")
                # 没工具调用也没文本 (罕见) → 逼一次最终答案
                messages.append({"role": "user", "content": "请现在输出最终完整分析 (不要再调用工具)。"})
                forced_final = True
                continue
            # ---- 有工具调用: 逐个执行并喂回 ----
            asst = {"role": "assistant", "content": (getattr(msg, "content", None) or "")}
            asst["tool_calls"] = [{
                "id": tcall.id, "type": "function",
                "function": {"name": tcall.function.name, "arguments": tcall.function.arguments},
            } for tcall in tool_calls]
            messages.append(asst)
            for tcall in tool_calls:
                name = getattr(tcall.function, "name", "")
                out = ""
                if name != "web_search":
                    out = json.dumps({"error": f"未知工具 {name}, 只有 web_search 可用"}, ensure_ascii=False)
                elif searches_used >= max_searches:
                    out = json.dumps({"error": f"搜索次数已达上限 {max_searches}, 请基于已有信息输出最终分析"},
                                     ensure_ascii=False)
                else:
                    try:
                        args = json.loads(tcall.function.arguments or "{}")
                    except Exception:
                        args = {}
                    query = str(args.get("query") or "").strip()
                    if not query:
                        out = json.dumps({"error": "query 为空"}, ensure_ascii=False)
                    else:
                        searches_used += 1
                        try:
                            results, urls = _rest_web_search(api_key, query, count=per_search_count)
                            sources.extend(urls)
                            out = json.dumps({"query": query, "results": results}, ensure_ascii=False)
                            log.info(f"{log_prefix} 🔍 第{searches_used}/{max_searches}搜:「{query[:50]}」→ {len(results)} 条")
                        except Exception as e:
                            # 单次搜索失败不炸整轮: 告诉模型失败了, 它可换词重试 (次数已计)
                            out = json.dumps({"error": f"本次搜索失败: {type(e).__name__}", "query": query},
                                             ensure_ascii=False)
                            log.warning(f"{log_prefix} 搜索失败「{query[:50]}」: {e}")
                messages.append({"role": "tool", "tool_call_id": tcall.id, "content": out})
            if searches_used >= max_searches and not forced_final:
                messages.append({"role": "user",
                                 "content": "搜索次数已用完。请基于以上全部调研, 现在输出最终完整分析, 不要再调用工具。"})
                forced_final = True
        raise AgentError(f"超过最大轮数仍未产出最终答案 (搜索 {searches_used} 次)")
    except AgentError:
        raise
    except Exception as e:
        raise AgentError(f"{type(e).__name__}: {e}") from e
