#!/usr/bin/env python3

# ==============================================================================
# Cowrie Command Intercept Layer — Project SCALPEL
# FAU Team - eMERGE 2026 Hackathon
#
# Helper modules live in ~/cowrie/src/cowrie/llm/ (NOT commands/).
# This file deploys as ~/cowrie/src/cowrie/commands/scalpel_intercept.py.
# The patched cowrie/shell/protocol.py:getCommand routes every command here
# via make_intercept_class(cmd_name).
# ==============================================================================

import sys
import os
import time
import json
import logging
from collections import deque
from datetime import datetime
from threading import Lock


# Running log of attacker commands for `history` — bounded so it can't grow
# unbounded. Kept per-process; for a single-attacker gauntlet this is
# equivalent to per-session.
_SESSION_HISTORY: deque = deque(maxlen=1000)
_SESSION_HISTORY_LOCK = Lock()


def _record_session_command(command: str) -> None:
    if not command:
        return
    if command.strip() == "history":
        return
    with _SESSION_HISTORY_LOCK:
        _SESSION_HISTORY.append(command)


def _render_history(limit: int = 100) -> str:
    with _SESSION_HISTORY_LOCK:
        entries = list(_SESSION_HISTORY)[-limit:]
    if not entries:
        return ""
    return "\n".join(f"{i + 1:>5}  {cmd}" for i, cmd in enumerate(entries))


try:
    from cowrie.llm import tier1_static as T1
    from cowrie.llm import tier2_classifier as T2
    from cowrie.llm import tier3_ollama_tier4_cloud as T34
    TIERS_LOADED = True
except ImportError:
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
# Metrics
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
# Core routing
# ==============================================================================

def route_command(command: str) -> tuple[str, int]:
    if not TIERS_LOADED:
        return "", 0

    _record_session_command(command)

    start = time.time()

    stripped = command.strip()
    if stripped == "history" or stripped.startswith("history "):
        limit = 100
        parts = stripped.split()
        if len(parts) == 2 and parts[1].isdigit():
            limit = int(parts[1])
        response = _render_history(limit)
        latency_ms = (time.time() - start) * 1000
        metrics.record(1, command, latency_ms)
        log.info(f"[SCALPEL T1 history] cmd={command!r} latency={latency_ms:.1f}ms")
        return response, 1

    found, response = T1.lookup(command)
    if found:
        latency_ms = (time.time() - start) * 1000
        metrics.record(1, command, latency_ms)
        log.info(f"[SCALPEL T1] cmd={command!r} latency={latency_ms:.1f}ms")
        return response, 1

    handled, response = T2.classify(command)
    if handled:
        latency_ms = (time.time() - start) * 1000
        metrics.record(2, command, latency_ms)
        log.info(f"[SCALPEL T2] cmd={command!r} latency={latency_ms:.1f}ms")
        return response, 2

    response, tier_used = T34.handle(command)
    latency_ms = (time.time() - start) * 1000
    metrics.record(tier_used, command, latency_ms)
    log.info(f"[SCALPEL T{tier_used}] cmd={command!r} latency={latency_ms:.1f}ms")
    return response, tier_used


# ==============================================================================
# Cowrie integration
# ==============================================================================

try:
    from cowrie.shell.command import HoneyPotCommand
    from twisted.python import log as twisted_log

    class Command_scalpel_intercept(HoneyPotCommand):
        """Catch-all Cowrie command handler.

        Cowrie's HoneyPotCommand doesn't receive the command name on init — only
        args. The patched getCommand uses make_intercept_class(cmd_name) to
        build a fresh subclass per command with _cmd_name baked in, so call()
        can reconstruct the full command line.
        """

        _cmd_name = ""  # overridden by the factory

        def call(self):
            # Synchronous path: write output before exit() so Cowrie's shell
            # redraws the prompt only after our response is flushed. Everything
            # wrapped in try/except: an unhandled exception here would
            # disconnect the attacker's SSH session.
            try:
                name = getattr(self, "_cmd_name", "") or ""
                args = [str(a) for a in (self.args or [])]
                command = " ".join([str(name)] + args).strip()
            except Exception as e:
                twisted_log.msg(f"[SCALPEL] cmd assembly failed: {e!r}")
                self._safe_exit()
                return

            if not command:
                self._safe_exit()
                return

            try:
                response, _tier = route_command(command)
            except Exception as e:
                twisted_log.msg(f"[SCALPEL] route_command crashed for {command!r}: {e!r}")
                response = ""

            if response:
                self._safe_write(response + "\r\n")

            self._safe_exit()

        def _safe_write(self, text: str) -> None:
            data = text.replace("\r\n", "\n").replace("\n", "\r\n")
            try:
                self.write(data)
            except TypeError:
                try:
                    self.write(data.encode("utf-8", "replace"))
                except Exception as e:
                    twisted_log.msg(f"[SCALPEL] write (bytes fallback) failed: {e!r}")
            except Exception as e:
                twisted_log.msg(f"[SCALPEL] write failed: {e!r}")

        def _safe_exit(self) -> None:
            # Some Cowrie versions auto-call exit() after call() returns; if we
            # also called exit() inside call(), the second call raises
            # ValueError('list.remove(x): x not in list'). Guard with a flag.
            if getattr(self, "_scalpel_exited", False):
                return
            self._scalpel_exited = True
            try:
                self.exit()
            except ValueError:
                # already removed from the command list — harmless
                pass
            except Exception as e:
                twisted_log.msg(f"[SCALPEL] exit failed: {e!r}")

    def make_intercept_class(cmd_name: str):
        """Return a fresh subclass with cmd_name baked into _cmd_name.
        Called by the patched getCommand in cowrie/shell/protocol.py."""
        return type(
            "Command_scalpel_intercept_dyn",
            (Command_scalpel_intercept,),
            {"_cmd_name": cmd_name},
        )

    commands = {"*": Command_scalpel_intercept}

except ImportError:
    def make_intercept_class(cmd_name: str):
        return None


# ==============================================================================
# Startup helpers — used by standalone smoke tests
# ==============================================================================

def startup():
    print("[SCALPEL] Starting intelligence stack...")
    if TIERS_LOADED:
        T34.warm_up()
        print("[SCALPEL] Tier 1 (cache), Tier 2 (SLM), Tier 3 (retry), Tier 4 (cloud) ready")
        cloud = (
            "configured"
            if T34.AWS_BEDROCK_ENDPOINT != "CHANGE_ME"
            else "NOT CONFIGURED"
        )
        print(f"[SCALPEL] AWS Bedrock: {cloud}")
    else:
        print("[SCALPEL] WARNING: tier modules not loaded — passthrough mode")


if __name__ == "__main__":
    startup()
    print()
    test_commands = [
        "whoami",
        "uname -a",
        "cat /etc/passwd",
        "ls /var/www/html",
        "systemctl status apache2",
        "history",
    ]
    for cmd in test_commands:
        print(f"\n[TEST] $ {cmd}")
        response, tier = route_command(cmd)
        print(f"[TIER {tier}] {response[:160] if response else '(empty)'}")
    print(metrics.summary())
