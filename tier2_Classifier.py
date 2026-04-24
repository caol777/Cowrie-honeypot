#!/usr/bin/env python3

# ==============================================================================
# Tier 2 — Path-aware dispatcher + SLM fallback
# FAU Team - eMERGE 2026 Hackathon - Project SCALPEL
#
# Per designbase.png:
#     Tier 1 (hash-map cache) miss    ->  Tier 2 (Get and Validate)
#     Tier 2 Hit                      ->  Output
#     Tier 2 Miss (timeout / invalid) ->  Tier 3 (Retry Locally)
#
# The LLM alone can't invent a consistent filesystem or systemd state, so Tier 2
# first tries deterministic handlers driven by system_facts (ls, systemctl,
# service, which, type, cat-of-unknown-path). Only commands none of those
# recognize are forwarded to the SLM — which is where they belonged all along.
# ==============================================================================

import shlex
import time

try:
    # Loaded inside Cowrie — helpers live in cowrie.llm.
    from cowrie.llm import tier3_ollama_tier4_cloud as _slm
    from cowrie.llm import system_facts as sf
except ImportError:
    # Standalone dev/testing — they're siblings on sys.path.
    import tier3_ollama_tier4_cloud as _slm
    import system_facts as sf


# ==============================================================================
# Path helpers
# ==============================================================================

def _normpath(p: str) -> str:
    """Collapse . and .. without touching the filesystem."""
    parts: list[str] = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/" + "/".join(parts)


def _resolve(path: str) -> str:
    """Resolve against the session cwd that tier3 tracks."""
    if path.startswith("/"):
        return _normpath(path)
    return _normpath(f"{_slm._CWD.rstrip('/')}/{path}")


def _is_dir(path: str) -> bool:
    return path in sf.DIRECTORY_LISTING


# ==============================================================================
# ls / ls -l / ls -la
# ==============================================================================

def _ls_split_flags(argv: list[str]) -> tuple[set[str], list[str]]:
    flags: set[str] = set()
    paths: list[str] = []
    for a in argv[1:]:
        if a.startswith("--"):
            continue
        if a.startswith("-") and len(a) > 1:
            flags.update(a[1:])
        else:
            paths.append(a)
    return flags, paths


def _ls_long_line(parent: str, name: str) -> str:
    full = _normpath(f"{parent.rstrip('/')}/{name}") if parent != "/" else f"/{name}"
    is_dir = full in sf.DIRECTORY_LISTING
    if is_dir:
        perm, size = "drwxr-xr-x", 4096
        nlinks = 2
    else:
        perm, size = "-rw-r--r--", 512
        nlinks = 1
    # Give .ssh and .aws tighter perms to look right
    if name in (".ssh", ".aws"):
        perm = "drwx------"
    if name in ("id_rsa",):
        perm, size = "-rw-------", 2602
    if name in ("shadow",):
        perm, size = "-rw-r-----", 945
    owner = "root"
    if parent.startswith("/home/pi"):
        owner = "pi"
    date = time.strftime("%b %e %H:%M")
    return f"{perm} {nlinks} {owner} {owner} {size:>6} {date} {name}"


def _handle_ls(argv: list[str]) -> tuple[bool, str]:
    flags, paths = _ls_split_flags(argv)
    targets = paths if paths else [_slm._CWD]

    outputs: list[str] = []
    multi = len(targets) > 1

    for idx, raw in enumerate(targets):
        full = _resolve(raw)
        listing = sf.DIRECTORY_LISTING.get(full)

        if listing is None:
            # Could be a known file (ls on a file prints the file name)
            parent = _normpath(full.rsplit("/", 1)[0] or "/")
            base = full.rsplit("/", 1)[-1]
            if parent in sf.DIRECTORY_LISTING and base in sf.DIRECTORY_LISTING[parent]:
                outputs.append(_ls_long_line(parent, base) if "l" in flags else base)
                continue
            outputs.append(f"ls: cannot access '{raw}': No such file or directory")
            continue

        visible = sorted(listing) if "a" not in flags and "A" not in flags \
            else sorted([e for e in listing])
        if "a" not in flags and "A" not in flags:
            visible = [e for e in visible if not e.startswith(".")]
        if "a" in flags:
            visible = [".", ".."] + [e for e in visible]

        if multi:
            outputs.append(f"{raw}:")

        if "l" in flags:
            total = sum(4 if _is_dir(_normpath(f"{full.rstrip('/')}/{e}")) else 1 for e in visible)
            body = [f"total {total * 4}"]
            for name in visible:
                body.append(_ls_long_line(full, name))
            outputs.append("\n".join(body))
        else:
            outputs.append("  ".join(visible))

        if multi and idx < len(targets) - 1:
            outputs.append("")

    return True, "\n".join(outputs)


# ==============================================================================
# systemctl / service
# ==============================================================================

def _systemctl_active(svc: str) -> str:
    return (
        f"● {svc}.service - {svc.capitalize()} Service\n"
        f"     Loaded: loaded (/lib/systemd/system/{svc}.service; enabled; preset: enabled)\n"
        "     Active: active (running) since Sun 2026-04-20 11:52:03 EDT; 3 days ago\n"
        f"   Main PID: 1284 ({svc})\n"
        "      Tasks: 4 (limit: 9486)\n"
        "     Memory: 12.3M\n"
        "        CPU: 1.284s\n"
        f"     CGroup: /system.slice/{svc}.service\n"
        f"             └─1284 /usr/sbin/{svc}"
    )


def _systemctl_inactive(svc: str) -> str:
    return (
        f"○ {svc}.service - {svc.capitalize()} Service\n"
        f"     Loaded: loaded (/lib/systemd/system/{svc}.service; disabled; preset: enabled)\n"
        "     Active: inactive (dead)"
    )


def _handle_systemctl(argv: list[str]) -> tuple[bool, str]:
    if len(argv) < 2:
        return False, ""
    sub = argv[1]

    if sub == "status" and len(argv) >= 3:
        svc = argv[2].replace(".service", "")
        if svc in sf.SERVICES_RUNNING:
            return True, _systemctl_active(svc)
        if svc in sf.SERVICES_INSTALLED_NOT_RUNNING:
            return True, _systemctl_inactive(svc)
        return True, f"Unit {svc}.service could not be found."

    if sub == "is-active" and len(argv) >= 3:
        svc = argv[2].replace(".service", "")
        return True, "active" if svc in sf.SERVICES_RUNNING else "inactive"

    if sub == "is-enabled" and len(argv) >= 3:
        svc = argv[2].replace(".service", "")
        if svc in sf.SERVICES_RUNNING or svc in sf.SERVICES_INSTALLED_NOT_RUNNING:
            return True, "enabled"
        return True, (
            f"Failed to get unit file state for {svc}.service: "
            "No such file or directory"
        )

    if sub == "list-units":
        lines = ["UNIT                               LOAD   ACTIVE SUB     DESCRIPTION"]
        for s in sorted(sf.SERVICES_RUNNING):
            lines.append(
                f"{s}.service".ljust(34)
                + " loaded active running "
                + s.capitalize() + " Service"
            )
        lines.append("")
        lines.append(f"{len(sf.SERVICES_RUNNING)} loaded units listed.")
        return True, "\n".join(lines)

    return False, ""


def _handle_service(argv: list[str]) -> tuple[bool, str]:
    if len(argv) >= 3 and argv[2] == "status":
        svc = argv[1]
        if svc in sf.SERVICES_RUNNING:
            return True, f" * {svc} is running"
        if svc in sf.SERVICES_INSTALLED_NOT_RUNNING:
            return True, f" * {svc} is not running"
        return True, f"{svc}: unrecognized service"
    return False, ""


# ==============================================================================
# which / type / command -v
# ==============================================================================

def _handle_which(argv: list[str]) -> tuple[bool, str]:
    if len(argv) < 2:
        return False, ""
    out: list[str] = []
    for name in argv[1:]:
        if name in sf.INSTALLED_BINS:
            out.append(sf.INSTALLED_BINS[name])
        # Real `which` emits nothing on miss and returns 1
    return True, "\n".join(out)


def _handle_type(argv: list[str]) -> tuple[bool, str]:
    if len(argv) < 2:
        return False, ""
    out: list[str] = []
    for name in argv[1:]:
        if name in sf.INSTALLED_BINS:
            out.append(f"{name} is {sf.INSTALLED_BINS[name]}")
        else:
            out.append(f"bash: type: {name}: not found")
    return True, "\n".join(out)


def _handle_command(argv: list[str]) -> tuple[bool, str]:
    # `command -v <name>` behaves like a quiet which
    if len(argv) >= 3 and argv[1] == "-v":
        name = argv[2]
        if name in sf.INSTALLED_BINS:
            return True, sf.INSTALLED_BINS[name]
        return True, ""
    return False, ""


# ==============================================================================
# cat for unknown paths — known paths live in Tier 1, let them return there.
# If Tier 1 didn't match and the path isn't known, produce the real error.
# ==============================================================================

def _handle_cat(argv: list[str]) -> tuple[bool, str]:
    paths = [a for a in argv[1:] if not a.startswith("-")]
    if not paths:
        return False, ""  # bare `cat` reads stdin — let LLM/fallback handle
    outs: list[str] = []
    any_known = False
    for raw in paths:
        full = _resolve(raw) if not raw.startswith("/") else _normpath(raw)
        # Known path but not answered by Tier 1 -> defer to LLM
        if full in sf.KNOWN_PATHS:
            any_known = True
            break
        # Path points at a directory
        if full in sf.DIRECTORY_LISTING:
            outs.append(f"cat: {raw}: Is a directory")
            continue
        outs.append(f"cat: {raw}: No such file or directory")
    if any_known:
        return False, ""
    return True, "\n".join(outs)


# ==============================================================================
# ps — a plausible process list built from SERVICES_RUNNING
# ==============================================================================

def _handle_ps(argv: list[str]) -> tuple[bool, str]:
    # Only answer the common invocations; fancier flags go to the LLM
    flags = "".join(a.lstrip("-") for a in argv[1:] if a.startswith("-"))
    simple = len(argv) == 1
    if not (simple or set(flags) <= set("auxefwxAF")):
        return False, ""

    header = "  PID TTY          TIME CMD"
    lines = [header, "    1 ?        00:00:02 systemd"]
    pid = 100
    for svc in sorted(sf.SERVICES_RUNNING):
        lines.append(f" {pid:>4} ?        00:00:01 {svc}")
        pid += 1
    lines.append(" 9823 pts/0    00:00:00 bash")
    lines.append(" 9899 pts/0    00:00:00 ps")

    if "a" in flags or "e" in flags or "u" in flags or "x" in flags:
        header = "USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND"
        lines = [header]
        lines.append("root           1  0.1  0.2 167234 12384 ?        Ss   Apr20   0:02 /sbin/init")
        pid = 100
        for svc in sorted(sf.SERVICES_RUNNING):
            lines.append(
                f"root        {pid:>4}  0.0  0.3  92184  9823 ?        Ss   Apr20   0:01 /usr/sbin/{svc}"
            )
            pid += 1
        lines.append("root        9823  0.0  0.1  12384  4829 pts/0    Ss   12:34   0:00 -bash")
        lines.append("root        9899  0.0  0.0  10284  3212 pts/0    R+   12:34   0:00 ps " + " ".join(argv[1:]))
    return True, "\n".join(lines)


# ==============================================================================
# Dispatcher table
# ==============================================================================

_DISPATCHERS = {
    "ls": _handle_ls,
    "dir": _handle_ls,
    "systemctl": _handle_systemctl,
    "service": _handle_service,
    "which": _handle_which,
    "type": _handle_type,
    "command": _handle_command,
    "cat": _handle_cat,
    "ps": _handle_ps,
}


# ==============================================================================
# Public entry point
# ==============================================================================

def classify(command: str) -> tuple[bool, str]:
    """
    Tier 2 entry point.
    Returns (handled, response).
        handled=True  -> authoritative response; caller uses it directly.
        handled=False -> Miss; caller invokes Tier 3 (retry) then Tier 4 (cloud).
    """
    cmd = command.strip()
    if not cmd:
        return True, ""

    # Strip sudo prefix(es)
    stripped = cmd
    while stripped.startswith("sudo "):
        stripped = stripped[5:].lstrip()

    # cd is stateful and silent — handle without an LLM call.
    if stripped.startswith("cd ") or stripped == "cd":
        _slm._update_cwd(stripped if stripped != "cd" else "cd /root")
        _slm._record_history(command, "")
        return True, ""

    # Path-aware deterministic handlers (ls, systemctl, which, cat-unknown, ps, ...)
    try:
        argv = shlex.split(stripped)
    except ValueError:
        argv = stripped.split()
    if argv:
        handler = _DISPATCHERS.get(argv[0])
        if handler:
            handled, response = handler(argv)
            if handled:
                _slm._record_history(command, response)
                return True, response
            # handler returned (False, "") -> deliberate fall-through to the LLM

    # SLM fallback
    success, response, latency = _slm._ollama_request(command)

    if not success:
        return False, ""
    if latency > _slm.OLLAMA_TIMEOUT:
        return False, ""
    if not _slm._validate_response(command, response):
        return False, ""

    clean = _slm._sanitize(response)
    # qwen2.5:1.5b frequently returns empty on shell-emulation prompts. Treat
    # empty as a Miss so Tier 3 gets a second try instead of us claiming a hit.
    if not clean:
        return False, ""

    _slm._record_history(command, clean)
    return True, clean


if __name__ == "__main__":
    # Smoke test — the path-aware handlers do not need Ollama running.
    tests = [
        "ls",
        "ls /etc",
        "ls -la /root",
        "ls /var/www/html",
        "which docker",
        "which python3",
        "type curl",
        "systemctl status apache2",
        "systemctl status docker",
        "systemctl is-active mariadb",
        "service sshd status",
        "cat /etc/doesnotexist",
        "ps",
        "ps aux",
        "cd /var/www/html",
        "ls",  # after cd
    ]
    for t in tests:
        handled, resp = classify(t)
        print(f"[{'HIT' if handled else 'MISS'}] {t}")
        if handled and resp:
            print(f"  -> {resp[:160]}")
