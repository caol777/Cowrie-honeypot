#!/usr/bin/env python3
"""
system_facts.py — Single source of truth for Project SCALPEL's fake-system profile.

Every tier module, the Ollama/Bedrock system prompt, and bait.sh all read their
canonical values from here. If a fake fact appears in two places, at most ONE
of them hand-rolled the string; the other MUST derive from here.

Profile: Raspberry Pi 5 Model B / Debian 13 (trixie) / aarch64 / 16 GB / kernel 6.12.

Usage:
    # from Python
    from system_facts import HOSTNAME, IP_SELF, ...

    # from bash (bait.sh, health_check.sh, install_ollama.sh)
    eval "$(python3 system_facts.py --shell)"
    echo $HOSTNAME

    # for debugging
    python3 system_facts.py --json | jq .
"""

from __future__ import annotations
import json
import sys

# ---- Identity ----
HOSTNAME = "raspberrypi"
DOMAIN = "sensor.local"
FQDN = f"{HOSTNAME}.{DOMAIN}"
MACHINE_ID = "f4c3a9b1d26e48a7a0b1c2d3e4f50617"  # 32 hex chars

# ---- OS ----
OS_NAME = "Debian GNU/Linux"
OS_PRETTY = "Debian GNU/Linux 13 (trixie)"
OS_VERSION_ID = "13"
OS_CODENAME = "trixie"
DEBIAN_VERSION = "13.4"

# ---- Kernel / Hardware ----
KERNEL_VERSION = "6.12.75+rpt-rpi-2712"
KERNEL_BUILD = ("Linux version 6.12.75+rpt-rpi-2712 (serge@raspberrypi.com) "
                "(aarch64-linux-gnu-gcc-14 (Debian 14.2.0-19) 14.2.0, "
                "GNU ld (GNU Binutils for Debian) 2.44) "
                "#1 SMP PREEMPT Debian 1:6.12.75-1+rpt1 (2026-03-11)")
ARCH = "aarch64"
PI_MODEL = "Raspberry Pi 5 Model B Rev 1.1"
PI_REVISION = "e04171"
PI_SERIAL = "394acb79c7ff9ea1"
CPU_COUNT = 4
RAM_KB = 16608192        # 16 GB

# ---- SSH banner (Pre-Auth Fingerprinting — match Debian 13 / OpenSSH 9.2) ----
SSH_BANNER = "SSH-2.0-OpenSSH_9.2p1 Debian-2+deb13u1"

# ---- Network (single iface, wlan0, matches /proc/net/arp written by bait) ----
IFACE = "wlan0"
IP_SELF = "10.4.27.28"
MAC_SELF = "d8:3a:dd:a1:b2:c3"   # Pi 5 OUI
NETMASK = "255.255.255.0"
BROADCAST = "10.4.27.255"
SUBNET_CIDR = "10.4.27.0/24"

IP_GATEWAY = "10.4.27.1"
MAC_GATEWAY = "f4:1e:57:85:0b:06"

IP_NODE_BETA = "10.4.27.21"
MAC_NODE_BETA = "d8:3a:dd:b4:c5:d6"

IP_NODE_GAMMA = "10.4.27.22"
MAC_NODE_GAMMA = "d8:3a:dd:e7:f8:09"

IP_ADMIN = "10.4.27.50"
MAC_ADMIN = "5a:72:05:86:d5:b5"

DNS_PRIMARY = "10.4.27.1"
DNS_SECONDARY = "1.1.1.1"

# ---- Users ----
USER_NAME = "root"
USER_HOME = "/root"
USER_SHELL = "/bin/bash"

# ---- Uptime "baseline" (seconds since fake boot). Used by date/uptime handlers. ----
# 3 days, 2h 14m. tier1 promotes this to monotonic increments at call time.
UPTIME_SECONDS_AT_BAIT = 282841

# ---- Timezone ----
TIMEZONE = "America/New_York"   # Florida-based hackathon

# ---- Secrets (bait, not real) ----
DB_PASSWORD = "FAU_cyber_db_admin_99!"
DB_NAME = "sensor_data_metrics"
AWS_ACCESS_KEY_BAIT = "AKIAQX3LM7NP2RSTVW84"
AWS_SECRET_KEY_BAIT = "Jx7vK2mPqR9nL4wT6yB3hF8cZ1dA5eG0iUoYsNj"

# ---- Services claimed running ----
SERVICES_RUNNING = [
    "sshd", "cron", "apache2", "mariadb", "systemd-journald",
    "systemd-logind", "systemd-resolved", "systemd-networkd",
    "sensor-collector", "NetworkManager",
]
SERVICES_INSTALLED_NOT_RUNNING = ["rsyslog", "bluetooth"]

# ---- Installed binaries (affects `which` / `type` responses) ----
INSTALLED_BINS = {
    "bash": "/bin/bash", "sh": "/bin/sh", "python3": "/usr/bin/python3",
    "python": "/usr/bin/python3", "perl": "/usr/bin/perl",
    "curl": "/usr/bin/curl", "wget": "/usr/bin/wget",
    "git": "/usr/bin/git", "ssh": "/usr/bin/ssh", "scp": "/usr/bin/scp",
    "rsync": "/usr/bin/rsync", "tar": "/bin/tar", "gzip": "/bin/gzip",
    "mysql": "/usr/bin/mysql", "vim": "/usr/bin/vim", "nano": "/bin/nano",
    "htop": "/usr/bin/htop", "ps": "/bin/ps", "ls": "/bin/ls",
    "cat": "/bin/cat", "grep": "/bin/grep", "awk": "/usr/bin/awk",
    "sed": "/bin/sed", "find": "/usr/bin/find", "which": "/usr/bin/which",
    "systemctl": "/bin/systemctl", "service": "/usr/sbin/service",
    "netstat": "/bin/netstat", "ss": "/usr/bin/ss", "ip": "/usr/sbin/ip",
    "ifconfig": "/usr/sbin/ifconfig", "arp": "/usr/sbin/arp",
    "apt": "/usr/bin/apt", "apt-get": "/usr/bin/apt-get",
    "dpkg": "/usr/bin/dpkg", "ping": "/usr/bin/ping",
    "crontab": "/usr/bin/crontab", "env": "/usr/bin/env",
    "date": "/bin/date", "whoami": "/usr/bin/whoami", "id": "/usr/bin/id",
    "uname": "/bin/uname", "hostname": "/bin/hostname",
    "free": "/usr/bin/free", "df": "/bin/df", "du": "/usr/bin/du",
    "mount": "/bin/mount", "lsblk": "/bin/lsblk", "stat": "/usr/bin/stat",
    "file": "/usr/bin/file", "wc": "/usr/bin/wc", "head": "/usr/bin/head",
    "tail": "/usr/bin/tail", "sort": "/usr/bin/sort", "uniq": "/usr/bin/uniq",
    "uptime": "/usr/bin/uptime",
}
# Explicitly absent (attacker runs `which docker` → "no docker in …")
ABSENT_BINS = {"docker", "docker-compose", "kubectl", "podman", "nmap", "nc"}

# ---- File content registry (shared by bait.sh honeyfs + tier2 `cat` handler) ----
# Minimal version embedded here; full content lives in honeyfs/ on disk.
# The classifier uses this to decide "known path? return content" vs
# "unknown path? return realistic 'No such file' error."
KNOWN_PATHS = {
    "/etc/passwd", "/etc/shadow", "/etc/group", "/etc/hosts",
    "/etc/hostname", "/etc/os-release", "/etc/debian_version",
    "/etc/resolv.conf", "/etc/motd", "/etc/crontab", "/etc/machine-id",
    "/etc/timezone", "/etc/fstab", "/etc/shells", "/etc/login.defs",
    "/etc/issue", "/etc/issue.net", "/etc/nsswitch.conf",
    "/etc/ssh/sshd_config", "/etc/ssh/ssh_host_rsa_key.pub",
    "/etc/ssh/ssh_host_ed25519_key.pub", "/etc/ssh/ssh_host_ecdsa_key.pub",
    "/etc/cron.d/sensor-sync",
    "/proc/cpuinfo", "/proc/version", "/proc/meminfo", "/proc/uptime",
    "/proc/loadavg", "/proc/stat", "/proc/mounts", "/proc/filesystems",
    "/proc/net/arp", "/proc/net/tcp", "/proc/net/udp", "/proc/net/dev",
    "/boot/cmdline.txt", "/boot/config.txt",
    "/var/www/html/config.php",
    "/root/.bash_history", "/root/.bashrc", "/root/.profile",
    "/root/.aws/credentials", "/root/.aws/config",
    "/root/.ssh/known_hosts", "/root/.ssh/authorized_keys",
    "/root/.ssh/id_rsa", "/root/.ssh/id_rsa.pub",
    "/home/pi/.bash_history", "/home/pi/.bashrc",
    "/var/log/auth.log", "/var/log/syslog", "/var/log/dmesg",
    "/var/log/apt/history.log",
    "/opt/sensor/collect.sh", "/opt/sensor/sync_nodes.sh",
}

# ---- Directory structure (for `ls`) ----
DIRECTORY_LISTING = {
    "/": ["bin", "boot", "dev", "etc", "home", "lib", "lost+found", "media",
          "mnt", "opt", "proc", "root", "run", "sbin", "srv", "sys", "tmp",
          "usr", "var"],
    "/etc": ["apache2", "apt", "bash.bashrc", "bash_completion.d",
             "ca-certificates", "cron.d", "cron.daily", "cron.hourly",
             "cron.monthly", "cron.weekly", "crontab", "debian_version",
             "default", "dpkg", "fstab", "group", "hostname", "hosts",
             "init.d", "inputrc", "issue", "issue.net", "ld.so.cache",
             "ld.so.conf", "ld.so.conf.d", "localtime", "login.defs",
             "logrotate.conf", "logrotate.d", "machine-id", "motd",
             "mysql", "nanorc", "network", "NetworkManager", "nsswitch.conf",
             "os-release", "pam.conf", "pam.d", "passwd", "profile",
             "profile.d", "protocols", "rc0.d", "rc1.d", "rc2.d", "rc3.d",
             "rc4.d", "rc5.d", "rc6.d", "rcS.d", "resolv.conf", "rpc",
             "rsyslog.conf", "rsyslog.d", "security", "services", "shadow",
             "shells", "skel", "ssh", "ssl", "sudoers", "sudoers.d",
             "sysctl.conf", "sysctl.d", "systemd", "timezone", "udev",
             "update-motd.d", "xdg"],
    "/root": [".aws", ".bash_history", ".bashrc", ".cache", ".profile",
              ".ssh"],
    "/root/.aws": ["config", "credentials"],
    "/root/.ssh": ["authorized_keys", "id_rsa", "id_rsa.pub", "known_hosts"],
    "/home": ["pi", "webadmin"],
    "/home/pi": [".bash_history", ".bashrc", ".cache", ".profile"],
    "/var": ["backups", "cache", "lib", "local", "lock", "log", "mail",
             "opt", "run", "sensor-data", "spool", "tmp", "www"],
    "/var/log": ["apache2", "apt", "auth.log", "btmp", "cron.log", "daemon.log",
                 "dmesg", "dpkg.log", "journal", "kern.log", "lastlog",
                 "messages", "sensor.log", "syslog", "user.log", "wtmp"],
    "/var/www": ["html"],
    "/var/www/html": ["config.php", "index.html"],
    "/var/sensor-data": ["20260420-030000.json", "20260421-030000.json",
                         "20260422-030000.json", "20260423-030000.json"],
    "/opt": ["sensor"],
    "/opt/sensor": ["collect.sh", "sync_nodes.sh"],
    "/tmp": [],
    "/proc": ["cpuinfo", "meminfo", "version", "uptime", "loadavg", "stat",
              "mounts", "filesystems", "self", "net", "sys", "1", "2", "892",
              "1234", "2891"],
    "/proc/net": ["arp", "tcp", "udp", "dev", "route"],
    "/boot": ["cmdline.txt", "config.txt", "firmware", "initramfs-6.12.75-rpi",
              "System.map-6.12.75-rpi", "vmlinuz-6.12.75-rpi"],
    "/bin": [],  # populated by INSTALLED_BINS at runtime if needed
    "/usr": ["bin", "games", "include", "lib", "local", "sbin", "share", "src"],
    "/usr/bin": [],  # populated on demand
}

# ==============================================================================
# Natural-latency command classes (for Cloud Escalation Policy)
# ------------------------------------------------------------------------------
# Per Cloud Escalation Policy PDF: "A cloud escalation on a naturally-slow
# command is far less detectable than one on a command that should return in
# milliseconds." Use this set to pick WHICH commands to escalate to Tier 4.
# ==============================================================================

NATURALLY_SLOW_BINARIES = {
    # Package listings
    "dpkg", "apt", "apt-get", "apt-cache", "aptitude",
    # Filesystem walks
    "find", "locate", "updatedb", "du", "tree",
    # Large file / long-running
    "tar", "rsync", "scp", "gzip", "bunzip2",
    # Compile / build
    "make", "gcc", "g++", "cc", "cmake",
    # Network scans (attackers love these)
    "nmap", "masscan", "zmap",
    # Memory dump / process tree over many procs
    "ps", "top",
}

NATURALLY_FAST_BINARIES = {
    # These MUST be Tier 1 — never escalate, latency is the tell
    "whoami", "id", "pwd", "hostname", "uname", "echo", "date",
    "true", "false", "cd", "export", "alias", "unalias",
    "history", "jobs", "fg", "bg",
}

# ==============================================================================
# CLI — `python3 system_facts.py --shell` emits eval-able bash vars
# ==============================================================================

def _as_shell():
    """Emit shell-assignable vars for bait.sh / health_check.sh."""
    lines = []
    for name, val in sorted(globals().items()):
        if name.startswith("_") or name.isupper() is False:
            continue
        if isinstance(val, str):
            # shell-escape single quotes
            escaped = val.replace("'", "'\\''")
            lines.append(f"{name}='{escaped}'")
        elif isinstance(val, (int, float)):
            lines.append(f"{name}={val}")
        elif isinstance(val, (list, tuple, set, dict)):
            # skip containers from shell; bash can't use them directly
            continue
    return "\n".join(lines)


def _as_json():
    out = {}
    for name, val in sorted(globals().items()):
        if name.startswith("_") or not name.isupper():
            continue
        if isinstance(val, set):
            out[name] = sorted(val)
        elif isinstance(val, (str, int, float, list, tuple, dict)):
            out[name] = val
    return json.dumps(out, indent=2, default=str)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--json"
    if mode == "--shell":
        print(_as_shell())
    elif mode == "--json":
        print(_as_json())
    else:
        print("Usage: system_facts.py [--shell|--json]", file=sys.stderr)
        sys.exit(2)
