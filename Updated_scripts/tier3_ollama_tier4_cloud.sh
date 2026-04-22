#!/usr/bin/env python3

# ==============================================================================
# Tier 3 — Local Ollama LLM Handler
# Tier 4 — AWS Bedrock Escalation
# FAU Team - eMERGE 2026 Hackathon - Project SCALPEL
#
# Tier 3: Handles dynamic commands locally using a small LLM via Ollama.
#         Model stays resident in memory to avoid 30-40s reload penalty.
#
# Tier 4: Escalates to AWS Bedrock only when Tier 3 confidence is low
#         or command is flagged as high-complexity by Tier 2.
#
# IMPORTANT: Keep OLLAMA_MODEL resident in memory at all times.
#            Check: curl http://localhost:11434/api/ps
# ==============================================================================

import json
import time
import urllib.request
import urllib.error
import os

# ==============================================================================
# Config
# ==============================================================================

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:1.5b"   # Change to phi3:mini for higher quality if Pi can handle it

# !! DAY-OF: Fill in your AWS endpoint once they give you credentials !!
AWS_BEDROCK_ENDPOINT = "CHANGE_ME"   # e.g. https://bedrock-runtime.us-east-1.amazonaws.com/...
AWS_API_KEY = "CHANGE_ME"
AWS_REGION = "us-east-1"

# Timeout thresholds (seconds)
OLLAMA_TIMEOUT = 8      # if Ollama takes longer than this, escalate to cloud
BEDROCK_TIMEOUT = 15    # hard limit for cloud calls

# ==============================================================================
# System prompt — tells the LLM how to behave as a convincing Debian Pi shell
# ==============================================================================

SYSTEM_PROMPT = """You are simulating a real Debian Linux 11 (Bullseye) shell on a Raspberry Pi 4.
The hostname is pi-sensor-gateway. You are logged in as root.
The system is a sensor network node for a distributed IoT deployment.

When given a shell command, respond ONLY with what the terminal would output.
No explanations. No markdown. No preamble. Just the raw terminal output.

Key facts about this system:
- IP: 10.1.10.20, gateway: 10.1.10.1
- Other nodes: 10.1.10.21 (node-beta), 10.1.10.22 (node-gamma), 10.1.10.55 (admin)
- Services running: apache2, mariadb, sshd, cron, sensor collector
- Web root: /var/www/html with config.php containing DB credentials
- Python3, curl, wget, git are installed
- Docker is NOT installed
- The system has been running for 3 days without reboot

If the command would produce no output (like cd, export), return nothing.
If the command is not found, return: bash: <command>: command not found
Keep responses concise and realistic."""


# ==============================================================================
# Tier 3 — Ollama local LLM
# ==============================================================================

def _ollama_request(command: str) -> tuple[bool, str, float]:
    """
    Returns (success, response_text, latency_seconds)
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"Command: {command}\nOutput:",
        "system": SYSTEM_PROMPT,
        "stream": False,
        "keep_alive": "10m",   # Keep model in memory for 10 minutes — critical for latency
        "options": {
            "temperature": 0.3,      # Low temp = more consistent, realistic output
            "num_predict": 256,      # Limit output length — commands don't write novels
            "top_p": 0.9,
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            latency = time.time() - start
            return True, result.get("response", "").strip(), latency
    except urllib.error.URLError:
        return False, "", time.time() - start
    except Exception:
        return False, "", time.time() - start


def tier3_local(command: str) -> tuple[bool, str, bool]:
    """
    Returns (handled, response, should_escalate).
    If Ollama is down or too slow, sets should_escalate=True for Tier 4.
    """
    success, response, latency = _ollama_request(command)

    if not success:
        # Ollama unavailable — escalate to cloud
        return False, "", True

    if latency > OLLAMA_TIMEOUT:
        # Too slow — escalate to cloud
        return False, "", True

    if not response:
        # Empty response — return realistic empty output
        return True, "", False

    return True, response, False


# ==============================================================================
# Tier 4 — AWS Bedrock escalation
# ==============================================================================

def tier4_cloud(command: str) -> tuple[bool, str]:
    """
    Returns (success, response).
    Falls back to a safe default if cloud is unreachable.

    !! DAY-OF: Update AWS_BEDROCK_ENDPOINT and AWS_API_KEY once provided !!
    """
    if AWS_BEDROCK_ENDPOINT == "CHANGE_ME":
        # Cloud not configured yet — return a plausible fallback
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
        headers={
            "Content-Type": "application/json",
            "x-api-key": AWS_API_KEY,
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=BEDROCK_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            # Parse response based on Bedrock model format
            response = (
                result.get("completion") or
                result.get("content", [{}])[0].get("text", "") or
                result.get("outputText", "")
            ).strip()
            return True, response
    except Exception:
        return True, _safe_fallback(command)


def _safe_fallback(command: str) -> str:
    """
    Last resort — return something plausible so honeypot doesn't crash.
    Better to return a generic response than an error or silence.
    """
    cmd = command.strip().lower()

    if cmd.startswith("cat "):
        return "cat: No such file or directory"
    if cmd.startswith("cd "):
        return ""
    if cmd.startswith("ls"):
        return ""
    if "permission" in cmd or "sudo" in cmd:
        return "Permission denied"

    # Generic command not found
    parts = command.split()
    return f"bash: {parts[0]}: command not found" if parts else ""


# ==============================================================================
# Main entry point — called by cowrie_intercept.py
# ==============================================================================

def handle(command: str, force_cloud: bool = False) -> str:
    """
    Main handler for Tier 3/4.
    force_cloud=True skips Tier 3 and goes straight to Bedrock.
    """
    if force_cloud:
        _, response = tier4_cloud(command)
        return response

    # Try Tier 3 first
    handled, response, should_escalate = tier3_local(command)

    if handled:
        return response

    if should_escalate:
        _, response = tier4_cloud(command)
        return response

    # Tier 3 returned nothing useful — safe fallback
    return _safe_fallback(command)


def warm_up():
    """
    Call this on startup to pre-load the model into memory.
    Prevents the 30-40s cold start on the first real command.
    """
    print(f"[*] Warming up Ollama model ({OLLAMA_MODEL})...")
    success, _, latency = _ollama_request("echo warm up")
    if success:
        print(f"[+] Model loaded and ready ({latency:.2f}s)")
    else:
        print("[!] Ollama not available — Tier 3 disabled, falling back to Tier 4")


if __name__ == "__main__":
    warm_up()
    print()

    tests = [
        "ls /etc",
        "cat /var/www/html/config.php",
        "python3 --version",
        "mysql --version",
        "ls -la /root",
    ]
    for cmd in tests:
        print(f"[CMD] {cmd}")
        result = handle(cmd)
        print(f"[OUT] {result[:120]}")
        print()