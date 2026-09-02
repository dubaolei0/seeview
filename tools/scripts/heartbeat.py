#!/usr/bin/env python3
# heartbeat.py — 钉钉群通知（加签模式）
# 用法: py -3 heartbeat.py <项目根目录>     → 发送日报
#       py -3 heartbeat.py                  → 发送欢迎介绍

import json
import sys
import os
import hmac
import hashlib
import base64
import time
import urllib.request
import urllib.parse
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# --- 配置区 ---
SECRET = "SECc30187087019e00860985d974237bfa55c70e3b205b78f7e9354aba87de17c31"
WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send?access_token=3b71bf7597aea21374b8b50dcbf81198165d18cb574bee8103ee7645384bd854"
# ----------------

def sign_dingtalk(secret):
    """生成钉钉加签签名"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(
        secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return timestamp, sign

def send(text, title="数学组通知"):
    """发送钉钉消息"""
    payload = json.dumps({
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text}
    }).encode("utf-8")
    timestamp, sign = sign_dingtalk(SECRET)
    url = f"{WEBHOOK_URL}&timestamp={timestamp}&sign={sign}"
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("errcode") == 0:
        print(f"OK: 已发送 ({title})")
    else:
        print(f"FAIL: {result}")

# 不带参数 → 发送欢迎消息
if len(sys.argv) < 2:
    send(
        "### 📚 数学组知识库已上线\n\n"
        "**这个项目是什么**\n"
        "我们建了一个共享知识库，整合了高考真题拆解（715份）、教材PDF（5册72节）、考点分析方法论、知识图谱等核心资产。所有资料放在 NAS 共享文件夹，10人共用一套数据。\n\n"
        "**这个机器人能做什么**\n"
        "📊 每日播报：每天推送使用统计（总人数/今日动态）\n"
        "📢 重要通知：知识库有重大更新时推送\n\n"
        "**怎么用知识库**\n"
        "打开 Claude Code，工作目录指向共享文件夹，即可自动读取所有资料。新人查看 ONBOARDING.md。",
        "数学组知识库介绍"
    )
    sys.exit(0)

# 带参数 → 发送日报
BASE_DIR = sys.argv[1]
LOG_FILE = os.path.join(BASE_DIR, "records/log.md")
TEAM_DIR = os.path.join(BASE_DIR, "community/team")
today = datetime.now().strftime("%Y-%m-%d")

today_count = 0
users = set()
if os.path.exists(LOG_FILE):
    for line in open(LOG_FILE, encoding="utf-8"):
        if today in line:
            today_count += 1
            parts = line.split("|")
            if len(parts) >= 3:
                name = parts[2].strip()
                if name and name != "姓名":
                    users.add(name)

total_users = len(users)
team_count = len([d for d in os.listdir(TEAM_DIR) if os.path.isdir(os.path.join(TEAM_DIR, d))]) if os.path.exists(TEAM_DIR) else 0

today_logs = []
if os.path.exists(LOG_FILE):
    for line in open(LOG_FILE, encoding="utf-8"):
        if today in line and "|" in line:
            parts = [p.strip() for p in line.strip().split("|")]
            if len(parts) >= 3 and parts[1] != "姓名":
                today_logs.append(f"- {parts[1]}: {parts[2]}")

text = f"### 📊 数学组知识库日报 — {today}\n\n"
text += f"**今日数据**\n"
text += f"- 总使用人数：{total_users} 人\n"
text += f"- 已建档成员：{team_count} 人\n"
text += f"- 今天使用次数：{today_count} 次\n"

if today_logs:
    text += f"\n**今日动态**\n"
    text += "\n".join(today_logs) + "\n"

send(text, f"数学组日报 — {today}")
