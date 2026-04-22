#!/bin/bash

# ==============================================================================
# Cowrie Deception Configurator v3
# FAU Team - eMERGE 2026 Hackathon - Project SCALPEL
#
# Run as the 'cowrie' user from within your cowrie installation directory.
# ==============================================================================

# ==============================================================================
# !! DAY-OF CHECKLIST — CHANGE THESE BEFORE RUNNING !!
#
#   1. HOST_SERVER_IP — set this to the IP of whichever laptop is serving
#      the pickle file. To serve it, run this on that laptop:
#        python3 -m http.server 8000
#      Then find the laptop's IP with: ip a  (Linux) or ipconfig (Windows)
#      If you have no pickle ready, comment out Section 3 entirely and
#      Cowrie will fall back to its default filesystem (not ideal but functional)
#
#   2. That's it. Everything else is pre-configured.
#
# ==============================================================================

COWRIE_DIR="$HOME/cowrie"
NEW_HOSTNAME="pi-sensor-gateway"
SSH_BANNER="SSH-2.0-OpenSSH_8.4p1 Debian-5+deb11u1"

# !! DAY-OF: Change this to your pickle-serving laptop's IP !!
HOST_SERVER_IP="CHANGE_ME"
PICKLE_FILENAME="hackathon_pi.pickle"

# Safety check — warn but don't exit, so rest of script still runs
if [ "$HOST_SERVER_IP" = "CHANGE_ME" ]; then
    echo "[!] WARNING: HOST_SERVER_IP is not set. Skipping pickle download."
    echo "[!]          Set HOST_SERVER_IP at the top of this script and re-run Section 3 manually."
    SKIP_PICKLE=true
else
    SKIP_PICKLE=false
fi

echo "[*] Starting Cowrie Deception Setup v3..."

# ==============================================================================
# 1. Initialize Configuration File
# ==============================================================================
if [ ! -f "$COWRIE_DIR/etc/cowrie.cfg" ]; then
    echo "[+] Creating cowrie.cfg from distribution template..."
    cp "$COWRIE_DIR/etc/cowrie.cfg.dist" "$COWRIE_DIR/etc/cowrie.cfg"
fi

# Point COWRIE_CFG to wherever the cfg actually lives
if [ -f "$COWRIE_DIR/etc/cowrie.cfg" ]; then
    COWRIE_CFG="$COWRIE_DIR/etc/cowrie.cfg"
else
    COWRIE_CFG="$COWRIE_DIR/cowrie.cfg"
fi

# ==============================================================================
# 2. Modify Hostname and SSH Banner
# ==============================================================================
echo "[+] Spoofing hostname to: $NEW_HOSTNAME"
sed -i "s/^hostname =.*/hostname = $NEW_HOSTNAME/" "$COWRIE_CFG"

echo "[+] Spoofing SSH version banner to: $SSH_BANNER"
sed -i "s/^version =.*/version = $SSH_BANNER/" "$COWRIE_CFG"

# ==============================================================================
# 3. Download & Configure the Custom Skeleton (.pickle)
# ==============================================================================
if [ "$SKIP_PICKLE" = false ]; then
    echo "[+] Fetching custom filesystem skeleton from $HOST_SERVER_IP..."
    curl -s --connect-timeout 5 \
        -o "$COWRIE_DIR/share/cowrie/$PICKLE_FILENAME" \
        "http://$HOST_SERVER_IP:8000/$PICKLE_FILENAME"

    if [ $? -eq 0 ] && [ -s "$COWRIE_DIR/share/cowrie/$PICKLE_FILENAME" ]; then
        echo "[+] Pickle downloaded successfully."
        sed -i '/^filesystem =/d' "$COWRIE_CFG"
        sed -i "/^\[shell\]/a filesystem = share/cowrie/$PICKLE_FILENAME" "$COWRIE_CFG"
        echo "[+] cowrie.cfg updated to use custom filesystem."
    else
        echo "[!] Pickle download failed or file is empty — falling back to Cowrie default filesystem."
        echo "[!] Check that python3 -m http.server 8000 is running on $HOST_SERVER_IP"
    fi
else
    echo "[*] Skipping pickle download (HOST_SERVER_IP not set)."
fi

# ==============================================================================
# 4. HoneyFS — Core System Files
# ==============================================================================
echo "[+] Generating realistic system files in honeyfs..."
mkdir -p "$COWRIE_DIR/honeyfs/etc/cron.d"
mkdir -p "$COWRIE_DIR/honeyfs/var/www/html"
mkdir -p "$COWRIE_DIR/honeyfs/var/log"
mkdir -p "$COWRIE_DIR/honeyfs/proc"
mkdir -p "$COWRIE_DIR/honeyfs/root/.aws"
mkdir -p "$COWRIE_DIR/honeyfs/root/.ssh"
mkdir -p "$COWRIE_DIR/honeyfs/home/pi"
mkdir -p "$COWRIE_DIR/honeyfs/home/webadmin"

# Fake /etc/passwd
cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/passwd"
root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
bin:x:2:2:bin:/bin:/usr/sbin/nologin
sys:x:3:3:sys:/dev:/usr/sbin/nologin
sync:x:4:65534:sync:/bin:/bin/sync
games:x:5:60:games:/usr/games:/usr/sbin/nologin
man:x:6:12:man:/var/cache/man:/usr/sbin/nologin
www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin
pi:x:1000:1000:,,,:/home/pi:/bin/bash
webadmin:x:1001:1001:,,,:/home/webadmin:/bin/bash
mysql:x:1002:1002:MySQL Server,,,:/nonexistent:/bin/false
EOF

# Fake /etc/shadow (hashed passwords — looks real, not crackable)
cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/shadow"
root:$6$rounds=656000$randomsalt123$fakehashedpassword123456789abcdefghijklmnopqrstuvwxyz0123456789:19200:0:99999:7:::
pi:$6$rounds=656000$anothersalt456$fakehashedpassword987654321zyxwvutsrqponmlkjihgfedcba9876543210:19200:0:99999:7:::
webadmin:$6$rounds=656000$yetsalt789$fakehashedpasswordabcdef123456789abcdefghijklmnopqrstuvwxyz01234:19200:0:99999:7:::
EOF

# Fake /etc/os-release
cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/os-release"
PRETTY_NAME="Debian GNU/Linux 11 (bullseye)"
NAME="Debian GNU/Linux"
VERSION_ID="11"
VERSION="11 (bullseye)"
VERSION_CODENAME=bullseye
ID=debian
HOME_URL="https://www.debian.org/"
SUPPORT_URL="https://www.debian.org/support"
BUG_REPORT_URL="https://bugs.debian.org/"
EOF

# Fake /etc/hostname
echo "pi-sensor-gateway" > "$COWRIE_DIR/honeyfs/etc/hostname"

# Fake /etc/hosts
cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/hosts"
127.0.0.1       localhost
127.0.1.1       pi-sensor-gateway
10.1.10.20      node-alpha.sensor.local     node-alpha
10.1.10.21      node-beta.sensor.local      node-beta
10.1.10.22      node-gamma.sensor.local     node-gamma
10.1.10.1       gateway.sensor.local        gateway
EOF

# ==============================================================================
# 5. HoneyFS — Fake Crontabs (attackers ALWAYS check these)
# ==============================================================================
echo "[+] Injecting fake crontab entries..."

# /etc/crontab
cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/crontab"
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# m h dom mon dow user  command
17 *    * * *   root    cd / && run-parts --report /etc/cron.hourly
25 6    * * *   root    test -x /usr/sbin/anacron || ( cd / && run-parts --report /etc/cron.daily )
47 6    * * 7   root    test -x /usr/sbin/anacron || ( cd / && run-parts --report /etc/cron.weekly )
52 6    1 * *   root    test -x /usr/sbin/anacron || ( cd / && run-parts --report /etc/cron.monthly )
# Sensor data collection
*/5 *   * * *   pi      /opt/sensor/collect.sh >> /var/log/sensor.log 2>&1
# Database backup
0   2   * * *   root    /usr/local/bin/db_backup.sh
# Sync to remote node
30  3   * * *   root    rsync -az /var/sensor-data/ admin@10.1.10.55:/backup/node-alpha/
EOF

# Fake cron job that references the database backup script
cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/cron.d/sensor-sync"
# Sensor network sync job - DO NOT REMOVE
*/10 * * * * root /opt/sensor/sync_nodes.sh 2>/dev/null
0 4 * * * root scp -i /root/.ssh/id_rsa /var/www/html/config.php webadmin@10.1.10.55:/tmp/cfg_backup
EOF

# ==============================================================================
# 6. HoneyFS — Fake /proc entries (attackers run uname, check cpuinfo)
# ==============================================================================
echo "[+] Injecting fake /proc entries..."

# Fake /proc/cpuinfo — looks like a real Raspberry Pi 4
cat << 'EOF' > "$COWRIE_DIR/honeyfs/proc/cpuinfo"
processor       : 0
model name      : ARMv7 Processor rev 3 (v7l)
BogoMIPS        : 108.00
Features        : half thumb fastmult vfp edsp neon vfpv3 tls vfpv4 idiva idivt vfpd32 lpae evtstrm crc32
CPU implementer : 0x41
CPU architecture: 7
CPU variant     : 0x0
CPU part        : 0xd08
CPU revision    : 3

processor       : 1
model name      : ARMv7 Processor rev 3 (v7l)
BogoMIPS        : 108.00
Features        : half thumb fastmult vfp edsp neon vfpv3 tls vfpv4 idiva idivt vfpd32 lpae evtstrm crc32
CPU implementer : 0x41
CPU architecture: 7
CPU variant     : 0x0
CPU part        : 0xd08
CPU revision    : 3

Hardware        : BCM2711
Revision        : c03114
Serial          : 10000000b1234567
Model           : Raspberry Pi 4 Model B Rev 1.4
EOF

# Fake /proc/meminfo
cat << 'EOF' > "$COWRIE_DIR/honeyfs/proc/meminfo"
MemTotal:        3884968 kB
MemFree:          234156 kB
MemAvailable:    1823456 kB
Buffers:          124892 kB
Cached:          1654320 kB
SwapCached:            0 kB
Active:          2341872 kB
Inactive:         987654 kB
SwapTotal:       102396 kB
SwapFree:        102396 kB
EOF

# Fake /proc/version
cat << 'EOF' > "$COWRIE_DIR/honeyfs/proc/version"
Linux version 5.15.84-v7l+ (dom@buildhost) (arm-linux-gnueabihf-gcc-8 (Ubuntu/Linaro 8.4.0-3ubuntu1) 8.4.0, GNU ld (GNU Binutils for Ubuntu) 2.34) #1613 SMP Thu Jan 5 12:01:26 GMT 2023
EOF

# ==============================================================================
# 7. HoneyFS — Fake ARP neighbors (makes network feel populated)
# ==============================================================================
echo "[+] Injecting fake ARP table..."

# Cowrie doesn't simulate arp -a natively but we can add it to honeyfs
# so if attacker views /proc/net/arp it looks populated
cat << 'EOF' > "$COWRIE_DIR/honeyfs/proc/net/arp"
IP address       HW type     Flags       HW address            Mask     Device
10.1.10.1        0x1         0x2         b8:27:eb:12:34:56     *        eth0
10.1.10.21       0x1         0x2         b8:27:eb:ab:cd:ef     *        eth0
10.1.10.22       0x1         0x2         b8:27:eb:98:76:54     *        eth0
10.1.10.55       0x1         0x2         dc:a6:32:11:22:33     *        eth0
EOF

# ==============================================================================
# 8. HoneyFS — Bait Files
# ==============================================================================
echo "[+] Injecting bait files..."

# Fake database config
cat << 'EOF' > "$COWRIE_DIR/honeyfs/var/www/html/config.php"
<?php
// Auto-generated by Ansible
define('DB_SERVER', 'localhost');
define('DB_USERNAME', 'root');
define('DB_PASSWORD', 'FAU_cyber_db_admin_99!');
define('DB_NAME', 'sensor_data_metrics');
?>
EOF

# Fake MOTD
cat << 'EOF' > "$COWRIE_DIR/honeyfs/etc/motd"

====================================================================
WARNING: UNAUTHORIZED ACCESS PROHIBITED
Property of Distributed Sensor Network - Node Alpha
All connections are monitored and recorded.
====================================================================
EOF

# Fake .bash_history for root — tells a convincing story
cat << 'EOF' > "$COWRIE_DIR/honeyfs/root/.bash_history"
ping 8.8.8.8
apt update && apt upgrade -y
nano /var/www/html/config.php
systemctl restart mariadb
systemctl status apache2
ssh admin@10.1.10.55
ssh -i /root/.ssh/id_rsa webadmin@10.1.10.21
rsync -az /var/sensor-data/ admin@10.1.10.55:/backup/
docker-compose up -d
cat /etc/passwd
crontab -l
mysql -u root -pFAU_cyber_db_admin_99! sensor_data_metrics
exit
EOF

# Fake .bash_history for pi user
cat << 'EOF' > "$COWRIE_DIR/honeyfs/home/pi/.bash_history"
ls -la
cd /var/www/html
cat config.php
python3 collect.py
sudo systemctl status sensor
ping 10.1.10.1
exit
EOF

# Fake AWS credentials — plausible looking, NOT the AWS docs example key
# Key format: AKIA + 16 uppercase alphanumeric chars
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

# Fake SSH known_hosts (implies this node connects to others)
cat << 'EOF' > "$COWRIE_DIR/honeyfs/root/.ssh/known_hosts"
10.1.10.21 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC2vX fake_key_node_beta==
10.1.10.22 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD3wY fake_key_node_gamma==
10.1.10.55 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQE4xZ fake_key_admin==
EOF

# Fake /var/log/auth.log snippet (shows prior legitimate logins)
cat << 'EOF' > "$COWRIE_DIR/honeyfs/var/log/auth.log"
Apr 20 03:12:45 pi-sensor-gateway sshd[1234]: Accepted publickey for pi from 10.1.10.55 port 51234 ssh2
Apr 20 03:12:46 pi-sensor-gateway sshd[1234]: pam_unix(sshd:session): session opened for user pi
Apr 20 03:18:22 pi-sensor-gateway sshd[1234]: pam_unix(sshd:session): session closed for user pi
Apr 21 02:00:01 pi-sensor-gateway cron[892]: (root) CMD (/usr/local/bin/db_backup.sh)
Apr 21 02:00:03 pi-sensor-gateway cron[893]: (root) CMD (rsync -az /var/sensor-data/ admin@10.1.10.55:/backup/node-alpha/)
Apr 22 03:15:01 pi-sensor-gateway sshd[2891]: Accepted publickey for root from 10.1.10.1 port 49823 ssh2
Apr 22 03:15:02 pi-sensor-gateway sshd[2891]: pam_unix(sshd:session): session opened for user root
Apr 22 03:22:17 pi-sensor-gateway sshd[2891]: pam_unix(sshd:session): session closed for user root
EOF

echo ""
echo "[*] Deception setup complete!"
echo "[*] Restart Cowrie to apply changes: bin/cowrie restart"
echo ""
echo "=== Deception Summary ==="
echo "  Hostname     : $NEW_HOSTNAME"
echo "  SSH Banner   : $SSH_BANNER"
echo "  Pickle       : $([ "$SKIP_PICKLE" = true ] && echo 'SKIPPED - set HOST_SERVER_IP' || echo "loaded from $HOST_SERVER_IP")"
echo "  Fake users   : root, pi, webadmin, mysql"
echo "  Bait files   : config.php, .aws/credentials, .bash_history, crontab, auth.log"
echo "  Fake network : 4 ARP neighbors, known_hosts to 3 nodes"