---
name: cron-push-failing-backlog
description: "[已修复 2026-06-15] cron push 静默失败的根因=cron 够不到 macOS 钥匙串; 已加 store 凭证 fallback + 失败 sentinel. 再失败看 data/.backup_push_failing"
metadata: 
  node_type: memory
  type: project
  originSessionId: d6d4a450-58bd-4301-8b33-d12922015d6e
---

**根因 (2026-06-15 查明):** cron 跑 `git push` (HTTPS dev remote) 需认证, 凭证存在 macOS **登录钥匙串** (`credential.helper=osxkeychain`, 来自 Apple 系统 gitconfig)。但 cron 跑在 launchd **后台会话**, 够不到绑定 GUI 登录会话的钥匙串 → `git-credential-osxkeychain` 返回**空** → git 退回**问终端要用户名** → cron **无 TTY** → `fatal: could not read Username for 'https://github.com': Device not configured` → push 失败。`auto_backup.sh` 旧版 `git push 2>&1` 是最后一行**从不检查退出码** → 静默积压 (这次发现时积了 67 commit / 34 小时)。手动 push 能成是因为 Claude/终端跑在**已登录会话**, 够得到解锁的钥匙串。**不是** DNS/网络/token 过期问题。

**修复 (2026-06-15, commit 006d81b):**
1. 全局加 `credential.helper=store` 作为 osxkeychain 的 **fallback** (`git config --global --add`)。PAT 用 `git credential fill | git credential approve` 从钥匙串迁到 `~/.git-credentials` (chmod 600, token 没经过 transcript)。helper 链 = osxkeychain(系统) → store(全局): 交互式仍走钥匙串行为不变, cron 走文件凭证。已用 `GIT_TERMINAL_PROMPT=0 git -c credential.helper= -c credential.helper=store push` 模拟 cron (仅 store + 无 TTY) 验证推送成功。
2. `auto_backup.sh`: push 检查退出码, **失败**写 `data/.backup_push_failing` sentinel (gitignored) + 非零退出 + log "PUSH FAILED"; **成功**删 sentinel; 即使本轮无新改动只要 ahead>0 也重试 push (防历史积压不再尝试)。

**How to apply:** 平时不用再手动 push, cron 自己能推。若哪天又积压 → 99% 是 **PAT 过期** (钥匙串和 store 文件存的是同一个 token): 症状 = `data/.backup_push_failing` 文件存在 + `auto_backup.log` 有 "PUSH FAILED"。修法: 在 GitHub 重新生成 PAT, 同时更新钥匙串 (interactive `git push` 会重新存) **和** `~/.git-credentials` 里的 store 条目。参考 [[dns-poisoning-polymarket]] (那是另一类网络故障, 跟这个无关)。
