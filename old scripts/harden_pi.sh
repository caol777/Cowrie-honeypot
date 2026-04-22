#!/bin/bash

# ==============================================================================
# Pi Hardening Script for Project SCALPEL
# FAU Team - eMERGE 2026 Hackathon
#
# PURPOSE: Secure the REAL system so only the honeypot surface is exposed.
#   - Moves real SSH from port 22 → 2222 (team access preserved)
#   - Routes all port 22 traffic to Cowrie via iptables (authbind not needed)
#   - Disables unnecessary services to free up Pi CPU/RAM for Cowrie
#   - Locks down /proc and kernel params to prevent info leakage
#   - Enables UFW with correct rules
#
# !! RUN THIS FIRST before other setup scripts !!
# !! Make sure you know port 2222 before running or you may lock yourself out !!
#
# Run as root.
# ==============================================================================

set -e

REAL_SSH_PORT=2222
COWRIE_SSH_PORT=2222   # Port Cowrie listens on internally (its listen_port)
HONEYPOT_PORT=22       # Port attackers connect to externally

echo "================================================================"
echo " SCALPEL Pi Hardening Script"
echo " Real SSH will move to port $REAL_SSH_PORT"
echo " Port 22 will route to Cowrie"
echo "================================================================"
echo ""
echo "[!] WARNING: If this is a remote session, ensure you can reach"
echo "    port $REAL_SSH_PORT before confirming."
read -rp "Type 'yes' to continue: " confirm
[ "$confirm" = "yes" ] || { echo "Aborted."; exit 1; }

# ==============================================================================
# 1. Move real SSH to port 2222
# ==============================================================================
echo "[*] Moving real SSH daemon to port $REAL_SSH_PORT..."

# Backup original config
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup.$(date +%Y%m%d)

# Update port
sed -i "s/^#Port 22/Port $REAL_SSH_PORT/" /etc/ssh/sshd_config
sed -i "s/^Port 22$/Port $REAL_SSH_PORT/" /etc/ssh/sshd_config

# If neither matched (port line was absent), append it
grep -q "^Port $REAL_SSH_PORT" /etc/ssh/sshd_config || echo "Port $REAL_SSH_PORT" >> /etc/ssh/sshd_config

# Harden real SSH (no password auth, no root login)
cat << EOF >> /etc/ssh/sshd_config

# SCALPEL hardening additions
PermitRootLogin no
PasswordAuthentication no
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowTcpForwarding no
EOF

systemctl restart sshd
echo "[+] Real SSH now on port $REAL_SSH_PORT"

# ==============================================================================
# 2. Configure Cowrie to listen on port 2222 internally, authbind port 22
#    (Cowrie non-root can't bind <1024, so we use iptables redirect instead)
# ==============================================================================
echo "[*] Configuring Cowrie listen port and iptables redirect..."

COWRIE_CFG="/home/cowrie/cowrie/etc/cowrie.cfg"
if [ -f "$COWRIE_CFG" ]; then
    # Set Cowrie to listen on 2223 internally (avoids conflict with real SSH on 2222)
    sed -i 's/^listen_port =.*/listen_port = 2223/' "$COWRIE_CFG"
    grep -q "^listen_port" "$COWRIE_CFG" || echo "listen_port = 2223" >> "$COWRIE_CFG"
    echo "[+] Cowrie set to internal listen port 2223"
else
    echo "[!] cowrie.cfg not found — run setup.sh first, then re-run this script"
    echo "    Skipping Cowrie port config. You must set listen_port = 2223 manually."
fi

# iptables: redirect inbound port 22 → 2223 (where Cowrie listens)
echo "[*] Setting up iptables redirect: 22 → 2223 (Cowrie)..."
iptables -t nat -A PREROUTING -p tcp --dport 22 -j REDIRECT --to-port 2223
iptables -t nat -A OUTPUT -p tcp --dport 22 -j REDIRECT --to-port 2223

# Persist iptables rules across reboots
apt-get install -y iptables-persistent
netfilter-persistent save

echo "[+] Port 22 → 2223 (Cowrie) redirect active"

# ==============================================================================
# 3. Disable unnecessary Pi services (free up RAM/CPU for Cowrie + Suricata)
# ==============================================================================
echo "[*] Disabling unnecessary services..."

SERVICES_TO_DISABLE=(
    bluetooth
    avahi-daemon
    triggerhappy
    cups
    cups-browsed
    ModemManager
    wpa_supplicant   # disable if using wired ethernet only
)

for svc in "${SERVICES_TO_DISABLE[@]}"; do
    if systemctl list-unit-files | grep -q "^$svc.service"; then
        systemctl disable --now "$svc" 2>/dev/null && echo "  [+] Disabled: $svc" || true
    fi
done

# ==============================================================================
# 4. Kernel hardening via sysctl
# ==============================================================================
echo "[*] Applying kernel security params..."
cat << 'EOF' > /etc/sysctl.d/99-scalpel.conf
# SCALPEL Pi Hardening

# Hide kernel pointers from non-root (stops info leakage via /proc)
kernel.kptr_restrict = 2

# Disable dmesg for non-root
kernel.dmesg_restrict = 1

# Ignore ICMP redirects (prevent MITM)
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0

# Ignore broadcast pings (smurf protection)
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Enable SYN flood protection
net.ipv4.tcp_syncookies = 1

# Don't forward packets (we're not a router)
net.ipv4.ip_forward = 0

# Log martian packets (unusual source IPs — useful for Suricata correlation)
net.ipv4.conf.all.log_martians = 1

# Protect against time-wait assassination
net.ipv4.tcp_rfc1337 = 1

# Disable IPv6 (reduces attack surface on Pi)
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
EOF

sysctl -p /etc/sysctl.d/99-scalpel.conf

# ==============================================================================
# 5. UFW firewall rules
# ==============================================================================
echo "[*] Configuring UFW firewall..."
apt-get install -y ufw

ufw --force reset

# Default policy: deny inbound, allow outbound
ufw default deny incoming
ufw default allow outgoing

# Real SSH — team access only (restrict source IP if you know it)
ufw allow $REAL_SSH_PORT/tcp comment 'Real SSH - team access'

# Honeypot ports — wide open for attackers
ufw allow 22/tcp    comment 'Cowrie honeypot SSH (via iptables redirect)'
ufw allow 80/tcp    comment 'Decoy Apache'
ufw allow 21/tcp    comment 'Decoy FTP'
ufw allow 3306/tcp  comment 'Decoy MySQL'
ufw allow 8080/tcp  comment 'Decoy Tomcat'

# Allow outbound to AWS (cloud brain / tier 2)
ufw allow out 443/tcp comment 'AWS HTTPS outbound'

ufw --force enable
echo "[+] UFW enabled"

# ==============================================================================
# 6. Restrict /proc access (hides real process list from honeypot escapees)
# ==============================================================================
echo "[*] Restricting /proc visibility..."
if ! grep -q "hidepid=2" /etc/fstab; then
    echo "proc /proc proc defaults,hidepid=2 0 0" >> /etc/fstab
    mount -o remount,hidepid=2 /proc 2>/dev/null || echo "  [!] /proc remount skipped (reboot to apply)"
fi

# ==============================================================================
# 7. Rotate Cowrie logs daily so they don't fill the Pi SD card
# ==============================================================================
echo "[*] Setting up Cowrie log rotation..."
cat << 'EOF' > /etc/logrotate.d/cowrie
/home/cowrie/cowrie/var/log/cowrie/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    create 0640 cowrie cowrie
    postrotate
        systemctl kill -s HUP cowrie 2>/dev/null || true
    endscript
}
EOF

# ==============================================================================
# Summary
# ==============================================================================
echo ""
echo "================================================================"
echo " SCALPEL Pi Hardening Complete"
echo "================================================================"
echo ""
echo "  Real SSH          : port $REAL_SSH_PORT  (key auth only, no root login)"
echo "  Cowrie honeypot   : port 22 → 2223 (iptables redirect)"
echo "  Decoy ports open  : 80, 21, 3306, 8080"
echo "  Kernel hardened   : yes (/etc/sysctl.d/99-scalpel.conf)"
echo "  UFW               : enabled"
echo "  Log rotation      : daily, 7-day retention"
echo ""
echo "[!] REMEMBER: SSH into this Pi on port $REAL_SSH_PORT from now on"
echo "[!] Test a new SSH session on port $REAL_SSH_PORT BEFORE closing this one"
echo ""
echo "Recommended run order:"
echo "  1. harden_pi.sh          <- you just ran this"
echo "  2. setup.sh              <- install Cowrie"
echo "  3. bait.sh               <- configure deception"
echo "  4. setup_vuln_scanner_decoys.sh"
echo "  5. setup_suricata.sh"
echo "  6. setup_fail2ban.sh"
echo "  7. service.sh            <- start Cowrie as a service"