---
name: funnel-intentionally-on
description: "Tailscale Funnel 开着是有意的 (gmail-pubsub 需要公网), 不要关、不要再提醒"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a572a580-6150-42f5-804f-66e7df0b8b04
---

Tailscale Funnel 处于开启状态 (公网可达), 与 CLAUDE.md v5.7 "Funnel 关掉, tailnet-only" 的描述不一致 — 但这是**用户有意为之**, 2026-06-11 已确认 "这个不用管".

**Why:** serve 配置里有 `/gmail-pubsub → 127.0.0.1:8788` 路由 (`gog gmail watch` 边车, 开机自启), Google Pub/Sub 推送必须公网可达. Dashboard 本身有 session 密码层 (非 localhost Host 一律要 auth), 安全层还在.

**2026-06-19 追加:** 用户明确确认 **dashboard 本身公网常开也是有意的** (为了让没装 Tailscale 的设备 — 如 Windows 电脑 — 凭密码直接 `https://baymaxs-mac-mini.tailc6dc26.ts.net` 登录)。已解释"公网+密码 不如 tailnet-only 安全"+提议过"公网访问 开/关"app层开关, **用户拒绝, 决定一直公网常开、密码即可**。

**How to apply:** 开机检查 / 安全检查时看到 Funnel on / dashboard 公网可达, 不要报警、不要关掉、不要建议改 CLAUDE.md、**不要再提议加"公网访问开关"或建议改回 tailnet-only**. 用户已拍板. (唯一还值得做的: 若哪天发现 `DASHBOARD_PASSWORD` 很弱可一提, 因为它是公网唯一防线.)
