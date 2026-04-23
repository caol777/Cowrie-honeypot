#!/bin/bash

# ==============================================================================
# Cowrie Deception Configurator v4 — Project SCALPEL
# FAU Team - eMERGE 2026 Hackathon
#
# Run as the COWRIE USER (not root):
#   ssh cowrie@<pi_ip>    password: honeypot
#   bash bait.sh
#
# The Pi comes with Cowrie PRE-INSTALLED. This script only:
#   - Updates cowrie.cfg (hostname, SSH banner)
#   - Populates honeyfs with realistic fake files
#   - Does NOT install, reinstall, or touch the Cowrie service
#
# DAY-OF CHECKLIST:
#   Nothing to change in this file — it runs as-is.
#   The pickle file is already at ~/cowrie/share/cowrie/fs.pickle (pre-installed).
# ==============================================================================

if [ -d "$HOME/cowrie" ]; then
    COWRIE_DIR="$HOME/cowrie"
else
    echo "[!] Cannot find cowrie directory at $HOME/cowrie"
    exit 1
fi

if [ -f "$COWRIE_DIR/etc/cowrie.cfg" ]; then
    COWRIE_CFG="$COWRIE_DIR/etc/cowrie.cfg"
elif [ -f "$COWRIE_DIR/cowrie.cfg" ]; then
    COWRIE_CFG="$COWRIE_DIR/cowrie.cfg"
else
    echo "[!] cowrie.cfg not found — copying from template"
    cp "$COWRIE_DIR/etc/cowrie.cfg.dist" "$COWRIE_DIR/etc/cowrie.cfg"
    COWRIE_CFG="$COWRIE_DIR/etc/cowrie.cfg"
fi

NEW_HOSTNAME="raspberrypi"
SSH_BANNER="SSH-2.0-OpenSSH_8.4p1 Debian-5+deb11u1"

echo "[*] Starting Cowrie Deception Setup v4..."

# ==============================================================================
# 1. Update cowrie.cfg
# ==============================================================================
echo "[+] Setting hostname: $NEW_HOSTNAME"
sed -i "s/^hostname =.*/hostname = $NEW_HOSTNAME/" "$COWRIE_CFG"
grep -q "^hostname" "$COWRIE_CFG" || echo "hostname = $NEW_HOSTNAME" >> "$COWRIE_CFG"

echo "[+] Setting SSH banner: $SSH_BANNER"
sed -i "s/^version =.*/version = $SSH_BANNER/" "$COWRIE_CFG"
grep -q "^version" "$COWRIE_CFG" || echo "version = $SSH_BANNER" >> "$COWRIE_CFG"

# ==============================================================================
# 2. HoneyFS directories
# ==============================================================================
echo "[+] Creating honeyfs structure..."
mkdir -p "$COWRIE_DIR/honeyfs/etc/cron.d"
mkdir -p "$COWRIE_DIR/honeyfs/var/www/html"
mkdir -p "$COWRIE_DIR/honeyfs/var/log"
mkdir -p "$COWRIE_DIR/honeyfs/proc/net"
mkdir -p "$COWRIE_DIR/honeyfs/root/.aws"
mkdir -p "$COWRIE_DIR/honeyfs/root/.ssh"
mkdir -p "$COWRIE_DIR/honeyfs/home/pi"
mkdir -p "$COWRIE_DIR/honeyfs/opt/sensor"

# ==============================================================================
# 3. Core system files
# ==============================================================================
echo "[+] Writing core system files..."

cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/passwd"
root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
bin:x:2:2:bin:/bin:/usr/sbin/nologin
sys:x:3:3:sys:/dev:/usr/sbin/nologin
sync:x:4:65534:sync:/bin:/bin/sync
www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin
pi:x:1000:1000:,,,:/home/pi:/bin/bash
webadmin:x:1001:1001:,,,:/home/webadmin:/bin/bash
mysql:x:1002:1002:MySQL Server,,,:/nonexistent:/bin/false
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/shadow"
root:$6$rounds=656000$rAnDoMsAlT123$fakehashedpassword123456789abcdef:19200:0:99999:7:::
pi:$6$rounds=656000$aNothErSaLt456$fakehashedpassword987654321zyxwvu:19200:0:99999:7:::
webadmin:$6$rounds=656000$yEtAnOtHeR789$fakehashedpasswordabcdef123456789:19200:0:99999:7:::
EOF

echo "pi-sensor-gateway" > "$COWRIE_DIR/honeyfs/etc/hostname"

cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/hosts"
# Your system has configured 'manage_etc_hosts' as True.
# As a result, if you wish for changes to this file to persist
# then you will need to either
# a.) make changes to the master file in /etc/cloud/templates/hosts.debian.tmpl
# b.) change or remove the value of 'manage_etc_hosts' in
#     /etc/cloud/cloud.cfg or cloud-config from user-data
#
127.0.1.1 raspberrypi raspberrypi
127.0.0.1 localhost

# The following lines are desirable for IPv6 capable hosts
::1 localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/os-release"
PRETTY_NAME="Debian GNU/Linux 13 (trixie)"
NAME="Debian GNU/Linux"
VERSION_ID="13"
VERSION="13 (trixie)"
VERSION_CODENAME=trixie
DEBIAN_VERSION_FULL=13.4
ID=debian
HOME_URL="https://www.debian.org/"
SUPPORT_URL="https://www.debian.org/support"
BUG_REPORT_URL="https://bugs.debian.org/"
EOF

# ==============================================================================
# 4. Crontabs
# ==============================================================================
echo "[+] Writing crontabs..."

cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/crontab"
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# m h dom mon dow user  command
17 *    * * *   root    cd / && run-parts --report /etc/cron.hourly
25 6    * * *   root    test -x /usr/sbin/anacron || ( cd / && run-parts --report /etc/cron.daily )
*/5 *   * * *   pi      /opt/sensor/collect.sh >> /var/log/sensor.log 2>&1
0   2   * * *   root    /usr/local/bin/db_backup.sh
30  3   * * *   root    rsync -az /var/sensor-data/ admin@10.1.10.55:/backup/node-alpha/
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/cron.d/sensor-sync"
# Sensor network sync - DO NOT REMOVE
*/10 * * * * root /opt/sensor/sync_nodes.sh 2>/dev/null
0 4 * * * root scp -i /root/.ssh/id_rsa /var/www/html/config.php webadmin@10.1.10.55:/tmp/cfg_backup
EOF

# ==============================================================================
# 5. /proc entries
# ==============================================================================
echo "[+] Writing /proc entries..."

cat << 'EOF' > "$COWRIE_DIR/honeyfs/proc/cpuinfo"
processor       : 0
BogoMIPS        : 108.00
Features        : fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp asimdhp cpuid asimdrdm lrcpc dcpop asimddp
CPU implementer : 0x41
CPU architecture: 8
CPU variant     : 0x4
CPU part        : 0xd0b
CPU revision    : 1

processor       : 1
BogoMIPS        : 108.00
Features        : fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp asimdhp cpuid asimdrdm lrcpc dcpop asimddp
CPU implementer : 0x41
CPU architecture: 8
CPU variant     : 0x4
CPU part        : 0xd0b
CPU revision    : 1

processor       : 2
BogoMIPS        : 108.00
Features        : fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp asimdhp cpuid asimdrdm lrcpc dcpop asimddp
CPU implementer : 0x41
CPU architecture: 8
CPU variant     : 0x4
CPU part        : 0xd0b
CPU revision    : 1

processor       : 3
BogoMIPS        : 108.00
Features        : fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp asimdhp cpuid asimdrdm lrcpc dcpop asimddp
CPU implementer : 0x41
CPU architecture: 8
CPU variant     : 0x4
CPU part        : 0xd0b
CPU revision    : 1

Revision        : e04171
Serial          : 394acb79c7ff9ea1
Model           : Raspberry Pi 5 Model B Rev 1.1
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/proc/version"
Linux version 6.12.75+rpt-rpi-2712 (serge@raspberrypi.com) (aarch64-linux-gnu-gcc-14 (Debian 14.2.0-19) 14.2.0, GNU ld (GNU Binutils for Debian) 2.44) #1 SMP PREEMPT Debian 1:6.12.75-1+rpt1 (2026-03-11)
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/proc/meminfo"
MemTotal:       16608192 kB
MemFree:        15828176 kB
MemAvailable:   16218368 kB
Buffers:           38560 kB
Cached:           432464 kB
SwapCached:            0 kB
Active:           248528 kB
Inactive:         286448 kB
Active(anon):      76816 kB
Inactive(anon):        0 kB
Active(file):     171712 kB
Inactive(file):   286448 kB
Unevictable:           0 kB
Mlocked:               0 kB
SwapTotal:       2097136 kB
SwapFree:        2097136 kB
Zswap:                 0 kB
Zswapped:              0 kB
Dirty:                 0 kB
Writeback:             0 kB
AnonPages:         64144 kB
Mapped:            44528 kB
Shmem:             13152 kB
KReclaimable:      36640 kB
Slab:              80288 kB
SReclaimable:      36640 kB
SUnreclaim:        43648 kB
KernelStack:        2912 kB
PageTables:         3808 kB
SecPageTables:       128 kB
NFS_Unstable:          0 kB
Bounce:                0 kB
WritebackTmp:          0 kB
CommitLimit:    10401232 kB
Committed_AS:     137344 kB
VmallocTotal:   68447887360 kB
VmallocUsed:       65904 kB
VmallocChunk:          0 kB
Percpu:             1344 kB
CmaTotal:          65536 kB
CmaFree:           55296 kB
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/proc/net/arp"
IP address       HW type     Flags       HW address            Mask     Device
10.4.27.50       0x1         0x2         5a:72:05:86:d5:b5     *        wlan0
10.4.27.1        0x1         0x2         f4:1e:57:85:0b:06     *        wlan0
10.4.27.34       0x1         0x2         f4:46:37:cb:66:b9     *        wlan0
EOF

# ==============================================================================
# 6. Bait files
# ==============================================================================
echo "[+] Writing bait files..."

cat << 'EOF' > "$COWRIE_DIR/honeyfs/var/www/html/config.php"
<?php
// Auto-generated by Ansible
define('DB_SERVER', 'localhost');
define('DB_USERNAME', 'root');
define('DB_PASSWORD', 'FAU_cyber_db_admin_99!');
define('DB_NAME', 'sensor_data_metrics');
?>
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/motd"

====================================================================
WARNING: UNAUTHORIZED ACCESS PROHIBITED
Property of Distributed Sensor Network - Node Alpha
All connections are monitored and recorded.
====================================================================
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/root/.bash_history"
ping 8.8.8.8
apt update && apt upgrade -y
nano /var/www/html/config.php
systemctl restart mariadb
systemctl status apache2
ssh admin@10.1.10.55
ssh -i /root/.ssh/id_rsa webadmin@10.1.10.21
rsync -az /var/sensor-data/ admin@10.1.10.55:/backup/
cat /etc/passwd
crontab -l
mysql -u root -pFAU_cyber_db_admin_99! sensor_data_metrics
exit
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/home/pi/.bash_history"
ls -la
cd /var/www/html
cat config.php
python3 collect.py
sudo systemctl status sensor
ping 10.1.10.1
exit
EOF

# Plausible AWS key — NOT the AWS docs example (AKIAIOSFODNN7EXAMPLE)
cat << 'EOF' > "$COWRIE_DIR/honeyfs/root/.aws/credentials"
[default]
aws_access_key_id = AKIAQX3LM7NP2RSTVW84
aws_secret_access_key = Jx7vK2mPqR9nL4wT6yB3hF8cZ1dA5eG0iUoYsNj
region = us-east-1
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/root/.aws/config"
[default]
region = us-east-1
output = json
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/root/.ssh/known_hosts"
10.1.10.21 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC2vX fake_key_node_beta==
10.1.10.22 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD3wY fake_key_node_gamma==
10.1.10.55 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQE4xZ fake_key_admin==
EOF

cat << 'EOF' > "$COWRIE_DIR/honeyfs/var/log/auth.log"
Apr 20 03:12:45 pi-sensor-gateway sshd[1234]: Accepted publickey for pi from 10.1.10.55 port 51234 ssh2
Apr 20 03:12:46 pi-sensor-gateway sshd[1234]: pam_unix(sshd:session): session opened for user pi
Apr 20 03:18:22 pi-sensor-gateway sshd[1234]: pam_unix(sshd:session): session closed for user pi
Apr 21 02:00:01 pi-sensor-gateway cron[892]: (root) CMD (/usr/local/bin/db_backup.sh)
Apr 22 03:15:01 pi-sensor-gateway sshd[2891]: Accepted publickey for root from 10.1.10.1 port 49823 ssh2
Apr 22 03:22:17 pi-sensor-gateway sshd[2891]: pam_unix(sshd:session): session closed for user root
EOF

# ==============================================================================
# 7. Restart Cowrie
# ==============================================================================
echo "[+] Restarting Cowrie..."
if [ -f "$COWRIE_DIR/bin/cowrie" ]; then
    "$COWRIE_DIR/bin/cowrie" restart
    sleep 2
    "$COWRIE_DIR/bin/cowrie" status
else
    echo "[!] Restart manually: ~/cowrie/bin/cowrie restart"
fi

echo ""
echo "=== Deception Setup Complete ==="
echo "  Hostname : $NEW_HOSTNAME"
echo "  Banner   : $SSH_BANNER"
echo "  HoneyFS  : passwd, shadow, hosts, crontab, proc, auth.log, .aws, .bash_history"
echo ""
echo "  Verify: ssh root@<pi_ip> -p 2222   password: root"
