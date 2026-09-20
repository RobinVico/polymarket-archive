#!/bin/bash
# 天气 bot 重启脚本 — 唯一推荐的重启方式
# 只杀 5053 端口的监听进程 (绝不按进程名杀, 保证碰不到 5051 主 bot / 5052 auto)
set -u
cd /Users/baymaxagent/天气

PIDS=$(lsof -ti tcp:5053 -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  echo "stopping old instance: $PIDS"
  echo "$PIDS" | xargs kill -9 2>/dev/null || true
  sleep 1
fi

nohup .venv/bin/python main.py > output.log 2>&1 &
echo "started pid $!"
sleep 5
tail -8 bot.log
