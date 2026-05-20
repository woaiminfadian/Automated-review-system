#!/bin/bash
cd "$(dirname "$0")/database"
echo "学报管理系统 v2 启动中..."
echo "启动后，同局域网编辑可访问: http://$(ipconfig getifaddr en0):5678"
echo "本机访问: http://127.0.0.1:5678"
echo "按 Ctrl+C 停止"
python3 webapp.py 5678
