#!/usr/bin/env python3

# ==============================================================================
# Tier 3 — Local Ollama LLM Handler (with retry + validation)
# Tier 4 — AWS Bedrock Escalation
# FAU Team - eMERGE 2026 Hackathon - Project SCALPEL
#
# Tier 3 matches the design diagram:
#   - Takes Tier 2 miss (timeout / invalid)
#   - Feeds the local LLM with: raw command, last 5 commands, fake FS snapshot
#   - Validates the LLM response
#   - Retries locally once if validation fails
#   - Hit   -> Output
#   - Miss  -> Tier 4 (payload enrichment / cloud)
#
# IMPORTANT: keep OLLAMA_MODEL resident in memory at all times.
#            Check: curl http://localhost:11434/api/ps
# ==============================================================================

import json
import time
import urllib.request
import urllib.error
from collections import deque
from threading import Lock

# ==============================================================================
# Config
# ==============================================================================

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:1.5b"   # swap to phi3:mini if the Pi 5 handles it comfortably

# !! DAY-OF: Fill in your AWS endpoint once they give you credentials !!
AWS_BEDROCK_ENDPOINT = "https://bedrock-runtime.us-east-1.amazonaws.com/"
AWS_API_KEY = ""
AWS_REGION = "us-east-1"

OLLAMA_TIMEOUT = 8        # seconds; retry or escalate if exceeded
BEDROCK_TIMEOUT = 15      # hard limit for cloud calls
TIER3_MAX_RETRIES = 0     # Tier 2 is the first SLM call; Tier 3 is the single retry.

# ==============================================================================
# Session state — last 5 commands + simulated cwd (per-process; fine for single
# active attacker session, which is how Cowrie launches command handlers)
# ==============================================================================

_HISTORY = deque(maxlen=5)
_HISTORY_LOCK = Lock()
_CWD = "/root"

FAKE_FS_SNAPSHOT = """\
/root: .bashrc .profile .ssh/ notes.txt
/etc: passwd shadow group hosts hostname os-release resolv.conf cron.d/ systemd/
/var/www/html: index.php config.php uploads/ admin/
/opt/sensor: collect.sh readings.db sensor.conf
/home/pi: .bash_history sensor_client.py
/home/webadmin: .ssh/ site_backup.tar.gz
"""


def _record_history(command: str, output: str) -> None:
    with _HISTORY_LOCK:
        _HISTORY.append((command, (output or "")[:200]))


def _history_block() -> str:
    with _HISTORY_LOCK:
        if not _HISTORY:
            return "(no prior commands this session)"
        return "\n".join(f"$ {c}\n{o}" for c, o in _HISTORY)


def _update_cwd(command: str) -> None:
    global _CWD
    target = command[3:].strip() or "/root"
    if target.startswith("/"):
        _CWD = target
    elif target == "..":
        _CWD = "/" if _CWD in ("/", "") else "/".join(_CWD.rstrip("/").split("/")[:-1]) or "/"
    else:
        _CWD = f"{_CWD.rstrip('/')}/{target}"


# ==============================================================================
# System prompt — tells the LLM how to behave as a convincing Debian Pi shell
# ==============================================================================

SYSTEM_PROMPT = """You are simulating a real Debian Linux 11 (Bullseye) shell on a Raspberry Pi 4.
The hostname is pi-sensor-gateway. You are logged in as root.
The system is a sensor network node for a distributed IoT deployment.

When given a shell command, respond ONLY with what the terminal would output.
No explanations. No markdown. No preamble. No code fences. Just the raw terminal output.

Key facts about this system:
- IP: 10.1.10.20, gateway: 10.1.10.1
- Other nodes: 10.1.10.21 (node-beta), 10.1.10.22 (node-gamma), 10.1.10.55 (admin)
- Services running: apache2, mariadb, sshd, cron, sensor collector
- Web root: /var/www/html with config.php containing DB credentials
- Users: root, pi (1000), webadmin (1001), mysql (1002), www-data
- Python3, curl, wget, git are installed. Docker is NOT installed.
- The system has been running for 3 days without reboot.

If the command produces no output (cd, export, assignments), return nothing.
If the command is not found, return exactly: bash: <command>: command not found
Keep responses concise and realistic. Stay consistent with the session history."""


# ==============================================================================
# Tier 3 — Ollama local LLM
# ==============================================================================

def _ollama_request(command: str) -> tuple[bool, str, float]:
    """
    Returns (success, response_text, latency_seconds).
    Feeds the LLM the command + session history + fake FS snapshot, as the
    design diagram specifies.
    """
    prompt = (
        f"Recent session history:\n{_history_block()}\n\n"
        f"Current directory: {_CWD}\n"
        f"Filesystem snapshot:\n{FAKE_FS_SNAPSHOT}\n"
        f"Command: {command}\nOutput:"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "keep_alive": "60m",
        "options": {
            "temperature": 0.15,
            "num_predict": 128,
            "top_p": 0.9,
            "stop": ["```", "\nNote:", "\nHere"],
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            latency = time.time() - start
            return True, result.get("response", "").strip(), latency
    except Exception:
        return False, "", time.time() - start


# ==============================================================================
# Response validation + sanitization
# ==============================================================================

_BAD_PREAMBLES = (
    "here ", "here's", "here is", "sure", "certainly", "output:", "note:",
    "as an ai", "i cannot", "i can't", "```",
)


def _validate_response(command: str, text: str) -> bool:
    """
    Returns True if the text looks like plausible raw shell output.
    Empty text is valid (many commands produce no output).
    """
    if text is None:
        return False
    t = text.strip()
    if not t:
        return True
    low = t.lower()
    if any(low.startswith(p) for p in _BAD_PREAMBLES):
        return False
    if "```" in t:
        return False
    if t.count("\n") > 60:
        return False
    if len(t) > 4000:
        return False
    return True


def _sanitize(text: str) -> str:
    """Strip code fences and obvious prompt artifacts."""
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("```"):
            continue
        lines.append(ln)
    return "\n".join(lines).rstrip()


def tier3_local(command: str, max_retries: int = TIER3_MAX_RETRIES) -> tuple[bool, str, bool]:
    """
    Returns (handled, response, should_escalate).
    Implements the 'Retry Locally' box from the design diagram:
    one retry on timeout OR invalid response, then escalate on Miss.
    """
    attempt = 0
    while attempt <= max_retries:
        success, response, latency = _ollama_request(command)
        if success and latency <= OLLAMA_TIMEOUT and _validate_response(command, response):
            return True, _sanitize(response), False
        attempt += 1

    return False, "", True


# ==============================================================================
# Tier 4 — AWS Bedrock escalation
# ==============================================================================

def tier4_cloud(command: str) -> tuple[bool, str]:
    """
    Returns (success, response). Falls back to a safe default if cloud is
    unreachable or not yet configured.
    """
    if AWS_BEDROCK_ENDPOINT == "CHANGE_ME":
        return True, _safe_fallback(command)

    payload = {
        "prompt": f"\n\nHuman: {SYSTEM_PROMPT}\n\nCommand: {command}\nOutput:\n\nAssistant:",
        "max_tokens_to_sample": 512,
        "temperature": 0.2,
        "top_p": 0.9,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        AWS_BEDROCK_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json", "x-api-key": AWS_API_KEY},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=BEDROCK_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            response = (
                result.get("completion")
                or result.get("content", [{}])[0].get("text", "")
                or result.get("outputText", "")
            ).strip()
            if not _validate_response(command, response):
                return True, _safe_fallback(command)
            return True, _sanitize(response)
    except Exception:
        return True, _safe_fallback(command)


def _safe_fallback(command: str) -> str:
    """Last-resort plausible output so the honeypot never goes silent."""
    cmd = command.strip().lower()
    if cmd.startswith("cat "):
        return "cat: No such file or directory"
    if cmd.startswith("cd "):
        return ""
    if cmd.startswith("ls"):
        return ""
    if "permission" in cmd or "sudo" in cmd:
        return "Permission denied"
    parts = command.split()
    return f"bash: {parts[0]}: command not found" if parts else ""


# ==============================================================================
# Main entry point — called by cowrie_intercept.py
# ==============================================================================

def handle(command: str) -> tuple[str, int]:
    """
    Tier 3 (retry) + Tier 4 (cloud) handler.
    Called by the orchestrator after Tier 2 (SLM) returns Miss.
    Returns (response, tier_used) where tier_used is 3 or 4.
    """
    cmd = command.strip()

    # cd is stateful — track it locally and do not call the LLM.
    if cmd.startswith("cd ") or cmd == "cd":
        _update_cwd(cmd if cmd != "cd" else "cd /root")
        _record_history(command, "")
        return "", 3

    handled, response, should_escalate = tier3_local(command)
    if handled:
        _record_history(command, response)
        return response, 3

    if should_escalate:
        _, response = tier4_cloud(command)
        _record_history(command, response)
        return response, 4

    fallback = _safe_fallback(command)
    _record_history(command, fallback)
    return fallback, 4


def warm_up() -> None:
    """Pre-load the model into memory to avoid the 30–40s cold start."""
    print(f"[*] Warming up Ollama model ({OLLAMA_MODEL})...")
    success, _, latency = _ollama_request("echo warm up")
    if success:
        print(f"[+] Model loaded and ready ({latency:.2f}s)")
    else:
        print("[!] Ollama not available — Tier 3 disabled, will fall through to Tier 4")


if __name__ == "__main__":
    warm_up()
    print()

    tests = [
        "ls /etc",
        "cat /var/www/html/config.php",
        "python3 --version",
        "mysql --version",
        "cd /var/www/html",
        "ls",
        "ls -la /root",
    ]
    for cmd in tests:
        print(f"[CMD] {cmd}")
        result, tier = handle(cmd)
        print(f"[T{tier}] {result[:160]}")
        print()
