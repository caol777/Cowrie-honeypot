#!/usr/bin/env python3
"""
Tier 1 — Static Command Lookup Table
Project SCALPEL, FAU Team, eMERGE 2026 Hackathon

Commands whose output is 100% predictable given our honeyfs profile.
No model, no cloud — O(1) dict lookup. Target: >60% of probes land here.

Imports system_facts so there is ONE source of truth. If you change the profile,
change system_facts.py and every tier updates.
"""
from __future__ import annotations
import re
import shlex
import time
from typing import Tuple

try:
    # Loaded inside Cowrie: system_facts lives in the sibling cowrie.llm package.
    from cowrie.llm.system_facts import (
        HOSTNAME, FQDN, OS_PRETTY, OS_CODENAME, OS_VERSION_ID, DEBIAN_VERSION,
        KERNEL_VERSION, KERNEL_BUILD, ARCH, PI_MODEL, PI_REVISION, PI_SERIAL,
        RAM_KB, SSH_BANNER, IFACE, IP_SELF, MAC_SELF, NETMASK, BROADCAST,
        IP_GATEWAY, MAC_GATEWAY, IP_NODE_BETA, MAC_NODE_BETA,
        IP_NODE_GAMMA, MAC_NODE_GAMMA, IP_ADMIN, MAC_ADMIN,
        DOMAIN, DNS_PRIMARY, DNS_SECONDARY, USER_NAME, USER_HOME, USER_SHELL,
        UPTIME_SECONDS_AT_BAIT, TIMEZONE, MACHINE_ID, CPU_COUNT,
    )
except ImportError:
    # Standalone dev/testing — system_facts.py is a sibling file on sys.path.
    from system_facts import (
        HOSTNAME, FQDN, OS_PRETTY, OS_CODENAME, OS_VERSION_ID, DEBIAN_VERSION,
        KERNEL_VERSION, KERNEL_BUILD, ARCH, PI_MODEL, PI_REVISION, PI_SERIAL,
        RAM_KB, SSH_BANNER, IFACE, IP_SELF, MAC_SELF, NETMASK, BROADCAST,
        IP_GATEWAY, MAC_GATEWAY, IP_NODE_BETA, MAC_NODE_BETA,
        IP_NODE_GAMMA, MAC_NODE_GAMMA, IP_ADMIN, MAC_ADMIN,
        DOMAIN, DNS_PRIMARY, DNS_SECONDARY, USER_NAME, USER_HOME, USER_SHELL,
        UPTIME_SECONDS_AT_BAIT, TIMEZONE, MACHINE_ID, CPU_COUNT,
    )

# ==============================================================================
# Runtime identity — what the running system reports (differs from /etc/hostname).
# bait.sh writes "raspberrypi" to cowrie.cfg's hostname= (the prompt + hostname
# binary) but "pi-sensor-gateway" to honeyfs/etc/hostname. Real Linux behaves
# the same way if /etc/hostname is edited without running hostnamectl.
# ==============================================================================
COWRIE_HOSTNAME = "raspberrypi"
# SSH banner bait.sh sets in cowrie.cfg — Debian 11 / OpenSSH 8.4
COWRIE_SSH_BANNER = "SSH-2.0-OpenSSH_8.4p1 Debian-5+deb11u1"
# Unknown wlan client that appears in bait.sh's /proc/net/arp
IP_UNKNOWN_CLIENT = "10.4.27.28"
MAC_UNKNOWN_CLIENT = "f4:46:37:cb:66:b9"

# ==============================================================================
# Static table — every line composed from system_facts, so it can't drift.
# ==============================================================================

# --- Memory rendered in /proc/meminfo units ---
_MEM_TOTAL_KB = RAM_KB
_MEM_FREE_KB = int(RAM_KB * 0.953)
_MEM_AVAIL_KB = int(RAM_KB * 0.977)
_SWAP_TOTAL_KB = 2097136

def _kb_to_h(kb: int) -> str:
    if kb >= 1024 * 1024:
        return f"{kb / 1024 / 1024:.1f}G".replace(".0G", "G")
    if kb >= 1024:
        return f"{kb // 1024}M"
    return f"{kb}K"

# --- Fake "boot time" (epoch) used by `date`, `uptime`, `/proc/uptime` ---
_BOOT_EPOCH = time.time() - UPTIME_SECONDS_AT_BAIT

def _uptime_line() -> str:
    now = time.localtime()
    up = int(time.time() - _BOOT_EPOCH)
    days, rem = divmod(up, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    if days:
        updesc = f"{days} day{'s' if days != 1 else ''},  {hours:02d}:{mins:02d}"
    else:
        updesc = f"{hours:02d}:{mins:02d}"
    return (f" {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d} "
            f"up {updesc},  1 user,  load average: 0.12, 0.08, 0.05")

def _date_default() -> str:
    # `date` default format: "Thu Apr 23 14:23:01 EDT 2026"
    return time.strftime("%a %b %e %H:%M:%S %Z %Y", time.localtime())

def _date_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime())

def _date_epoch() -> str:
    return str(int(time.time()))

def _proc_uptime() -> str:
    up = time.time() - _BOOT_EPOCH
    idle = up * CPU_COUNT * 0.85
    return f"{up:.2f} {idle:.2f}"

# ==============================================================================
# The table. Keys are normalized (lowercased, collapsed whitespace).
# ==============================================================================

STATIC_RESPONSES = {
    # --- Identity & session ---
    "whoami": USER_NAME,
    "id": f"uid=0({USER_NAME}) gid=0({USER_NAME}) groups=0({USER_NAME})",
    "id -u": "0",
    "id -g": "0",
    "id -un": USER_NAME,
    "id -gn": USER_NAME,
    "id -nG": USER_NAME,
    "groups": USER_NAME,
    "pwd": USER_HOME,
    "tty": "/dev/pts/0",
    "users": USER_NAME,
    "logname": USER_NAME,

    # --- Host identity ---
    # Runtime `hostname` comes from cowrie.cfg (raspberrypi), but /etc/hostname
    # on disk says pi-sensor-gateway — mismatch is authentic to bait.sh state.
    "hostname": COWRIE_HOSTNAME,
    "hostname -s": COWRIE_HOSTNAME,
    "hostname -f": COWRIE_HOSTNAME,
    "hostname -d": "",
    "hostname -i": IP_SELF,
    "dnsdomainname": "",
    "domainname": "(none)",
    "cat /etc/hostname": HOSTNAME,
    "cat /etc/machine-id": MACHINE_ID,

    # --- Kernel / OS ---
    "uname": "Linux",
    "uname -s": "Linux",
    "uname -n": COWRIE_HOSTNAME,
    "uname -r": KERNEL_VERSION,
    "uname -m": ARCH,
    "uname -p": "unknown",
    "uname -i": "unknown",
    "uname -o": "GNU/Linux",
    "uname -v": "#1 SMP PREEMPT Debian 1:6.12.75-1+rpt1 (2026-03-11)",
    "uname -a": f"Linux {COWRIE_HOSTNAME} {KERNEL_VERSION} #1 SMP PREEMPT Debian 1:6.12.75-1+rpt1 (2026-03-11) {ARCH} GNU/Linux",
    "arch": ARCH,
    "cat /proc/version": KERNEL_BUILD,
    "cat /etc/debian_version": DEBIAN_VERSION,
    "cat /etc/os-release": (
        f'PRETTY_NAME="{OS_PRETTY}"\n'
        'NAME="Debian GNU/Linux"\n'
        f'VERSION_ID="{OS_VERSION_ID}"\n'
        f'VERSION="{OS_VERSION_ID} ({OS_CODENAME})"\n'
        f'VERSION_CODENAME={OS_CODENAME}\n'
        f'DEBIAN_VERSION_FULL={DEBIAN_VERSION}\n'
        'ID=debian\n'
        'HOME_URL="https://www.debian.org/"\n'
        'SUPPORT_URL="https://www.debian.org/support"\n'
        'BUG_REPORT_URL="https://bugs.debian.org/"'
    ),
    "lsb_release -a": (
        "No LSB modules are available.\n"
        "Distributor ID: Debian\n"
        f"Description:    {OS_PRETTY}\n"
        f"Release:        {OS_VERSION_ID}\n"
        f"Codename:       {OS_CODENAME}"
    ),
    "lsb_release -i": "Distributor ID: Debian",
    "lsb_release -r": f"Release:        {OS_VERSION_ID}",
    "lsb_release -c": f"Codename:       {OS_CODENAME}",
    "lsb_release -d": f"Description:    {OS_PRETTY}",

    # --- Timezone ---
    "cat /etc/timezone": TIMEZONE,
    "timedatectl": (
        "               Local time: " + _date_default() + "\n"
        f"           Universal time: {time.strftime('%a %Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
        f"                 RTC time: {time.strftime('%a %Y-%m-%d %H:%M:%S', time.gmtime())}\n"
        f"                Time zone: {TIMEZONE} (EDT, -0400)\n"
        "System clock synchronized: yes\n"
        "              NTP service: active\n"
        "          RTC in local TZ: no"
    ),

    # --- Memory / swap ---
    "free": (
        "              total        used        free      shared  buff/cache   available\n"
        f"Mem:        {_MEM_TOTAL_KB:>8}     {_MEM_TOTAL_KB-_MEM_AVAIL_KB:>7}      {_MEM_FREE_KB:>6}       45892     {_MEM_AVAIL_KB-_MEM_FREE_KB:>7}     {_MEM_AVAIL_KB:>7}\n"
        f"Swap:        {_SWAP_TOTAL_KB:>6}           0      {_SWAP_TOTAL_KB:>6}"
    ),
    "free -m": (
        "              total        used        free      shared  buff/cache   available\n"
        f"Mem:          {_MEM_TOTAL_KB//1024:>5}         380       {_MEM_FREE_KB//1024:>5}          44         380       {_MEM_AVAIL_KB//1024:>5}\n"
        f"Swap:          {_SWAP_TOTAL_KB//1024:>4}           0        {_SWAP_TOTAL_KB//1024:>4}"
    ),
    "free -h": (
        "              total        used        free      shared  buff/cache   available\n"
        f"Mem:           {_kb_to_h(_MEM_TOTAL_KB)}        380M        {_kb_to_h(_MEM_FREE_KB)}         44M        380M        {_kb_to_h(_MEM_AVAIL_KB)}\n"
        f"Swap:           {_kb_to_h(_SWAP_TOTAL_KB)}          0B         {_kb_to_h(_SWAP_TOTAL_KB)}"
    ),

    # --- Disk ---
    "df": (
        "Filesystem     1K-blocks    Used Available Use% Mounted on\n"
        "udev             8186432       0   8186432   0% /dev\n"
        "tmpfs            1660820    1832   1658988   1% /run\n"
        "/dev/mmcblk0p2  30703044 4823456  24234456  17% /\n"
        "tmpfs            8304092       0   8304092   0% /dev/shm\n"
        "tmpfs               5120       0      5120   0% /run/lock\n"
        "/dev/mmcblk0p1    258095   49024    209071  19% /boot/firmware\n"
        "tmpfs            2097152      24   2097128   1% /tmp\n"
        "tmpfs             332164     100    332064   1% /run/user/1000"
    ),
    "df -h": (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "udev            7.8G     0  7.8G   0% /dev\n"
        "tmpfs           1.6G  1.8M  1.6G   1% /run\n"
        "/dev/mmcblk0p2   30G  4.6G   23G  17% /\n"
        "tmpfs           7.9G     0  7.9G   0% /dev/shm\n"
        "tmpfs           5.0M     0  5.0M   0% /run/lock\n"
        "/dev/mmcblk0p1  253M   48M  205M  19% /boot/firmware\n"
        "tmpfs           2.0G   24K  2.0G   1% /tmp\n"
        "tmpfs           325M  100K  324M   1% /run/user/1000"
    ),
    "df -i": (
        "Filesystem      Inodes  IUsed   IFree IUse% Mounted on\n"
        "udev           2046608    640 2045968    1% /dev\n"
        "/dev/mmcblk0p2 1945600 152423 1793177    8% /\n"
        "/dev/mmcblk0p1       0      0       0     - /boot/firmware\n"
        "tmpfs           415205     41  415164    1% /run"
    ),

    # --- Network ---
    "ifconfig": (
        f"{IFACE}: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500\n"
        f"        inet {IP_SELF}  netmask {NETMASK}  broadcast {BROADCAST}\n"
        "        inet6 fe80::da3a:ddff:fea1:b2c3  prefixlen 64  scopeid 0x20<link>\n"
        f"        ether {MAC_SELF}  txqueuelen 1000  (Ethernet)\n"
        "        RX packets 45231  bytes 2847293912 (2.6 GiB)\n"
        "        RX errors 0  dropped 0  overruns 0  frame 0\n"
        "        TX packets 31982  bytes 1204857293 (1.1 GiB)\n"
        "        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0\n\n"
        "lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536\n"
        "        inet 127.0.0.1  netmask 255.0.0.0\n"
        "        inet6 ::1  prefixlen 128  scopeid 0x10<host>\n"
        "        loop  txqueuelen 1000  (Local Loopback)\n"
        "        RX packets 1024  bytes 1048576 (1.0 MiB)\n"
        "        TX packets 1024  bytes 1048576 (1.0 MiB)"
    ),
    f"ifconfig {IFACE}": (
        f"{IFACE}: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500\n"
        f"        inet {IP_SELF}  netmask {NETMASK}  broadcast {BROADCAST}\n"
        f"        ether {MAC_SELF}  txqueuelen 1000  (Ethernet)"
    ),
    "ifconfig lo": (
        "lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536\n"
        "        inet 127.0.0.1  netmask 255.0.0.0\n"
        "        loop  txqueuelen 1000  (Local Loopback)"
    ),
    "ip a": (
        "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000\n"
        "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00\n"
        "    inet 127.0.0.1/8 scope host lo\n"
        "       valid_lft forever preferred_lft forever\n"
        "    inet6 ::1/128 scope host\n"
        "       valid_lft forever preferred_lft forever\n"
        f"2: {IFACE}: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000\n"
        f"    link/ether {MAC_SELF} brd ff:ff:ff:ff:ff:ff\n"
        f"    inet {IP_SELF}/24 brd {BROADCAST} scope global {IFACE}\n"
        "       valid_lft forever preferred_lft forever\n"
        f"    inet6 fe80::da3a:ddff:fea1:b2c3/64 scope link\n"
        "       valid_lft forever preferred_lft forever"
    ),
    "ip addr": None,     # filled below = same as ip a
    "ip addr show": None,
    "ip link": (
        "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000\n"
        "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00\n"
        f"2: {IFACE}: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP mode DEFAULT group default qlen 1000\n"
        f"    link/ether {MAC_SELF} brd ff:ff:ff:ff:ff:ff"
    ),
    "ip route": (
        f"default via {IP_GATEWAY} dev {IFACE} proto dhcp metric 600\n"
        f"10.4.27.0/24 dev {IFACE} proto kernel scope link src {IP_SELF} metric 600"
    ),
    "ip route show": None,
    "ip r": None,
    # Neighbor table matches bait.sh /proc/net/arp — only 3 entries; node-beta
    # and node-gamma are NOT in the live cache, so arp must not advertise them.
    "ip neigh": (
        f"{IP_ADMIN} dev {IFACE} lladdr {MAC_ADMIN} REACHABLE\n"
        f"{IP_GATEWAY} dev {IFACE} lladdr {MAC_GATEWAY} REACHABLE\n"
        f"{IP_UNKNOWN_CLIENT} dev {IFACE} lladdr {MAC_UNKNOWN_CLIENT} STALE"
    ),
    "arp": (
        "Address                  HWtype  HWaddress           Flags Mask            Iface\n"
        f"{IP_ADMIN}               ether   {MAC_ADMIN}   C                     {IFACE}\n"
        f"{IP_GATEWAY}                ether   {MAC_GATEWAY}   C                     {IFACE}\n"
        f"{IP_UNKNOWN_CLIENT}               ether   {MAC_UNKNOWN_CLIENT}   C                     {IFACE}"
    ),
    "arp -a": (
        f"? ({IP_ADMIN}) at {MAC_ADMIN} [ether] on {IFACE}\n"
        f"_gateway ({IP_GATEWAY}) at {MAC_GATEWAY} [ether] on {IFACE}\n"
        f"? ({IP_UNKNOWN_CLIENT}) at {MAC_UNKNOWN_CLIENT} [ether] on {IFACE}"
    ),
    "arp -n": (
        "Address                  HWtype  HWaddress           Flags Mask            Iface\n"
        f"{IP_ADMIN}               ether   {MAC_ADMIN}   C                     {IFACE}\n"
        f"{IP_GATEWAY}                ether   {MAC_GATEWAY}   C                     {IFACE}\n"
        f"{IP_UNKNOWN_CLIENT}               ether   {MAC_UNKNOWN_CLIENT}   C                     {IFACE}"
    ),
    "netstat -i": (
        "Kernel Interface table\n"
        "Iface      MTU    RX-OK RX-ERR RX-DRP RX-OVR    TX-OK TX-ERR TX-DRP TX-OVR Flg\n"
        f"{IFACE:<8} 1500    45231      0      0 0         31982      0      0      0 BMRU\n"
        "lo       65536     1024      0      0 0          1024      0      0      0 LRU"
    ),
    "netstat -rn": (
        "Kernel IP routing table\n"
        "Destination     Gateway         Genmask         Flags   MSS Window  irtt Iface\n"
        f"0.0.0.0         {IP_GATEWAY}      0.0.0.0         UG        0 0          0 {IFACE}\n"
        f"10.4.27.0       0.0.0.0         255.255.255.0   U         0 0          0 {IFACE}"
    ),
    "cat /etc/resolv.conf": (
        "# Generated by NetworkManager\n"
        f"search {DOMAIN}\n"
        f"nameserver {DNS_PRIMARY}\n"
        f"nameserver {DNS_SECONDARY}"
    ),

    # --- Users & Auth files (cat /etc/passwd, /etc/group already in honeyfs) ---
    # Mirrors bait.sh honeyfs/etc/hosts exactly — no extra node entries.
    "cat /etc/hosts": (
        "# Your system has configured 'manage_etc_hosts' as True.\n"
        "# As a result, if you wish for changes to this file to persist\n"
        "# then you will need to either\n"
        "# a.) make changes to the master file in /etc/cloud/templates/hosts.debian.tmpl\n"
        "# b.) change or remove the value of 'manage_etc_hosts' in\n"
        "#     /etc/cloud/cloud.cfg or cloud-config from user-data\n"
        "#\n"
        f"127.0.1.1 {COWRIE_HOSTNAME} {COWRIE_HOSTNAME}\n"
        "127.0.0.1 localhost\n\n"
        "# The following lines are desirable for IPv6 capable hosts\n"
        "::1 localhost ip6-localhost ip6-loopback\n"
        "ff02::1 ip6-allnodes\n"
        "ff02::2 ip6-allrouters"
    ),

    # --- Environment ---
    "env": (
        f"SHELL={USER_SHELL}\n"
        f"PWD={USER_HOME}\n"
        f"LOGNAME={USER_NAME}\n"
        f"HOME={USER_HOME}\n"
        "LANG=en_US.UTF-8\n"
        f"USER={USER_NAME}\n"
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
        "TERM=xterm-256color\n"
        "SSH_CONNECTION=10.4.27.28 49234 10.4.27.20 22\n"
        "SSH_CLIENT=10.4.27.28 49234 22\n"
        "SSH_TTY=/dev/pts/0\n"
        "MAIL=/var/mail/root\n"
        "_=/usr/bin/env"
    ),
    "printenv": None,    # filled = env
    "printenv SHELL": USER_SHELL,
    "printenv HOME": USER_HOME,
    "printenv USER": USER_NAME,
    "printenv PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "printenv PWD": USER_HOME,
    "printenv LANG": "en_US.UTF-8",
    "printenv TERM": "xterm-256color",

    # --- Crontab ---
    "crontab -l": (
        "no crontab for root"
    ),
    # Exact copy of bait.sh honeyfs/etc/crontab — note the 10.1.10.55 admin
    # target is intentional (lateral-movement bait, on the old subnet).
    "cat /etc/crontab": (
        "SHELL=/bin/sh\n"
        "PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin\n\n"
        "# m h dom mon dow user  command\n"
        "17 *    * * *   root    cd / && run-parts --report /etc/cron.hourly\n"
        "25 6    * * *   root    test -x /usr/sbin/anacron || ( cd / && run-parts --report /etc/cron.daily )\n"
        "*/5 *   * * *   pi      /opt/sensor/collect.sh >> /var/log/sensor.log 2>&1\n"
        "0   2   * * *   root    /usr/local/bin/db_backup.sh\n"
        "30  3   * * *   root    rsync -az /var/sensor-data/ admin@10.1.10.55:/backup/node-alpha/"
    ),

    # --- /proc/net/arp (file) --- exact copy of bait.sh honeyfs/proc/net/arp
    "cat /proc/net/arp": (
        "IP address       HW type     Flags       HW address            Mask     Device\n"
        f"{IP_ADMIN}       0x1         0x2         {MAC_ADMIN}     *        {IFACE}\n"
        f"{IP_GATEWAY}        0x1         0x2         {MAC_GATEWAY}     *        {IFACE}\n"
        f"{IP_UNKNOWN_CLIENT}       0x1         0x2         {MAC_UNKNOWN_CLIENT}     *        {IFACE}"
    ),
    "cat /proc/loadavg": "0.12 0.08 0.05 1/234 9823",

    # ==========================================================================
    # File reads — exact copies of bait.sh honeyfs content. These MUST match
    # what bait.sh writes to disk, otherwise Tier 1 and Cowrie's honeyfs serve
    # different content for the same path.
    # ==========================================================================

    "cat /etc/passwd": (
        "root:x:0:0:root:/root:/bin/bash\n"
        "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n"
        "bin:x:2:2:bin:/bin:/usr/sbin/nologin\n"
        "sys:x:3:3:sys:/dev:/usr/sbin/nologin\n"
        "sync:x:4:65534:sync:/bin:/bin/sync\n"
        "www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin\n"
        "pi:x:1000:1000:,,,:/home/pi:/bin/bash\n"
        "webadmin:x:1001:1001:,,,:/home/webadmin:/bin/bash\n"
        "mysql:x:1002:1002:MySQL Server,,,:/nonexistent:/bin/false"
    ),

    "cat /etc/shadow": (
        "root:$6$rounds=656000$rAnDoMsAlT123$fakehashedpassword123456789abcdef:19200:0:99999:7:::\n"
        "pi:$6$rounds=656000$aNothErSaLt456$fakehashedpassword987654321zyxwvu:19200:0:99999:7:::\n"
        "webadmin:$6$rounds=656000$yEtAnOtHeR789$fakehashedpasswordabcdef123456789:19200:0:99999:7:::"
    ),

    "cat /etc/motd": (
        "\n"
        "====================================================================\n"
        "WARNING: UNAUTHORIZED ACCESS PROHIBITED\n"
        "Property of Distributed Sensor Network - Node Alpha\n"
        "All connections are monitored and recorded.\n"
        "===================================================================="
    ),

    "cat /etc/cron.d/sensor-sync": (
        "# Sensor network sync - DO NOT REMOVE\n"
        "*/10 * * * * root /opt/sensor/sync_nodes.sh 2>/dev/null\n"
        "0 4 * * * root scp -i /root/.ssh/id_rsa /var/www/html/config.php webadmin@10.1.10.55:/tmp/cfg_backup"
    ),

    "cat /proc/cpuinfo": (
        "processor\t: 0\n"
        "BogoMIPS\t: 108.00\n"
        "Features\t: fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp asimdhp cpuid asimdrdm lrcpc dcpop asimddp\n"
        "CPU implementer\t: 0x41\n"
        "CPU architecture: 8\n"
        "CPU variant\t: 0x4\n"
        "CPU part\t: 0xd0b\n"
        "CPU revision\t: 1\n\n"
        "processor\t: 1\n"
        "BogoMIPS\t: 108.00\n"
        "Features\t: fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp asimdhp cpuid asimdrdm lrcpc dcpop asimddp\n"
        "CPU implementer\t: 0x41\n"
        "CPU architecture: 8\n"
        "CPU variant\t: 0x4\n"
        "CPU part\t: 0xd0b\n"
        "CPU revision\t: 1\n\n"
        "processor\t: 2\n"
        "BogoMIPS\t: 108.00\n"
        "Features\t: fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp asimdhp cpuid asimdrdm lrcpc dcpop asimddp\n"
        "CPU implementer\t: 0x41\n"
        "CPU architecture: 8\n"
        "CPU variant\t: 0x4\n"
        "CPU part\t: 0xd0b\n"
        "CPU revision\t: 1\n\n"
        "processor\t: 3\n"
        "BogoMIPS\t: 108.00\n"
        "Features\t: fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp asimdhp cpuid asimdrdm lrcpc dcpop asimddp\n"
        "CPU implementer\t: 0x41\n"
        "CPU architecture: 8\n"
        "CPU variant\t: 0x4\n"
        "CPU part\t: 0xd0b\n"
        "CPU revision\t: 1\n\n"
        f"Revision\t: {PI_REVISION}\n"
        f"Serial\t\t: {PI_SERIAL}\n"
        f"Model\t\t: {PI_MODEL}"
    ),

    "cat /proc/meminfo": (
        f"MemTotal:       {_MEM_TOTAL_KB} kB\n"
        f"MemFree:        {_MEM_FREE_KB} kB\n"
        f"MemAvailable:   {_MEM_AVAIL_KB} kB\n"
        "Buffers:           38560 kB\n"
        "Cached:           432464 kB\n"
        "SwapCached:            0 kB\n"
        "Active:           248528 kB\n"
        "Inactive:         286448 kB\n"
        "Active(anon):      76816 kB\n"
        "Inactive(anon):        0 kB\n"
        "Active(file):     171712 kB\n"
        "Inactive(file):   286448 kB\n"
        "Unevictable:           0 kB\n"
        "Mlocked:               0 kB\n"
        f"SwapTotal:       {_SWAP_TOTAL_KB} kB\n"
        f"SwapFree:        {_SWAP_TOTAL_KB} kB\n"
        "Zswap:                 0 kB\n"
        "Zswapped:              0 kB\n"
        "Dirty:                 0 kB\n"
        "Writeback:             0 kB\n"
        "AnonPages:         64144 kB\n"
        "Mapped:            44528 kB\n"
        "Shmem:             13152 kB\n"
        "KReclaimable:      36640 kB\n"
        "Slab:              80288 kB\n"
        "SReclaimable:      36640 kB\n"
        "SUnreclaim:        43648 kB\n"
        "KernelStack:        2912 kB\n"
        "PageTables:         3808 kB\n"
        "SecPageTables:       128 kB\n"
        "NFS_Unstable:          0 kB\n"
        "Bounce:                0 kB\n"
        "WritebackTmp:          0 kB\n"
        "CommitLimit:    10401232 kB\n"
        "Committed_AS:     137344 kB\n"
        "VmallocTotal:   68447887360 kB\n"
        "VmallocUsed:       65904 kB\n"
        "VmallocChunk:          0 kB\n"
        "Percpu:             1344 kB\n"
        "CmaTotal:          65536 kB\n"
        "CmaFree:           55296 kB"
    ),

    "cat /var/www/html/config.php": (
        "<?php\n"
        "// Auto-generated by Ansible\n"
        "define('DB_SERVER', 'localhost');\n"
        "define('DB_USERNAME', 'root');\n"
        "define('DB_PASSWORD', 'FAU_cyber_db_admin_99!');\n"
        "define('DB_NAME', 'sensor_data_metrics');\n"
        "?>"
    ),

    "cat /root/.bash_history": (
        "ping 8.8.8.8\n"
        "apt update && apt upgrade -y\n"
        "nano /var/www/html/config.php\n"
        "systemctl restart mariadb\n"
        "systemctl status apache2\n"
        "ssh admin@10.1.10.55\n"
        "ssh -i /root/.ssh/id_rsa webadmin@10.1.10.21\n"
        "rsync -az /var/sensor-data/ admin@10.1.10.55:/backup/\n"
        "cat /etc/passwd\n"
        "crontab -l\n"
        "mysql -u root -pFAU_cyber_db_admin_99! sensor_data_metrics\n"
        "exit"
    ),

    "cat /home/pi/.bash_history": (
        "ls -la\n"
        "cd /var/www/html\n"
        "cat config.php\n"
        "python3 collect.py\n"
        "sudo systemctl status sensor\n"
        "ping 10.1.10.1\n"
        "exit"
    ),

    "cat /root/.aws/credentials": (
        "[default]\n"
        "aws_access_key_id = AKIAQX3LM7NP2RSTVW84\n"
        "aws_secret_access_key = Jx7vK2mPqR9nL4wT6yB3hF8cZ1dA5eG0iUoYsNj\n"
        "region = us-east-1"
    ),

    "cat /root/.aws/config": (
        "[default]\n"
        "region = us-east-1\n"
        "output = json"
    ),

    "cat /root/.ssh/known_hosts": (
        "10.1.10.21 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC2vX fake_key_node_beta==\n"
        "10.1.10.22 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD3wY fake_key_node_gamma==\n"
        "10.1.10.55 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQE4xZ fake_key_admin=="
    ),

    "cat /var/log/auth.log": (
        "Apr 20 03:12:45 pi-sensor-gateway sshd[1234]: Accepted publickey for pi from 10.1.10.55 port 51234 ssh2\n"
        "Apr 20 03:12:46 pi-sensor-gateway sshd[1234]: pam_unix(sshd:session): session opened for user pi\n"
        "Apr 20 03:18:22 pi-sensor-gateway sshd[1234]: pam_unix(sshd:session): session closed for user pi\n"
        "Apr 21 02:00:01 pi-sensor-gateway cron[892]: (root) CMD (/usr/local/bin/db_backup.sh)\n"
        "Apr 22 03:15:01 pi-sensor-gateway sshd[2891]: Accepted publickey for root from 10.1.10.1 port 49823 ssh2\n"
        "Apr 22 03:22:17 pi-sensor-gateway sshd[2891]: pam_unix(sshd:session): session closed for user root"
    ),

    # ==========================================================================
    # SSH — server & client config, host keys, user keys (private key is bait)
    # ==========================================================================

    "cat /etc/ssh/sshd_config": (
        "# $OpenBSD: sshd_config,v 1.104 2021/07/02 05:11:21 dtucker Exp $\n\n"
        "# This is the sshd server system-wide configuration file.  See\n"
        "# sshd_config(5) for more information.\n\n"
        "# This sshd was compiled with PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n\n"
        "Include /etc/ssh/sshd_config.d/*.conf\n\n"
        "#Port 22\n"
        "#AddressFamily any\n"
        "#ListenAddress 0.0.0.0\n"
        "#ListenAddress ::\n\n"
        "#HostKey /etc/ssh/ssh_host_rsa_key\n"
        "#HostKey /etc/ssh/ssh_host_ecdsa_key\n"
        "#HostKey /etc/ssh/ssh_host_ed25519_key\n\n"
        "#LoginGraceTime 2m\n"
        "PermitRootLogin yes\n"
        "#StrictModes yes\n"
        "#MaxAuthTries 6\n"
        "#MaxSessions 10\n\n"
        "PubkeyAuthentication yes\n"
        "PasswordAuthentication yes\n"
        "PermitEmptyPasswords no\n\n"
        "ChallengeResponseAuthentication no\n"
        "KbdInteractiveAuthentication no\n\n"
        "UsePAM yes\n\n"
        "X11Forwarding yes\n"
        "PrintMotd no\n"
        "AcceptEnv LANG LC_*\n"
        "Subsystem\tsftp\t/usr/lib/openssh/sftp-server"
    ),

    "cat /etc/ssh/ssh_config": (
        "# This is the ssh client system-wide configuration file.  See\n"
        "# ssh_config(5) for more information.\n\n"
        "Include /etc/ssh/ssh_config.d/*.conf\n\n"
        "Host *\n"
        "#   ForwardAgent no\n"
        "#   ForwardX11 no\n"
        "#   PasswordAuthentication yes\n"
        "#   HostbasedAuthentication no\n"
        "#   IdentityFile ~/.ssh/id_rsa\n"
        "#   IdentityFile ~/.ssh/id_ecdsa\n"
        "#   IdentityFile ~/.ssh/id_ed25519\n"
        "#   Port 22\n"
        "    SendEnv LANG LC_*\n"
        "    HashKnownHosts yes\n"
        "    GSSAPIAuthentication yes"
    ),

    "cat /etc/ssh/ssh_host_rsa_key.pub": (
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDZ7f8k2vH3pT5cX9nQ2wR4sM6vB1aL"
        "x8KjF7yW3mE5nT2pQ4cV9uL0xJ5kR6sY1bN3mC8hF2dA7gU4eK9pO6tW0iE3qJ5zX4vB7nM1"
        " root@pi-sensor-gateway"
    ),

    "cat /etc/ssh/ssh_host_ed25519_key.pub": (
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKx8W4nR7mQ2pT3cH9vX6zB5uL1aK8jF4sM2yE3wN7rQ"
        " root@pi-sensor-gateway"
    ),

    "cat /etc/ssh/ssh_host_ecdsa_key.pub": (
        "ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBKj7vN2m"
        "Q4cX8hR5pT6wL9yB1fA3eK7sM4nU2iH6zJ8dG0uV5tE3yW7pC9qN1bO4xR6mD8jS5vK2hL9aT"
        " root@pi-sensor-gateway"
    ),

    "cat /root/.ssh/authorized_keys": (
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCk9vX2mT4cR7pH5sN3bY8wQ1uL6jF"
        "2aK4eM8dS7gV0xJ6yW5pC3qN9iO1rT2hB4vU7kL0xE5sD8fG3mR9aP2cW6tY4zI1qN7"
        " ansible@deploy-01\n"
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM4nP2wR7vK9sT3cH6xB1uL8jF4eK5yQ2mE3aN7rT9dW"
        " admin@10.1.10.55"
    ),

    "cat /root/.ssh/id_rsa.pub": (
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC2vX9nM4cR7pT5sH3bY8wQ1uL6jF2"
        "aK4eM8dS7gV0xJ6yW5pC3qN9iO1rT2hB4vU7kL0xE5sD8fG3mR9aP2cW6tY4zI1qN7"
        "mK8vB3dH5nQ9oL4pX2wR6sT7fC1yE5uJ8aN0zI3qM4kG7hD2bV9cS6tW8oR1pL3nF5yX2"
        " root@pi-sensor-gateway"
    ),

    # Attackers ALWAYS cat this — prime lateral-movement bait. Real-looking
    # RSA PEM structure but the key material is garbage.
    "cat /root/.ssh/id_rsa": (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABlwAAAAdzc2gt\n"
        "cnNhAAAAAwEAAQAAAYEAtvX9nM4cR7pT5sH3bY8wQ1uL6jF2aK4eM8dS7gV0xJ6yW5pC\n"
        "3qN9iO1rT2hB4vU7kL0xE5sD8fG3mR9aP2cW6tY4zI1qN7mK8vB3dH5nQ9oL4pX2wR6s\n"
        "T7fC1yE5uJ8aN0zI3qM4kG7hD2bV9cS6tW8oR1pL3nF5yX2dK9pT7mW4cL2bV5xR8fQ3\n"
        "nH6zJ1sK8vE4pU2wR7mL0xB5tC3yG9aN6qI4oD1eF8hS2jP5cV0kM7nT6uW3yL9rX1dB\n"
        "H4sE7pC2fA5oI8mR3qN1vT6wY0zK9gJ4xU2bL7cD5hV8nM3pR1tE6sK9yF2aO4wQ7iU0\n"
        "XzNpLmB8cR2kT4sV7xW5eJ1aH9dG3mF6pQ2uI4yN0oZ7vC8bE5rT1sK3hL6wM2fP9dJ7\n"
        "AAAAwQDJm2H8nK5pT4cR9sN3bY7wQ1uL6jF2aK4eM8dS7gV0xJ6yW5pC3qN9iO1rT2hB\n"
        "4vU7kL0xE5sD8fG3mR9aP2cW6tY4zI1qN7mK8vB3dH5nQ9oL4pX2wR6sT7fC1yE5uJ8a\n"
        "-----END OPENSSH PRIVATE KEY-----"
    ),

    "cat /home/pi/.ssh/authorized_keys": (
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDmK2nP8vR4cT7sL9xH3bY1wQ5uN6jF"
        "4aE2kM0dS9gV7xJ8yW3pC5qN1iO6rT2hB9vU4kL7xE3sD0fG8mR5aP6cW2tY9zI4qN1"
        " pi@workstation"
    ),

    # ==========================================================================
    # Dotfiles — root and pi
    # ==========================================================================

    "cat /root/.bashrc": (
        "# ~/.bashrc: executed by bash(1) for non-login shells.\n\n"
        "# Note: PS1 and umask are already set in /etc/profile. You should not\n"
        "# need this unless you want different defaults for root.\n"
        "# PS1='${debian_chroot:+($debian_chroot)}\\h:\\w\\$ '\n"
        "# umask 022\n\n"
        "# You may uncomment the following lines if you want `ls' to be colorized:\n"
        "export LS_OPTIONS='--color=auto'\n"
        "eval \"$(dircolors)\"\n"
        "alias ls='ls $LS_OPTIONS'\n"
        "alias ll='ls $LS_OPTIONS -l'\n"
        "alias l='ls $LS_OPTIONS -lA'\n\n"
        "# Some more alias to avoid making mistakes:\n"
        "alias rm='rm -i'\n"
        "alias cp='cp -i'\n"
        "alias mv='mv -i'"
    ),

    "cat /root/.profile": (
        "# ~/.profile: executed by Bourne-compatible login shells.\n\n"
        "if [ \"$BASH\" ]; then\n"
        "  if [ -f ~/.bashrc ]; then\n"
        "    . ~/.bashrc\n"
        "  fi\n"
        "fi\n\n"
        "mesg n 2> /dev/null || true"
    ),

    "cat /home/pi/.bashrc": (
        "# ~/.bashrc: executed by bash(1) for non-login shells.\n"
        "# see /usr/share/doc/bash/examples/startup-files (in the package bash-doc)\n"
        "# for examples\n\n"
        "case $- in\n"
        "    *i*) ;;\n"
        "      *) return;;\n"
        "esac\n\n"
        "HISTCONTROL=ignoreboth\n"
        "HISTSIZE=1000\n"
        "HISTFILESIZE=2000\n\n"
        "shopt -s checkwinsize\n\n"
        "if [ -x /usr/bin/dircolors ]; then\n"
        "    test -r ~/.dircolors && eval \"$(dircolors -b ~/.dircolors)\" || eval \"$(dircolors -b)\"\n"
        "    alias ls='ls --color=auto'\n"
        "    alias grep='grep --color=auto'\n"
        "fi\n\n"
        "alias ll='ls -alF'\n"
        "alias la='ls -A'\n"
        "alias l='ls -CF'"
    ),

    "cat /home/pi/.profile": (
        "# ~/.profile: executed by the command interpreter for login shells.\n\n"
        "if [ -n \"$BASH_VERSION\" ]; then\n"
        "    if [ -f \"$HOME/.bashrc\" ]; then\n"
        "\t. \"$HOME/.bashrc\"\n"
        "    fi\n"
        "fi\n\n"
        "if [ -d \"$HOME/bin\" ] ; then\n"
        "    PATH=\"$HOME/bin:$PATH\"\n"
        "fi\n\n"
        "if [ -d \"$HOME/.local/bin\" ] ; then\n"
        "    PATH=\"$HOME/.local/bin:$PATH\"\n"
        "fi"
    ),

    "cat /etc/bash.bashrc": (
        "# System-wide .bashrc file for interactive bash(1) shells.\n\n"
        "# To enable the settings / commands in this file for login shells as well,\n"
        "# this file has to be sourced in /etc/profile.\n\n"
        "# If not running interactively, don't do anything\n"
        "[ -z \"$PS1\" ] && return\n\n"
        "# check the window size after each command and, if necessary,\n"
        "# update the values of LINES and COLUMNS.\n"
        "shopt -s checkwinsize\n\n"
        "# set a fancy prompt (non-color, overwrite the one in /etc/profile)\n"
        "PS1='${debian_chroot:+($debian_chroot)}\\u@\\h:\\w\\$ '"
    ),

    "cat /etc/profile": (
        "# /etc/profile: system-wide .profile file for the Bourne shell (sh(1))\n"
        "# and Bourne compatible shells (bash(1), ksh(1), ash(1), ...).\n\n"
        "if [ \"$(id -u)\" -eq 0 ]; then\n"
        "  PATH=\"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\"\n"
        "else\n"
        "  PATH=\"/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games\"\n"
        "fi\n"
        "export PATH\n\n"
        "if [ \"${PS1-}\" ]; then\n"
        "  if [ \"${BASH-}\" ] && [ \"$BASH\" != \"/bin/sh\" ]; then\n"
        "    if [ -f /etc/bash.bashrc ]; then\n"
        "      . /etc/bash.bashrc\n"
        "    fi\n"
        "  else\n"
        "    if [ \"$(id -u)\" -eq 0 ]; then\n"
        "      PS1='# '\n"
        "    else\n"
        "      PS1='$ '\n"
        "    fi\n"
        "  fi\n"
        "fi\n\n"
        "if [ -d /etc/profile.d ]; then\n"
        "  for i in /etc/profile.d/*.sh; do\n"
        "    if [ -r $i ]; then\n"
        "      . $i\n"
        "    fi\n"
        "  done\n"
        "  unset i\n"
        "fi"
    ),

    # ==========================================================================
    # Core /etc system files
    # ==========================================================================

    "cat /etc/group": (
        "root:x:0:\n"
        "daemon:x:1:\n"
        "bin:x:2:\n"
        "sys:x:3:\n"
        "adm:x:4:pi\n"
        "tty:x:5:\n"
        "disk:x:6:\n"
        "lp:x:7:\n"
        "mail:x:8:\n"
        "news:x:9:\n"
        "uucp:x:10:\n"
        "man:x:12:\n"
        "proxy:x:13:\n"
        "kmem:x:15:\n"
        "dialout:x:20:pi\n"
        "fax:x:21:\n"
        "voice:x:22:\n"
        "cdrom:x:24:pi\n"
        "floppy:x:25:pi\n"
        "tape:x:26:\n"
        "sudo:x:27:pi,webadmin\n"
        "audio:x:29:pi\n"
        "dip:x:30:pi\n"
        "www-data:x:33:\n"
        "backup:x:34:\n"
        "operator:x:37:\n"
        "list:x:38:\n"
        "irc:x:39:\n"
        "src:x:40:\n"
        "gnats:x:41:\n"
        "shadow:x:42:\n"
        "utmp:x:43:\n"
        "video:x:44:pi\n"
        "sasl:x:45:\n"
        "plugdev:x:46:pi\n"
        "staff:x:50:\n"
        "games:x:60:\n"
        "users:x:100:\n"
        "nogroup:x:65534:\n"
        "pi:x:1000:\n"
        "webadmin:x:1001:\n"
        "mysql:x:1002:"
    ),

    "cat /etc/fstab": (
        "# /etc/fstab: static file system information.\n"
        "#\n"
        "# Use 'blkid' to print the universally unique identifier for a device; this\n"
        "# may be used with UUID= as a more robust way to name devices that works even\n"
        "# if disks are added and removed. See fstab(5).\n"
        "#\n"
        "# <file system> <mount point>   <type>  <options>       <dump>  <pass>\n"
        "proc            /proc           proc    defaults          0       0\n"
        "PARTUUID=738a4d67-01  /boot/firmware  vfat    defaults          0       2\n"
        "PARTUUID=738a4d67-02  /               ext4    defaults,noatime  0       1\n"
        "# a swapfile is not a swap partition, no line here\n"
        "#   use  dphys-swapfile swap[on|off]  for that"
    ),

    "cat /etc/issue": (
        f"{OS_PRETTY} \\n \\l\n"
    ),

    "cat /etc/issue.net": (
        f"{OS_PRETTY}\n"
    ),

    "cat /etc/shells": (
        "# /etc/shells: valid login shells\n"
        "/bin/sh\n"
        "/usr/bin/sh\n"
        "/bin/bash\n"
        "/usr/bin/bash\n"
        "/bin/rbash\n"
        "/usr/bin/rbash\n"
        "/usr/bin/dash\n"
        "/bin/dash"
    ),

    "cat /etc/sudoers": (
        "#\n"
        "# This file MUST be edited with the 'visudo' command as root.\n"
        "#\n"
        "# Please consider adding local content in /etc/sudoers.d/ instead of\n"
        "# directly modifying this file.\n"
        "#\n"
        "# See the man page for details on how to write a sudoers file.\n"
        "#\n"
        "Defaults\tenv_reset\n"
        "Defaults\tmail_badpass\n"
        "Defaults\tsecure_path=\"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\"\n\n"
        "# Host alias specification\n\n"
        "# User alias specification\n\n"
        "# Cmnd alias specification\n\n"
        "# User privilege specification\n"
        "root\tALL=(ALL:ALL) ALL\n\n"
        "# Allow members of group sudo to execute any command\n"
        "%sudo\tALL=(ALL:ALL) ALL\n\n"
        "# See sudoers(5) for more information on \"#include\" directives:\n\n"
        "@includedir /etc/sudoers.d"
    ),

    "cat /etc/nsswitch.conf": (
        "# /etc/nsswitch.conf\n"
        "#\n"
        "# Example configuration of GNU Name Service Switch functionality.\n"
        "# If you have the `glibc-doc-reference' and `info' packages installed, try:\n"
        "# `info libc \"Name Service Switch\"' for information about this file.\n\n"
        "passwd:         files systemd\n"
        "group:          files systemd\n"
        "shadow:         files\n"
        "gshadow:        files\n\n"
        "hosts:          files mdns4_minimal [NOTFOUND=return] dns\n"
        "networks:       files\n\n"
        "protocols:      db files\n"
        "services:       db files\n"
        "ethers:         db files\n"
        "rpc:            db files\n\n"
        "netgroup:       nis"
    ),

    "cat /etc/login.defs": (
        "# /etc/login.defs - Configuration control definitions for the login package.\n\n"
        "MAIL_DIR\t/var/mail\n"
        "FAILLOG_ENAB\t\tyes\n"
        "LOG_UNKFAIL_ENAB\tno\n"
        "LOG_OK_LOGINS\t\tno\n"
        "SYSLOG_SU_ENAB\t\tyes\n"
        "SYSLOG_SG_ENAB\t\tyes\n"
        "FTMP_FILE\t/var/log/btmp\n"
        "SU_NAME\t\tsu\n"
        "HUSHLOGIN_FILE\t.hushlogin\n"
        "ENV_SUPATH\tPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
        "ENV_PATH\tPATH=/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games\n"
        "TTYGROUP\ttty\n"
        "TTYPERM\t\t0600\n"
        "ERASECHAR\t0177\n"
        "KILLCHAR\t025\n"
        "UMASK\t\t022\n"
        "HOME_MODE\t0755\n"
        "PASS_MAX_DAYS\t99999\n"
        "PASS_MIN_DAYS\t0\n"
        "PASS_WARN_AGE\t7\n"
        "UID_MIN\t\t\t 1000\n"
        "UID_MAX\t\t\t60000\n"
        "SYS_UID_MIN\t\t  100\n"
        "SYS_UID_MAX\t\t  999\n"
        "GID_MIN\t\t\t 1000\n"
        "GID_MAX\t\t\t60000\n"
        "SYS_GID_MIN\t\t  100\n"
        "SYS_GID_MAX\t\t  999\n"
        "LOGIN_RETRIES\t\t5\n"
        "LOGIN_TIMEOUT\t\t60\n"
        "CHFN_RESTRICT\t\trwh\n"
        "DEFAULT_HOME\tyes\n"
        "USERGROUPS_ENAB yes\n"
        "ENCRYPT_METHOD YESCRYPT"
    ),

    "cat /etc/apt/sources.list": (
        "# deb cdrom:[Debian GNU/Linux 13 _Trixie_ - Official aarch64 NETINST]/ trixie main\n\n"
        "deb http://deb.debian.org/debian/ trixie main contrib non-free non-free-firmware\n"
        "deb-src http://deb.debian.org/debian/ trixie main contrib non-free non-free-firmware\n\n"
        "deb http://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware\n"
        "deb-src http://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware\n\n"
        "deb http://deb.debian.org/debian/ trixie-updates main contrib non-free non-free-firmware\n"
        "deb-src http://deb.debian.org/debian/ trixie-updates main contrib non-free non-free-firmware"
    ),

    "cat /etc/network/interfaces": (
        "# interfaces(5) file used by ifup(8) and ifdown(8)\n"
        "# Include files from /etc/network/interfaces.d:\n"
        "source /etc/network/interfaces.d/*\n\n"
        "# The loopback network interface\n"
        "auto lo\n"
        "iface lo inet loopback"
    ),

    "cat /etc/sysctl.conf": (
        "#\n"
        "# /etc/sysctl.conf - Configuration file for setting system variables\n"
        "# See /etc/sysctl.d/ for additional system variables.\n"
        "# See sysctl.conf (5) for information.\n"
        "#\n\n"
        "#kernel.domainname = example.com\n\n"
        "# Uncomment the following to stop low-level messages on console\n"
        "#kernel.printk = 3 4 1 3\n\n"
        "##############################################################3\n"
        "# Functions previously found in netbase\n"
        "#\n\n"
        "# Uncomment the next two lines to enable Spoof protection (reverse-path filter)\n"
        "#net.ipv4.conf.default.rp_filter=2\n"
        "#net.ipv4.conf.all.rp_filter=2\n\n"
        "# Uncomment the next line to enable TCP/IP SYN cookies\n"
        "#net.ipv4.tcp_syncookies=1\n\n"
        "# Uncomment the next line to enable packet forwarding for IPv4\n"
        "#net.ipv4.ip_forward=1"
    ),

    # ==========================================================================
    # /proc — mounts, filesystems, stat, net tables, self
    # ==========================================================================

    "cat /proc/mounts": (
        "/dev/root / ext4 rw,noatime 0 0\n"
        "devtmpfs /dev devtmpfs rw,relatime,size=8186432k,nr_inodes=2046608,mode=755 0 0\n"
        "sysfs /sys sysfs rw,nosuid,nodev,noexec,relatime 0 0\n"
        "proc /proc proc rw,relatime 0 0\n"
        "tmpfs /run tmpfs rw,nosuid,nodev,size=1660820k,mode=755 0 0\n"
        "devpts /dev/pts devpts rw,nosuid,noexec,relatime,gid=5,mode=620,ptmxmode=666 0 0\n"
        "tmpfs /dev/shm tmpfs rw,nosuid,nodev 0 0\n"
        "tmpfs /run/lock tmpfs rw,nosuid,nodev,noexec,relatime,size=5120k 0 0\n"
        "cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot 0 0\n"
        "systemd-1 /proc/sys/fs/binfmt_misc autofs rw,relatime,fd=29,pgrp=1,timeout=0,minproto=5,maxproto=5,direct,pipe_ino=1234 0 0\n"
        "mqueue /dev/mqueue mqueue rw,nosuid,nodev,noexec,relatime 0 0\n"
        "debugfs /sys/kernel/debug debugfs rw,nosuid,nodev,noexec,relatime 0 0\n"
        "tracefs /sys/kernel/tracing tracefs rw,nosuid,nodev,noexec,relatime 0 0\n"
        "configfs /sys/kernel/config configfs rw,nosuid,nodev,noexec,relatime 0 0\n"
        "fusectl /sys/fs/fuse/connections fusectl rw,nosuid,nodev,noexec,relatime 0 0\n"
        "/dev/mmcblk0p1 /boot/firmware vfat rw,relatime,fmask=0022,dmask=0022,codepage=437,iocharset=ascii,shortname=mixed,errors=remount-ro 0 0\n"
        "tmpfs /run/user/1000 tmpfs rw,nosuid,nodev,relatime,size=332164k,mode=700,uid=1000,gid=1000 0 0"
    ),

    "cat /proc/filesystems": (
        "nodev\tsysfs\n"
        "nodev\ttmpfs\n"
        "nodev\tbdev\n"
        "nodev\tproc\n"
        "nodev\tcgroup\n"
        "nodev\tcgroup2\n"
        "nodev\tcpuset\n"
        "nodev\tdevtmpfs\n"
        "nodev\tconfigfs\n"
        "nodev\tdebugfs\n"
        "nodev\ttracefs\n"
        "nodev\tsecurityfs\n"
        "nodev\tsockfs\n"
        "nodev\tbpf\n"
        "nodev\tpipefs\n"
        "nodev\tramfs\n"
        "nodev\thugetlbfs\n"
        "nodev\tdevpts\n"
        "\text3\n"
        "\text2\n"
        "\text4\n"
        "\tsquashfs\n"
        "\tvfat\n"
        "nodev\tmqueue\n"
        "nodev\tpstore\n"
        "\tfuseblk\n"
        "nodev\tfuse\n"
        "nodev\tfusectl\n"
        "nodev\tautofs\n"
        "nodev\toverlay"
    ),

    "cat /proc/stat": (
        "cpu  48293 128 24102 3847261 1834 0 892 0 0 0\n"
        "cpu0 12394 34 6123 961892 472 0 234 0 0 0\n"
        "cpu1 11982 31 5984 962103 441 0 218 0 0 0\n"
        "cpu2 12028 32 6012 961723 468 0 226 0 0 0\n"
        "cpu3 11889 31 5983 961543 453 0 214 0 0 0\n"
        "intr 2847392 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n"
        "ctxt 8234729\n"
        "btime 1745367240\n"
        "processes 38291\n"
        "procs_running 1\n"
        "procs_blocked 0\n"
        "softirq 1923847 0 892334 12 384729 0 0 29384 384729 0 232659"
    ),

    "cat /proc/net/dev": (
        "Inter-|   Receive                                                |  Transmit\n"
        " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
        "    lo:  1048576    1024    0    0    0     0          0         0  1048576    1024    0    0    0     0       0          0\n"
        f" {IFACE}: 2847293912   45231    0    0    0     0          0      1823 1204857293   31982    0    0    0     0       0          0"
    ),

    "cat /proc/net/tcp": (
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12847 1 0000000000000000 100 0 0 10 0\n"
        "   1: 0100007F:0035 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 14923 1 0000000000000000 100 0 0 10 0\n"
        "   2: 0100007F:0277 00000000:0000 0A 00000000:00000000 00:00000000 00000000   105        0 15284 1 0000000000000000 100 0 0 10 0\n"
        "   3: 141B040A:0016 37041B0A:C0B2 01 00000000:00000000 02:00028D42 00000000     0        0 18472 2 0000000000000000 20 4 30 10 -1"
    ),

    "cat /proc/net/udp": (
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode ref pointer drops\n"
        "   77: 00000000:0044 00000000:0000 07 00000000:00000000 00:00000000 00000000     0        0 12394 2 0000000000000000 0\n"
        "  156: 0100007F:0035 00000000:0000 07 00000000:00000000 00:00000000 00000000     0        0 14912 2 0000000000000000 0"
    ),

    "cat /proc/net/route": (
        "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
        f"{IFACE}\t00000000\t0104040A\t0003\t0\t0\t600\t00000000\t0\t0\t0\n"
        f"{IFACE}\t0004040A\t00000000\t0001\t0\t0\t600\t00FFFFFF\t0\t0\t0"
    ),

    "cat /proc/self/status": (
        "Name:\tcat\n"
        "Umask:\t0022\n"
        "State:\tR (running)\n"
        "Tgid:\t9823\n"
        "Ngid:\t0\n"
        "Pid:\t9823\n"
        "PPid:\t1847\n"
        "TracerPid:\t0\n"
        "Uid:\t0\t0\t0\t0\n"
        "Gid:\t0\t0\t0\t0\n"
        "FDSize:\t64\n"
        "Groups:\t0 \n"
        "VmPeak:\t    6084 kB\n"
        "VmSize:\t    6084 kB\n"
        "VmRSS:\t    1792 kB\n"
        "Threads:\t1\n"
        "SigQ:\t0/62732\n"
        "Cpus_allowed_list:\t0-3"
    ),

    "cat /proc/1/cmdline": "/sbin/init",
    "cat /proc/1/comm": "systemd",

    # ==========================================================================
    # /boot — Pi-specific
    # ==========================================================================

    "cat /boot/cmdline.txt": (
        "console=serial0,115200 console=tty1 root=PARTUUID=738a4d67-02 rootfstype=ext4 fsck.repair=yes rootwait quiet splash plymouth.ignore-serial-consoles"
    ),

    "cat /boot/config.txt": (
        "# For more options and information see\n"
        "# http://rptl.io/configtxt\n"
        "# Some settings may impact device functionality. See link above for details\n\n"
        "# Uncomment some or all of these to enable the optional hardware interfaces\n"
        "#dtparam=i2c_arm=on\n"
        "#dtparam=i2s=on\n"
        "#dtparam=spi=on\n\n"
        "# Enable audio (loads snd_bcm2835)\n"
        "dtparam=audio=on\n\n"
        "# Additional overlays and parameters are documented\n"
        "# /boot/firmware/overlays/README\n\n"
        "# Automatically load overlays for detected cameras\n"
        "camera_auto_detect=1\n\n"
        "# Automatically load overlays for detected DSI displays\n"
        "display_auto_detect=1\n\n"
        "# Automatically load initramfs files, if found\n"
        "auto_initramfs=1\n\n"
        "# Enable DRM VC4 V3D driver\n"
        "dtoverlay=vc4-kms-v3d\n"
        "max_framebuffers=2\n\n"
        "# Don't have the firmware create an initial video= setting in cmdline.txt.\n"
        "# Use the kernel's default instead.\n"
        "disable_fw_kms_setup=1\n\n"
        "# Run in 64-bit mode\n"
        "arm_64bit=1\n\n"
        "# Disable compensation for displays with overscan\n"
        "disable_overscan=1\n\n"
        "# Run as fast as firmware / board allows\n"
        "arm_boost=1\n\n"
        "[cm4]\n"
        "otg_mode=1\n\n"
        "[cm5]\n"
        "dtoverlay=dwc2,dr_mode=host\n\n"
        "[all]"
    ),

    # ==========================================================================
    # Logs & package history
    # ==========================================================================

    "cat /var/log/apt/history.log": (
        "Start-Date: 2026-04-15  03:14:22\n"
        "Commandline: apt-get upgrade -y\n"
        "Upgrade: libc6:arm64 (2.36-9+deb12u4, 2.36-9+deb12u5), openssh-server:arm64 (9.2p1-2+deb12u2, 9.2p1-2+deb12u3), libssl3:arm64 (3.0.11-1~deb12u2, 3.0.13-1~deb12u1)\n"
        "End-Date: 2026-04-15  03:15:08\n\n"
        "Start-Date: 2026-04-18  14:28:03\n"
        "Commandline: apt install -y rsync\n"
        "Install: rsync:arm64 (3.2.7-1+deb12u1, automatic)\n"
        "End-Date: 2026-04-18  14:28:11\n\n"
        "Start-Date: 2026-04-21  09:03:47\n"
        "Commandline: apt-get install -y mariadb-server\n"
        "Install: mariadb-server:arm64 (1:10.11.6-0+deb12u1), mariadb-client:arm64 (1:10.11.6-0+deb12u1, automatic)\n"
        "End-Date: 2026-04-21  09:04:22"
    ),

    "cat /var/log/dmesg": (
        "[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x414fd0b1]\n"
        f"[    0.000000] Linux version {KERNEL_VERSION} (serge@raspberrypi.com) (aarch64-linux-gnu-gcc-14 (Debian 14.2.0-19) 14.2.0, GNU ld (GNU Binutils for Debian) 2.44) #1 SMP PREEMPT Debian 1:6.12.75-1+rpt1 (2026-03-11)\n"
        "[    0.000000] Machine model: Raspberry Pi 5 Model B Rev 1.1\n"
        "[    0.000000] efi: UEFI not found.\n"
        "[    0.000000] OF: reserved mem: 0x0000000038000000..0x000000003fffffff (131072 KiB) map reusable linux,cma\n"
        "[    0.000000] NUMA: No NUMA configuration found\n"
        "[    0.000000] Kernel command line: coherent_pool=1M 8250.nr_uarts=1 snd_bcm2835.enable_compat_alsa=0 snd_bcm2835.enable_hdmi=1 video=HDMI-A-1:1920x1080M@60 video=HDMI-A-2:1920x1080M@60 smsc95xx.macaddr=D8:3A:DD:A1:B2:C3 vc_mem.mem_base=0x3ec00000 vc_mem.mem_size=0x40000000  console=ttyAMA10,115200 console=tty1 root=PARTUUID=738a4d67-02 rootfstype=ext4 fsck.repair=yes rootwait quiet splash\n"
        "[    1.284712] systemd[1]: Hostname set to <raspberrypi>.\n"
        "[    3.482193] cryptd: max_cpu_qlen set to 1000\n"
        "[    4.128402] Bluetooth: Core ver 2.22\n"
        "[    4.294873] IPv6: ADDRCONF(NETDEV_CHANGE): wlan0: link becomes ready"
    ),

    # --- Shell builtins / empties ---
    "clear": "",
    "exit": "",
    "logout": "",
    "true": "",
    "false": "",
    ":": "",

    # --- History ---
    "history": (
        "    1  ls -la\n"
        "    2  cd /var/www/html\n"
        "    3  cat config.php\n"
        "    4  systemctl status apache2\n"
        f"    5  ping {IP_GATEWAY}\n"
        f"    6  ssh admin@{IP_ADMIN}\n"
        "    7  apt update\n"
        "    8  systemctl restart mariadb\n"
        "    9  tail -f /var/log/syslog\n"
        "   10  df -h\n"
        "   11  free -h\n"
        "   12  crontab -l\n"
        "   13  history"
    ),

    # --- PATH / shell info ---
    "echo $SHELL": USER_SHELL,
    "echo $PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "echo $HOME": USER_HOME,
    "echo $USER": USER_NAME,
    "echo $LOGNAME": USER_NAME,
    "echo $PWD": USER_HOME,
    "echo $HOSTNAME": COWRIE_HOSTNAME,
    "echo $LANG": "en_US.UTF-8",
    "echo $TERM": "xterm-256color",

    # --- Version dumps ---
    "python3 --version": "Python 3.11.8",
    "python --version": "Python 3.11.8",
    "python3 -V": "Python 3.11.8",
    "bash --version": (
        "GNU bash, version 5.2.15(1)-release (aarch64-unknown-linux-gnu)\n"
        "Copyright (C) 2022 Free Software Foundation, Inc.\n"
        "License GPLv3+: GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>\n\n"
        "This is free software; you are free to change and redistribute it.\n"
        "There is NO WARRANTY, to the extent permitted by law."
    ),
    # Matches bait.sh SSH banner (Debian 11 OpenSSH) even though the OS is 13 —
    # this is the drift the attacker sees pre-auth, so ssh -V must agree.
    "ssh -V": "OpenSSH_8.4p1 Debian-5+deb11u1, OpenSSL 1.1.1n  15 Mar 2022",
    "openssl version": "OpenSSL 3.0.13 30 Jan 2024 (Library: OpenSSL 3.0.13 30 Jan 2024)",
    "curl --version": (
        "curl 7.88.1 (aarch64-unknown-linux-gnu) libcurl/7.88.1 OpenSSL/3.0.13 zlib/1.2.13 brotli/1.0.9\n"
        "Protocols: dict file ftp ftps gopher gophers http https imap imaps ldap ldaps mqtt pop3 pop3s rtsp smb smbs smtp smtps telnet tftp\n"
        "Features: alt-svc AsynchDNS brotli GSS-API HSTS HTTP2 HTTPS-proxy IDN IPv6 Kerberos Largefile libz NTLM NTLM_WB PSL SPNEGO SSL threadsafe TLS-SRP UnixSockets"
    ),
    "wget --version": "GNU Wget 1.21.4 built on linux-gnu.",
    "git --version": "git version 2.43.0",
    "perl --version": "This is perl 5, version 36, subversion 0 (v5.36.0) built for aarch64-linux-gnu-thread-multi",
    "mysql --version": "mysql  Ver 15.1 Distrib 10.11.6-MariaDB, for debian-linux-gnu (aarch64) using readline 5.2",
    "apache2 -v": (
        "Server version: Apache/2.4.57 (Debian)\n"
        "Server built:   2024-02-04T21:04:37"
    ),
    "rsync --version": "rsync  version 3.2.7  protocol version 31",
    "vi --version": "VIM - Vi IMproved 9.0 (2022 Jun 28, compiled Apr 12 2024)",
    "nano --version": "GNU nano, version 7.2",

    # --- Package-manager quick stubs (Tier 2 handles heavy queries) ---
    "apt --help": (
        "apt 2.7.14 (arm64)\n"
        "Usage: apt [options] command\n\n"
        "apt is a commandline package manager and provides commands for\n"
        "searching and managing as well as querying information about packages."
    ),
    "dpkg --version": "Debian 'dpkg' package management program version 1.22.0 (arm64).",
}

# Fill in aliases that share a response (defined above as None).
STATIC_RESPONSES["ip addr"] = STATIC_RESPONSES["ip a"]
STATIC_RESPONSES["ip addr show"] = STATIC_RESPONSES["ip a"]
STATIC_RESPONSES["ip route show"] = STATIC_RESPONSES["ip route"]
STATIC_RESPONSES["ip r"] = STATIC_RESPONSES["ip route"]
STATIC_RESPONSES["printenv"] = STATIC_RESPONSES["env"]


# ==============================================================================
# Dynamic handlers — commands whose output SHOULD vary each call
# (date, uptime, /proc/uptime). Real shells don't return the same `date` twice.
# ==============================================================================

def _dynamic(cmd: str):
    """Return (True, text) if cmd matches a dynamic-output command, else None."""
    if cmd == "date":
        return True, _date_default()
    if cmd == "date -u" or cmd == "date --utc":
        return True, time.strftime("%a %b %e %H:%M:%S UTC %Y", time.gmtime())
    if cmd == "date +%s":
        return True, _date_epoch()
    if cmd == "date +%Y-%m-%d":
        return True, time.strftime("%Y-%m-%d")
    if cmd == "date +%Y%m%d":
        return True, time.strftime("%Y%m%d")
    if cmd == "date +%H:%M:%S":
        return True, time.strftime("%H:%M:%S")
    if cmd.startswith("date +"):
        fmt = cmd[len("date +"):]
        # crude — only safe strftime tokens
        try:
            return True, time.strftime(fmt, time.localtime())
        except Exception:
            return True, _date_default()
    if cmd == "uptime":
        return True, _uptime_line()
    if cmd == "uptime -p":
        up = int(time.time() - _BOOT_EPOCH)
        days, rem = divmod(up, 86400)
        hours, rem = divmod(rem, 3600)
        return True, f"up {days} days, {hours} hours"
    if cmd == "uptime -s":
        return True, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_BOOT_EPOCH))
    if cmd == "cat /proc/uptime":
        return True, _proc_uptime()
    if cmd == "w":
        return True, (
            _uptime_line() + "\n"
            "USER     TTY      FROM             LOGIN@   IDLE JCPU   PCPU WHAT\n"
            f"{USER_NAME}     pts/0    10.4.27.55       {time.strftime('%H:%M')}    0.00s  0.02s  0.00s w"
        )
    if cmd == "who":
        return True, f"{USER_NAME}     pts/0        {time.strftime('%Y-%m-%d %H:%M')} (10.4.27.55)"
    if cmd == "last":
        return True, (
            f"{USER_NAME}     pts/0        10.4.27.55       {time.strftime('%a %b %e %H:%M')}   still logged in\n"
            "pi       pts/0        10.4.27.55       Tue Apr 21 03:12 - 03:18  (00:05)\n"
            f"{USER_NAME}     pts/0        {IP_GATEWAY}        Mon Apr 20 03:15 - 03:22  (00:07)\n"
            f"reboot   system boot  {KERNEL_VERSION}     Sun Apr 19 11:52"
        )
    return None


# ==============================================================================
# echo — own handler (flags + var expansion)
# ==============================================================================

_ENV_VARS = {
    "SHELL": USER_SHELL,
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": USER_HOME,
    "USER": USER_NAME,
    "LOGNAME": USER_NAME,
    "PWD": USER_HOME,
    "HOSTNAME": COWRIE_HOSTNAME,
    "LANG": "en_US.UTF-8",
    "TERM": "xterm-256color",
    "UID": "0",
    "EUID": "0",
    "PPID": "1",
    "RANDOM": "0",    # not truly random in our emulation
    "SECONDS": "0",
}
_VAR_RE = re.compile(r"\$(\{)?([A-Za-z_][A-Za-z0-9_]*)(?(1)\})")

def _expand_vars(s: str) -> str:
    return _VAR_RE.sub(lambda m: _ENV_VARS.get(m.group(2), ""), s)

def _handle_echo(argv: list[str]):
    # argv[0] == "echo"
    newline = True
    interp = False
    i = 1
    # parse flags
    while i < len(argv) and argv[i].startswith("-") and len(argv[i]) > 1:
        a = argv[i]
        # bash echo flags: -n (no newline), -e (interpret escapes), -E (no interpret)
        if all(c in "neE" for c in a[1:]):
            if "n" in a[1:]:
                newline = False
            if "e" in a[1:]:
                interp = True
            if "E" in a[1:]:
                interp = False
            i += 1
        else:
            break
    out = " ".join(argv[i:])
    out = _expand_vars(out)
    if interp:
        out = (out.replace("\\n", "\n").replace("\\t", "\t").replace("\\\\", "\\")
                  .replace("\\r", "\r").replace("\\a", "\a").replace("\\b", "\b"))
    return True, (out + ("" if not newline else ""))


# ==============================================================================
# Normalization + public lookup
# ==============================================================================

def _normalize(command: str) -> str:
    """Canonicalize whitespace, strip trailing ;/&, drop `sudo `/`env -i ` prefixes."""
    cmd = command.strip()
    cmd = re.sub(r"[;&]+\s*$", "", cmd).strip()
    cmd = re.sub(r"\s+", " ", cmd)
    # Strip the common noise prefixes attackers use
    while cmd.startswith("sudo "):
        cmd = cmd[5:].lstrip()
    return cmd


def lookup(command: str) -> Tuple[bool, str]:
    """
    Tier 1 public API: (found, response).
    found=True means authoritative — do NOT escalate.
    """
    try:
        cmd = _normalize(command)
    except Exception:
        return False, ""
    if not cmd:
        return True, ""

    # 1. exact hit
    if cmd in STATIC_RESPONSES:
        return True, STATIC_RESPONSES[cmd]

    # 2. dynamic (date/uptime/w/who/last)
    dyn = _dynamic(cmd)
    if dyn:
        return dyn

    # 3. echo with flags/vars
    try:
        argv = shlex.split(cmd)
    except ValueError:
        argv = cmd.split()
    if argv and argv[0] == "echo":
        return _handle_echo(argv)

    # 4. Common aliases: `ll` -> `ls -la` (Tier 2 will handle)
    #    Tier 1 intentionally does NOT answer ls/ps/cat<path>/netstat — those go
    #    to Tier 2 for path-aware dispatch.

    return False, ""


# ==============================================================================
# Self-test
# ==============================================================================
if __name__ == "__main__":
    tests = [
        "whoami", "id", "id -u", "pwd", "hostname", "hostname -f",
        "uname -a", "uname -r", "uname -m", "arch",
        "free -h", "df -h",
        "ifconfig", "ip a", "ip route", "arp -a",
        "cat /etc/passwd is_tier2", "cat /proc/net/arp",
        "date", "date +%s", "uptime", "uptime -p", "w", "who",
        "echo hello world", "echo -n no newline", 'echo "quoted text"',
        "echo $HOME", "echo $USER", "echo -e 'a\\nb'",
        "env", "printenv HOME",
        "python3 --version", "ssh -V",
        "ls /",    # should MISS (Tier 2)
        "ps aux",  # should MISS (Tier 2)
    ]
    for t in tests:
        found, r = lookup(t)
        tag = "HIT " if found else "MISS"
        snippet = (r[:70] + "…") if len(r) > 70 else r
        print(f"[{tag}] {t:<30}  -> {snippet!r}")
