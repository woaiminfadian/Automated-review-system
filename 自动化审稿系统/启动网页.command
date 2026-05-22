#!/bin/bash
# 学报管理系统 — 一键启动网页界面
cd "$(dirname "$0")/后端审稿系统"
echo "========================================="
echo "  法大研究生学报  —  管理系统"
echo "========================================="
echo ""
HOST=0.0.0.0 SECRET_KEY=a90594edc44a7ea698d2eab06fcc52432e98766b0f959f28 python3 webapp.py 5678 &
sleep 1.5
# 获取本机局域网 IP
LOCAL_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)
echo "本机访问: http://127.0.0.1:5678"
echo "局域网访问: http://${LOCAL_IP}:5678"
open "http://127.0.0.1:5678"
echo ""
echo "浏览器已打开，按 Ctrl+C 可停止服务。"
wait
