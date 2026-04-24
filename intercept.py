#!/usr/bin/env python3

# ==============================================================================
# Cowrie Command Intercept Layer — Project SCALPEL
# FAU Team - eMERGE 2026 Hackathon
#
# Maps 1:1 to designbase.png:
#
#     Input (Raw Red Team Command)
#           |
#      [Tier 1] hash-map cache         --Hit-->  Output
#           |
#         Miss
#           |
#      [Tier 2] local SLM (get + validate)    --Hit-->  Output
#           |
#         Miss  (timeout / invalid response)
#           |
#      [Tier 3] retry locally                 --Hit-->  Output
#           |
#         Miss
#           |
#      [Tier 4] payload enrichment -> AWS Lambda
#                                  -> OpenSearch Serverless (RAG)
#                                  -> Claude Haiku
#                                  -> Latency masking -> Output
#
# INSTALL on the Pi:
#   1. Symlink this repo's modules into Cowrie's commands directory:
#        ln -sf $(pwd)/cowrie_intercept.py         ~/cowrie/src/cowrie/commands/scalpel_intercept.py
#        ln -sf $(pwd)/tier1_static.py             ~/cowrie/src/cowrie/commands/tier1_static.py
#        ln -sf $(pwd)/tier2_classifier.py         ~/cowrie/src/cowrie/commands/tier2_classifier.py
#        ln -sf $(pwd)/tier3_ollama_tier4_cloud.py ~/cowrie/src/cowrie/commands/tier3_ollama_tier4_cloud.py
#   2. Append to ~/cowrie/src/cowrie/commands/__init__.py:
#        from cowrie.commands import scalpel_intercept
#        commands = {"*": scalpel_intercept.Command_scalpel_intercept}
#   3. Restart Cowrie:
#        ~/cowrie/bin/cowrie restart
# ==============================================================================

import sys
import os
import time
import json
import logging
from datetime import datetime

# Ensure tier modules resolve whether we run standalone or under Cowrie.
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
# Metrics — feeds the presentation scoreboard
# ==============================================================================

class MetricsTracker:
    def __init__(self):
        self.total_commands = 0
        self.tier1_hits = 0
        self.tier2_hits = 0
        self.tier3_hits = 0
        self.tier4_hits = 0
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
        self.latencies.append(latency_ms)
        self._write()

    def _write(self):
        try:
            total = max(self.total_commands, 1)
            data = {
                "timestamp": datetime.utcnow().isoformat(),
                "total_commands": self.total_commands,
                "tier1_hits": self.tier1_hits,
                "tier2_hits": self.tier2_hits,
                "tier3_hits": self.tier3_hits,
                "tier4_hits": self.tier4_hits,
                "cloud_escalation_rate": round(self.tier4_hits / total, 3),
                "local_handle_rate": round(
                    (self.tier1_hits + self.tier2_hits + self.tier3_hits) / total, 3
                ),
                "avg_latency_ms": round(sum(self.latencies) / len(self.latencies), 1) if self.latencies else 0,
                "max_latency_ms": round(max(self.latencies), 1) if self.latencies else 0,
            }
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def summary(self) -> str:
        total = max(self.total_commands, 1)
        return (
            f"\n=== SCALPEL Metrics ===\n"
            f"Total commands    : {self.total_commands}\n"
            f"Tier 1 (cache)    : {self.tier1_hits} ({100*self.tier1_hits//total}%)\n"
            f"Tier 2 (SLM)      : {self.tier2_hits} ({100*self.tier2_hits//total}%)\n"
            f"Tier 3 (retry)    : {self.tier3_hits} ({100*self.tier3_hits//total}%)\n"
            f"Tier 4 (cloud)    : {self.tier4_hits} ({100*self.tier4_hits//total}%)\n"
            f"Avg latency       : {round(sum(self.latencies)/len(self.latencies), 1) if self.latencies else 0}ms\n"
        )


metrics = MetricsTracker()


# ==============================================================================
# Core routing — matches designbase.png edges exactly
# ==============================================================================

def route_command(command: str) -> tuple[str, int]:
    """Routes a command through the four-tier stack. Returns (response, tier)."""
    if not TIERS_LOADED:
        return "", 0

    start = time.time()

    # Tier 1 — hash-map cache of common commands
    found, response = T1.lookup(command)
    if found:
        latency_ms = (time.time() - start) * 1000
        metrics.record(1, command, latency_ms)
        log.info(f"[SCALPEL T1] cmd={command!r} latency={latency_ms:.1f}ms")
        return response, 1

    # Tier 2 — local SLM (first attempt, validated)
    handled, response = T2.classify(command)
    if handled:
        latency_ms = (time.time() - start) * 1000
        metrics.record(2, command, latency_ms)
        log.info(f"[SCALPEL T2] cmd={command!r} latency={latency_ms:.1f}ms")
        return response, 2

    # Tier 3 — local retry; Tier 4 — cloud on retry miss
    response, tier_used = T34.handle(command)
    latency_ms = (time.time() - start) * 1000
    metrics.record(tier_used, command, latency_ms)
    log.info(f"[SCALPEL T{tier_used}] cmd={command!r} latency={latency_ms:.1f}ms")
    return response, tier_used


# ==============================================================================
# Cowrie integration — non-blocking: SLM call runs off the Twisted reactor
# ==============================================================================

try:
    from cowrie.shell.command import HoneyPotCommand
    from twisted.internet.threads import deferToThread

    class Command_scalpel_intercept(HoneyPotCommand):
        """Catch-all Cowrie command handler for attacker input."""

        def call(self):
            command = " ".join([self.cmd] + list(self.args))
            d = deferToThread(route_command, command)

            def _done(result):
                response, _tier = result
                if response:
                    self.write(response + "\n")
                self.exit()

            def _fail(_err):
                self.write("\n")
                self.exit()

            d.addCallbacks(_done, _fail)

    # Catch-all registration — see INSTALL comment at top.
    commands = {"*": Command_scalpel_intercept}

except ImportError:
    # Running outside Cowrie (standalone test) — only route_command is exposed.
    pass


# ==============================================================================
# Startup — warm up the SLM so the first command doesn't eat a cold start
# ==============================================================================

def startup():
    print("[SCALPEL] Starting intelligence stack...")
    if TIERS_LOADED:
        T34.warm_up()
        print("[SCALPEL] Tier 1 (cache), Tier 2 (SLM), Tier 3 (retry), Tier 4 (cloud) ready")
        cloud = (
            "configured"
            if T34.AWS_BEDROCK_ENDPOINT != "CHANGE_ME"
            else "NOT CONFIGURED — set in tier3_ollama_tier4_cloud.py"
        )
        print(f"[SCALPEL] AWS Bedrock: {cloud}")
    else:
        print("[SCALPEL] WARNING: tier modules not loaded — passthrough mode")


if __name__ == "__main__":
    startup()
    print()

    test_commands = [
        "whoami",                         # T1
        "uname -a",                       # T1
        "cat /etc/passwd",                # T1
        "ls /var/www/html",               # T2 (SLM — not in cache)
        "find / -name 'config.php'",      # T2 or T3
        "cat /var/www/html/config.php",   # T2
        "cd /var/www/html",               # T2 (stateful cd)
        "ls",                             # T2 (uses session cwd)
        "python3 -c 'print(42)'",         # T2
        "systemctl status apache2",       # T2 or T4
    ]

    for cmd in test_commands:
        print(f"\n[TEST] $ {cmd}")
        response, tier = route_command(cmd)
        print(f"[TIER {tier}] {response[:160] if response else '(empty)'}")

    print(metrics.summary())
