#!/usr/bin/env python3

# ==============================================================================
# Cowrie Command Intercept Layer — Project SCALPEL
# FAU Team - eMERGE 2026 Hackathon
#
# This file hooks into Cowrie's command pipeline and routes every attacker
# command through the four-tier intelligence stack:
#
#   Tier 1 — Static lookup table    (instant, ~0ms)
#   Tier 2 — Rule-based classifier  (fast, ~1ms)
#   Tier 3 — Local Ollama LLM       (moderate, ~1-3s)
#   Tier 4 — AWS Bedrock            (cloud, only when needed)
#
# INSTALL:
#   1. Copy this file to ~/cowrie/cowrie/commands/scalpel_intercept.py
#   2. Copy tier1_static.py, tier2_classifier.py, tier3_ollama_tier4_cloud.py
#      to the same directory
#   3. Edit ~/cowrie/etc/cowrie.cfg and add under [shell]:
#        [shell]
#        filesystem = share/cowrie/fs.pickle
#   4. In cowrie.cfg add the custom command module path:
#        [honeypot]
#        interact_timeout = 120
#   5. Restart Cowrie: ~/cowrie/bin/cowrie restart
#
# HOW COWRIE COMMAND INTERCEPTION WORKS:
#   Cowrie looks for command handlers in cowrie/commands/
#   Each handler is a class that Cowrie calls when the attacker runs a command.
#   We register a catch-all handler that intercepts everything before
#   Cowrie's built-in handlers run.
#
# ==============================================================================

import sys
import os
import time
import json
import logging
from datetime import datetime

# Add parent directory to path so we can import tier modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tier1_static as T1
    import tier2_classifier as T2
    import tier3_ollama_tier4_cloud as T34
    TIERS_LOADED = True
except ImportError as e:
    TIERS_LOADED = False
    print(f"[SCALPEL] Warning: Could not load tier modules: {e}")

log = logging.getLogger(__name__)

# ==============================================================================
# Metrics tracker — used for presentation and post-session report
# ==============================================================================

class MetricsTracker:
    def __init__(self):
        self.total_commands = 0
        self.tier1_hits = 0
        self.tier2_hits = 0
        self.tier3_hits = 0
        self.tier4_hits = 0
        self.fallback_hits = 0
        self.latencies = []
        self.log_path = os.path.expanduser("~/cowrie/var/log/cowrie/scalpel_metrics.json")

    def record(self, tier: int, command: str, latency_ms: float):
        self.total_commands += 1
        if tier == 1:
            self.tier1_hits += 1
        elif tier == 2:
            self.tier2_hits += 1
        elif tier == 3:
            self.tier3_hits += 1
        elif tier == 4:
            self.tier4_hits += 1
        else:
            self.fallback_hits += 1
        self.latencies.append(latency_ms)
        self._write()

    def _write(self):
        try:
            data = {
                "timestamp": datetime.utcnow().isoformat(),
                "total_commands": self.total_commands,
                "tier1_hits": self.tier1_hits,
                "tier2_hits": self.tier2_hits,
                "tier3_hits": self.tier3_hits,
                "tier4_hits": self.tier4_hits,
                "fallback_hits": self.fallback_hits,
                "cloud_escalation_rate": round(self.tier4_hits / max(self.total_commands, 1), 3),
                "local_handle_rate": round((self.tier1_hits + self.tier2_hits + self.tier3_hits) / max(self.total_commands, 1), 3),
                "avg_latency_ms": round(sum(self.latencies) / len(self.latencies), 1) if self.latencies else 0,
                "max_latency_ms": round(max(self.latencies), 1) if self.latencies else 0,
            }
            with open(self.log_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def summary(self) -> str:
        total = max(self.total_commands, 1)
        return (
            f"\n=== SCALPEL Metrics ===\n"
            f"Total commands    : {self.total_commands}\n"
            f"Tier 1 (static)   : {self.tier1_hits} ({100*self.tier1_hits//total}%)\n"
            f"Tier 2 (rules)    : {self.tier2_hits} ({100*self.tier2_hits//total}%)\n"
            f"Tier 3 (local LLM): {self.tier3_hits} ({100*self.tier3_hits//total}%)\n"
            f"Tier 4 (cloud)    : {self.tier4_hits} ({100*self.tier4_hits//total}%)\n"
            f"Cloud rate        : {100*self.tier4_hits//total}%\n"
            f"Avg latency       : {round(sum(self.latencies)/len(self.latencies), 1) if self.latencies else 0}ms\n"
        )


metrics = MetricsTracker()


# ==============================================================================
# Core routing function
# ==============================================================================

def route_command(command: str) -> tuple[str, int]:
    """
    Routes a command through the tier stack.
    Returns (response_text, tier_used)
    """
    if not TIERS_LOADED:
        return "", 0

    start = time.time()

    # --- Tier 1: Static lookup ---
    found, response = T1.lookup(command)
    if found:
        latency_ms = (time.time() - start) * 1000
        metrics.record(1, command, latency_ms)
        log.info(f"[SCALPEL T1] cmd={command!r} latency={latency_ms:.1f}ms")
        return response, 1

    # --- Tier 2: Rule-based classifier ---
    handled, response, force_cloud = T2.classify(command)
    if handled:
        latency_ms = (time.time() - start) * 1000
        metrics.record(2, command, latency_ms)
        log.info(f"[SCALPEL T2] cmd={command!r} latency={latency_ms:.1f}ms")
        return response, 2

    # --- Tier 3/4: LLM or cloud ---
    response = T34.handle(command, force_cloud=force_cloud)
    latency_ms = (time.time() - start) * 1000

    # Determine which tier was actually used based on latency heuristic
    # Tier 3 (Ollama) typically <5s, Tier 4 (cloud) typically >5s
    tier_used = 4 if force_cloud or latency_ms > 5000 else 3
    metrics.record(tier_used, command, latency_ms)
    log.info(f"[SCALPEL T{tier_used}] cmd={command!r} latency={latency_ms:.1f}ms force_cloud={force_cloud}")

    return response, tier_used


# ==============================================================================
# Cowrie integration
# ==============================================================================

# Cowrie command handler base class
try:
    from cowrie.shell.command import HoneyPotCommand

    class Command_scalpel_intercept(HoneyPotCommand):
        """
        Catch-all Cowrie command handler.
        Registered for commands not handled by Cowrie's built-ins.
        """
        def call(self):
            command = " ".join([self.cmd] + list(self.args))
            response, tier = route_command(command)
            if response:
                self.write(response + "\n")

    # Register as the default handler for unknown commands
    commands = {}

except ImportError:
    # Running outside Cowrie (e.g., testing) — just define the routing function
    pass


# ==============================================================================
# Cowrie plugin hook — intercept ALL commands before built-in handlers
# ==============================================================================

def install_intercept_hook():
    """
    Patches Cowrie's command dispatcher to run our routing logic first.
    Call this from Cowrie's startup sequence or from cowrie.cfg plugin path.

    This is the preferred integration method — it intercepts before Cowrie's
    built-in handlers so our responses take priority.
    """
    try:
        from cowrie.shell import server
        original_dispatch = server.CowrieSSHChannel.dataReceived

        def patched_dispatch(self, data):
            command = data.decode("utf-8", errors="replace").strip()
            if command:
                response, tier = route_command(command)
                if response is not None:
                    self.write(response.encode("utf-8") + b"\n")
                    return
            original_dispatch(self, data)

        server.CowrieSSHChannel.dataReceived = patched_dispatch
        log.info("[SCALPEL] Command intercept hook installed successfully")
        print("[SCALPEL] Command intercept hook installed")

    except Exception as e:
        log.warning(f"[SCALPEL] Could not install hook: {e}")
        print(f"[SCALPEL] Hook install failed: {e} — falling back to command handler mode")


# ==============================================================================
# Startup — warm up Ollama model on load
# ==============================================================================

def startup():
    """Call this when Cowrie starts to warm up the LLM."""
    print("[SCALPEL] Starting intelligence stack...")
    if TIERS_LOADED:
        T34.warm_up()
        print("[SCALPEL] Tier 1 (static), Tier 2 (rules), Tier 3 (Ollama), Tier 4 (cloud) ready")
        print(f"[SCALPEL] AWS Bedrock: {'configured' if T34.AWS_BEDROCK_ENDPOINT != 'CHANGE_ME' else 'NOT YET CONFIGURED — set in tier3_ollama_tier4_cloud.py'}")
    else:
        print("[SCALPEL] WARNING: Tier modules not loaded — running in passthrough mode")


if __name__ == "__main__":
    # Test the routing stack standalone
    startup()
    print()

    test_commands = [
        "whoami",
        "ps aux",
        "uname -a",
        "cat /etc/passwd",
        "netstat -tlnp",
        "systemctl status apache2",
        "find / -name '*.php'",
        "ls -la /root",
        "cat /var/www/html/config.php",
        "python3 -c 'import socket; s=socket.socket()'",
    ]

    for cmd in test_commands:
        print(f"\n[TEST] $ {cmd}")
        response, tier = route_command(cmd)
        print(f"[TIER {tier}] {response[:120] if response else '(empty)'}")

    print()
    print(metrics.summary())