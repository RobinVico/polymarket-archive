#!/bin/bash
# Polymarket AUTO 重启脚本 — 唯一推荐的重启方式
# 只杀 5052 端口的监听进程 (绝不按进程名杀, 保证碰不到老 bot 的 5051/main.py)
set -u
cd /Users/baymaxagent/polymarket-auto

PIDS=$(lsof -ti tcp:5052 -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  echo "stopping old instance: $PIDS"
  echo "$PIDS" | xargs kill -9 2>/dev/null || true
  sleep 1
fi

nohup .venv/bin/python autobot.py > output.log 2>&1 &
echo "started pid $!"
sleep 5
tail -5 bot.log
