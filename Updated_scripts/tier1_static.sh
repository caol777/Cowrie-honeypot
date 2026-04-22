#!/usr/bin/env python3

# ==============================================================================
# Tier 1 — Static Command Lookup Table
# FAU Team - eMERGE 2026 Hackathon - Project SCALPEL
#
# Handles fully predictable commands instantly with zero latency.
# No model, no cloud, no delay — just a dict lookup.
#
# Commands handled here should NEVER be escalated to Tier 2/3/4.
# Add any command whose output is 100% predictable given our honeyfs config.
# ==============================================================================

STATIC_RESPONSES = {

    # --- Identity & Session ---
    "whoami": "root",
    "id": "uid=0(root) gid=0(root) groups=0(root)",
    "pwd": "/root",
    "hostname": "pi-sensor-gateway",
    "hostname -f": "pi-sensor-gateway.sensor.local",

    # --- OS / Kernel ---
    "uname": "Linux",
    "uname -a": "Linux pi-sensor-gateway 5.15.84-v7l+ #1613 SMP Thu Jan 5 12:01:26 GMT 2023 armv7l GNU/Linux",
    "uname -r": "5.15.84-v7l+",
    "uname -m": "armv7l",
    "uname -s": "Linux",
    "uname -n": "pi-sensor-gateway",
    "arch": "armv7l",

    # --- OS Release ---
    "cat /etc/os-release": (
        'PRETTY_NAME="Debian GNU/Linux 11 (bullseye)"\n'
        'NAME="Debian GNU/Linux"\n'
        'VERSION_ID="11"\n'
        'VERSION="11 (bullseye)"\n'
        'VERSION_CODENAME=bullseye\n'
        'ID=debian\n'
        'HOME_URL="https://www.debian.org/"\n'
        'SUPPORT_URL="https://www.debian.org/support"\n'
        'BUG_REPORT_URL="https://bugs.debian.org/"'
    ),
    "cat /etc/debian_version": "11.6",
    "lsb_release -a": (
        "No LSB modules are available.\n"
        "Distributor ID: Debian\n"
        "Description:    Debian GNU/Linux 11 (bullseye)\n"
        "Release:        11\n"
        "Codename:       bullseye"
    ),

    # --- Hardware ---
    "cat /proc/cpuinfo": (
        "processor\t: 0\n"
        "model name\t: ARMv7 Processor rev 3 (v7l)\n"
        "BogoMIPS\t: 108.00\n"
        "Features\t: half thumb fastmult vfp edsp neon vfpv3 tls vfpv4 idiva idivt vfpd32 lpae evtstrm crc32\n"
        "CPU implementer\t: 0x41\n"
        "CPU architecture: 7\n"
        "CPU variant\t: 0x0\n"
        "CPU part\t: 0xd08\n"
        "CPU revision\t: 3\n\n"
        "processor\t: 1\n"
        "model name\t: ARMv7 Processor rev 3 (v7l)\n"
        "BogoMIPS\t: 108.00\n"
        "Features\t: half thumb fastmult vfp edsp neon vfpv3 tls vfpv4 idiva idivt vfpd32 lpae evtstrm crc32\n"
        "CPU implementer\t: 0x41\n"
        "CPU architecture: 7\n"
        "CPU variant\t: 0x0\n"
        "CPU part\t: 0xd08\n"
        "CPU revision\t: 3\n\n"
        "Hardware\t: BCM2711\n"
        "Revision\t: c03114\n"
        "Serial\t\t: 10000000b1234567\n"
        "Model\t\t: Raspberry Pi 4 Model B Rev 1.4"
    ),
    "cat /proc/version": (
        "Linux version 5.15.84-v7l+ (dom@buildhost) "
        "(arm-linux-gnueabihf-gcc-8 (Ubuntu/Linaro 8.4.0-3ubuntu1) 8.4.0, "
        "GNU ld (GNU Binutils for Ubuntu) 2.34) "
        "#1613 SMP Thu Jan 5 12:01:26 GMT 2023"
    ),

    # --- Memory ---
    "cat /proc/meminfo": (
        "MemTotal:        3884968 kB\n"
        "MemFree:          234156 kB\n"
        "MemAvailable:    1823456 kB\n"
        "Buffers:          124892 kB\n"
        "Cached:          1654320 kB\n"
        "SwapCached:            0 kB\n"
        "Active:          2341872 kB\n"
        "Inactive:         987654 kB\n"
        "SwapTotal:        102396 kB\n"
        "SwapFree:         102396 kB"
    ),
    "free": (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:        3884968     1823456      234156       45892     1827356     1756234\n"
        "Swap:        102396           0      102396"
    ),
    "free -m": (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:           3793        1780         228          44        1784        1715\n"
        "Swap:            99           0          99"
    ),
    "free -h": (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:           3.7G        1.7G        228M         44M        1.7G        1.7G\n"
        "Swap:           99M          0B         99M"
    ),

    # --- Disk ---
    "df": (
        "Filesystem     1K-blocks    Used Available Use% Mounted on\n"
        "udev             1823456       0   1823456   0% /dev\n"
        "tmpfs             388496    1832    386664   1% /run\n"
        "/dev/mmcblk0p2  30703044 4823456  24234456  17% /\n"
        "tmpfs            1942480       0   1942480   0% /dev/shm\n"
        "/dev/mmcblk0p1   258095   49024    209071  19% /boot"
    ),
    "df -h": (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "udev            1.7G     0  1.7G   0% /dev\n"
        "tmpfs           380M  1.8M  378M   1% /run\n"
        "/dev/mmcblk0p2   30G  4.6G   23G  17% /\n"
        "tmpfs           1.9G     0  1.9G   0% /dev/shm\n"
        "/dev/mmcblk0p1  253M   48M  205M  19% /boot"
    ),

    # --- Network ---
    "ifconfig": (
        "eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500\n"
        "        inet 10.1.10.20  netmask 255.255.255.0  broadcast 10.1.10.255\n"
        "        ether b8:27:eb:12:34:56  txqueuelen 1000  (Ethernet)\n"
        "        RX packets 45231  bytes 12453821 (11.8 MiB)\n"
        "        TX packets 31982  bytes 4821045 (4.5 MiB)\n\n"
        "lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536\n"
        "        inet 127.0.0.1  netmask 255.0.0.0\n"
        "        loop  txqueuelen 1000  (Local Loopback)"
    ),
    "ip a": (
        "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN\n"
        "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00\n"
        "    inet 127.0.0.1/8 scope host lo\n"
        "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP\n"
        "    link/ether b8:27:eb:12:34:56 brd ff:ff:ff:ff:ff:ff\n"
        "    inet 10.1.10.20/24 brd 10.1.10.255 scope global eth0"
    ),
    "ip addr": (
        "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN\n"
        "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00\n"
        "    inet 127.0.0.1/8 scope host lo\n"
        "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP\n"
        "    link/ether b8:27:eb:12:34:56 brd ff:ff:ff:ff:ff:ff\n"
        "    inet 10.1.10.20/24 brd 10.1.10.255 scope global eth0"
    ),
    "ip route": (
        "default via 10.1.10.1 dev eth0\n"
        "10.1.10.0/24 dev eth0 proto kernel scope link src 10.1.10.20"
    ),
    "arp -a": (
        "gateway (10.1.10.1) at b8:27:eb:12:34:56 [ether] on eth0\n"
        "node-beta (10.1.10.21) at b8:27:eb:ab:cd:ef [ether] on eth0\n"
        "node-gamma (10.1.10.22) at b8:27:eb:98:76:54 [ether] on eth0\n"
        "admin (10.1.10.55) at dc:a6:32:11:22:33 [ether] on eth0"
    ),
    "netstat -i": (
        "Kernel Interface table\n"
        "Iface      MTU    RX-OK RX-ERR RX-DRP RX-OVR    TX-OK TX-ERR TX-DRP TX-OVR Flg\n"
        "eth0      1500    45231      0      0 0         31982      0      0      0 BMRU\n"
        "lo       65536     1024      0      0 0          1024      0      0      0 LRU"
    ),

    # --- Users & Auth ---
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
    "cat /etc/group": (
        "root:x:0:\n"
        "daemon:x:1:\n"
        "bin:x:2:\n"
        "sys:x:3:\n"
        "sudo:x:27:pi\n"
        "www-data:x:33:\n"
        "pi:x:1000:\n"
        "webadmin:x:1001:"
    ),
    "w": (
        " 14:23:01 up 3 days,  2:14,  1 user,  load average: 0.12, 0.08, 0.05\n"
        "USER     TTY      FROM             LOGIN@   IDLE JCPU   PCPU WHAT\n"
        "root     pts/0    10.1.10.55       14:21    0.00s  0.02s  0.00s w"
    ),
    "who": "root     pts/0        2026-04-22 14:21 (10.1.10.55)",
    "last": (
        "root     pts/0        10.1.10.55       Wed Apr 22 14:21   still logged in\n"
        "pi       pts/0        10.1.10.55       Tue Apr 21 03:12 - 03:18  (00:05)\n"
        "root     pts/0        10.1.10.1        Mon Apr 20 03:15 - 03:22  (00:07)\n"
        "reboot   system boot  5.15.84-v7l+     Sun Apr 19 11:52"
    ),

    # --- Environment ---
    "env": (
        "SHELL=/bin/bash\n"
        "PWD=/root\n"
        "LOGNAME=root\n"
        "HOME=/root\n"
        "LANG=en_GB.UTF-8\n"
        "USER=root\n"
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n"
        "TERM=xterm-256color"
    ),
    "echo $SHELL": "/bin/bash",
    "echo $PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "echo $HOME": "/root",
    "echo $USER": "root",

    # --- Uptime / Load ---
    "uptime": " 14:23:01 up 3 days,  2:14,  1 user,  load average: 0.12, 0.08, 0.05",
    "cat /proc/uptime": "282841.23 1089234.12",

    # --- Crontab ---
    "crontab -l": (
        "# Sensor data collection\n"
        "*/5 * * * * /opt/sensor/collect.sh >> /var/log/sensor.log 2>&1\n"
        "# Database backup\n"
        "0 2 * * * /usr/local/bin/db_backup.sh\n"
        "# Sync to remote node\n"
        "30 3 * * * rsync -az /var/sensor-data/ admin@10.1.10.55:/backup/node-alpha/"
    ),

    # --- Common file reads ---
    "cat /etc/hostname": "pi-sensor-gateway",
    "cat /etc/hosts": (
        "127.0.0.1       localhost\n"
        "127.0.1.1       pi-sensor-gateway\n"
        "10.1.10.20      node-alpha.sensor.local     node-alpha\n"
        "10.1.10.21      node-beta.sensor.local      node-beta\n"
        "10.1.10.22      node-gamma.sensor.local     node-gamma\n"
        "10.1.10.1       gateway.sensor.local        gateway"
    ),
    "cat /etc/resolv.conf": (
        "nameserver 8.8.8.8\n"
        "nameserver 8.8.4.4\n"
        "search sensor.local"
    ),
    "cat /proc/net/arp": (
        "IP address       HW type     Flags       HW address            Mask     Device\n"
        "10.1.10.1        0x1         0x2         b8:27:eb:12:34:56     *        eth0\n"
        "10.1.10.21       0x1         0x2         b8:27:eb:ab:cd:ef     *        eth0\n"
        "10.1.10.22       0x1         0x2         b8:27:eb:98:76:54     *        eth0\n"
        "10.1.10.55       0x1         0x2         dc:a6:32:11:22:33     *        eth0"
    ),

    # --- Shell builtins that should always work ---
    "echo": "",
    "clear": "",
    "exit": "",
    "logout": "",
    "history": (
        "    1  ping 8.8.8.8\n"
        "    2  apt update && apt upgrade -y\n"
        "    3  nano /var/www/html/config.php\n"
        "    4  systemctl restart mariadb\n"
        "    5  ssh admin@10.1.10.55\n"
        "    6  docker-compose up -d\n"
        "    7  cat /etc/passwd\n"
        "    8  crontab -l\n"
        "    9  mysql -u root -pFAU_cyber_db_admin_99! sensor_data_metrics\n"
        "   10  exit"
    ),
}


def lookup(command: str) -> tuple[bool, str]:
    """
    Returns (found, response).
    If found is True, use response directly — do not escalate.
    If found is False, pass to Tier 2.
    """
    cmd = command.strip()

    # Exact match first
    if cmd in STATIC_RESPONSES:
        return True, STATIC_RESPONSES[cmd]

    # Prefix match for commands like 'echo anything'
    if cmd.startswith("echo "):
        text = cmd[5:].strip().strip('"').strip("'")
        return True, text

    # cat with known file
    for key, val in STATIC_RESPONSES.items():
        if key == cmd:
            return True, val

    return False, ""


if __name__ == "__main__":
    # Quick test
    tests = ["whoami", "uname -a", "free -h", "df -h", "cat /etc/passwd", "echo hello world", "unknown-cmd"]
    for t in tests:
        found, resp = lookup(t)
        print(f"[{'HIT' if found else 'MISS'}] {t!r}")
        if found:
            print(f"  -> {resp[:60]}...")
        print()