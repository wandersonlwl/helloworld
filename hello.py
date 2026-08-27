#!/usr/bin/env python3
"""
Teste dos endpoints do Grok Files com envio via Telegram.
"""

import requests
import os

# Configuração do Telegram (substitua se necessário)
TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"

# JWT (substitua pelo seu ou use variável de ambiente)
JWT = os.getenv("TERMINAL_JWT_VAL", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...")

def send_telegram(text):
    """Envia mensagem para o Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"Erro ao enviar: {e}")

def test_grok_files():
    """Testa endpoints do Grok Files e envia resultados."""
    base = "https://files.grok.com"
    headers = {"Authorization": f"Bearer {JWT}"}
    endpoints = [
        "/v1/files",
        "/v1/list",
        "/api/v1/files",
        "/files",
    ]
    send_telegram("🔍 **Testando endpoints do Grok Files**")
    for ep in endpoints:
        url = base + ep
        try:
            r = requests.get(url, headers=headers, timeout=10)
            status = r.status_code
            content = r.text[:200]  # Limita a 200 caracteres
            msg = f"**{ep}**\nStatus: {status}\n```\n{content}\n```"
            send_telegram(msg)
        except Exception as e:
            send_telegram(f"**{ep}**\nErro: {e}")

if __name__ == "__main__":
    test_grok_files()
