---
name: dns-poisoning-polymarket
description: "本机系统 DNS 对 *.polymarket.com 间歇性污染; 进程内 DoH guard 已兜底, 排查网络问题先想到它"
metadata: 
  node_type: memory
  type: project
  originSessionId: d6d4a450-58bd-4301-8b33-d12922015d6e
---

Mac mini 的系统 DNS (Tailscale 100.100.100.100 → 上游) 对 `*.polymarket.com` **间歇性 DNS 污染**: gamma-api 解析到 157.240.x.x (Facebook IP)、clob 解析到 162.125.x.x (Dropbox IP),TLS 证书校验失败或握手超时。8.8.8.8/1.1.1.1 直查返回正确 Cloudflare IP。

**Why:** 污染发作时整个 bot 静默degraded: 主页 0 positions、/history 现价全 None、resolution cron `checked=N updated=0`、CLOB 握手超时 — 没有单一明显报错,容易误判为代码 bug (2026-06-12 就差点把它当 /history 的 bug 修)。

**How to apply:** 遇到 polymarket API "突然全挂/数据全空"先 `dig +short gamma-api.polymarket.com` 对比 `dig @8.8.8.8`。修复已内置: `modules/gamma_client.py:install_polymarket_dns_guard()` (main.py 最早处安装, monkey-patch getaddrinfo 走 DoH 优先)。独立脚本要访问 polymarket 时也要先调用它 (参考 scripts/backfill_closed_resolution.py)。不要动系统 DNS / Tailscale 配置 ([[funnel-intentionally-on]] — Tailscale 配置是用户的领域)。
