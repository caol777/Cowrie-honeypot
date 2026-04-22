#!/bin/bash

# ==============================================================================
# Fail2ban Setup for Project SCALPEL Honeypot
# FAU Team - eMERGE 2026 Hackathon
#
# PURPOSE: Protect the REAL SSH port (2222) only.
#          Do NOT block port 22 — that's Cowrie's honeypot port, attackers
#          SHOULD be able to reach it freely to maximize deception score.
#
#          Also reads Cowrie logs to flag IPs that attempt known malware
#          commands inside the honeypot (useful for cloud reporting).
#
# Run as root. Run AFTER setup.sh and harden_pi.sh (which moves real SSH).
# ==============================================================================

set -e

COWRIE_LOG="/home/cowrie/cowrie/var/log/cowrie/cowrie.log"
REAL_SSH_PORT=2222  # Must match harden_pi.sh

echo "[*] Installing Fail2ban..."
apt-get update -y
apt-get install -y fail2ban

# ------------------------------------------------------------------------------
# 1. Fail2ban filter for Cowrie logs (detect malicious commands in honeypot)
# ------------------------------------------------------------------------------
echo "[*] Writing Cowrie log filter..."
cat << 'EOF' > /etc/fail2ban/filter.d/cowrie-commands.conf
# Filter: flag IPs that run known malicious commands inside Cowrie
# These IPs tried to do real damage — worth escalating to cloud

[Definition]
failregex = .*CMD: wget .*<HOST>.*
            .*CMD: curl .*<HOST>.*
            .*CMD: chmod \+x.*<HOST>.*
            .*CMD: /bin/bash -i.*<HOST>.*
            .*CMD: python.*socket.*<HOST>.*
            .*CMD: cat /etc/shadow.*<HOST>.*
            .*login attempt \[.*\] failed.*<HOST>.*

ignoreregex =
EOF

# Standard filter for real SSH brute force
cat << 'EOF' > /etc/fail2ban/filter.d/real-sshd.conf
# Filter: detect brute force against the REAL SSH port (2222)
[Definition]
failregex = ^.*sshd.*Failed password for .* from <HOST> port \d+ ssh2$
            ^.*sshd.*Invalid user .* from <HOST>$
            ^.*sshd.*Connection closed by authenticating user .* <HOST>.*\[preauth\]$
ignoreregex =
EOF

# ------------------------------------------------------------------------------
# 2. Main Fail2ban config
# ------------------------------------------------------------------------------
echo "[*] Writing Fail2ban jail config..."
cat << EOF > /etc/fail2ban/jail.d/scalpel.conf
[DEFAULT]
# Global defaults
bantime  = 3600        ; 1 hour ban
findtime = 300         ; 5 minute window
maxretry = 5
backend  = systemd
banaction = iptables-multiport

# -----------------------------------------------------------------------
# Jail 1: Protect the REAL SSH port (2222)
# This is the only port fail2ban should ever block on
# -----------------------------------------------------------------------
[real-sshd]
enabled  = true
filter   = real-sshd
port     = $REAL_SSH_PORT
logpath  = /var/log/auth.log
maxretry = 3
bantime  = 7200        ; 2 hours — stiffer for actual SSH
findtime = 120

# -----------------------------------------------------------------------
# Jail 2: Cowrie malicious command tracker (logging only, no block)
# IPs that run wget/curl/reverse shells inside honeypot get flagged
# We log them but do NOT ban — banning would break deception!
# -----------------------------------------------------------------------
[cowrie-malicious]
enabled  = true
filter   = cowrie-commands
logpath  = $COWRIE_LOG
maxretry = 1
bantime  = 1          ; 1 second "ban" = effectively just logs the event
findtime = 3600
action   = %(action_)s  ; log only, minimal action

# -----------------------------------------------------------------------
# Jail 3: Recidivism — repeated offenders get long-banned from real SSH
# -----------------------------------------------------------------------
[recidivist]
enabled  = true
filter   = real-sshd
port     = $REAL_SSH_PORT
logpath  = /var/log/auth.log
maxretry = 10
bantime  = 86400       ; 24 hours
findtime = 3600
EOF

# ------------------------------------------------------------------------------
# 3. Whitelist our own team IPs (edit these before hackathon)
# ------------------------------------------------------------------------------
echo "[*] Writing whitelist (edit /etc/fail2ban/jail.d/whitelist.conf with your team IPs)..."
cat << 'EOF' > /etc/fail2ban/jail.d/whitelist.conf
[DEFAULT]
# Add your team's IPs here so you don't lock yourselves out
# Format: space-separated IPs or CIDR ranges
ignoreip = 127.0.0.1/8 ::1
# Example: ignoreip = 127.0.0.1/8 ::1 192.168.1.100 10.0.0.50
EOF

# ------------------------------------------------------------------------------
# 4. Alert script: show banned IPs and cowrie flags in real time
# ------------------------------------------------------------------------------
cat << 'SCRIPT' > /usr/local/bin/scalpel-bans
#!/bin/bash
echo "=== Fail2ban Active Bans ==="
fail2ban-client status | grep "Jail list" 
echo ""
for jail in real-sshd cowrie-malicious recidivist; do
    echo "--- Jail: $jail ---"
    fail2ban-client status $jail 2>/dev/null | grep -E "Currently banned|IP list" || echo "  (not active)"
    echo ""
done
SCRIPT
chmod +x /usr/local/bin/scalpel-bans

# ------------------------------------------------------------------------------
# 5. Enable and start
# ------------------------------------------------------------------------------
systemctl enable fail2ban
systemctl restart fail2ban

echo ""
echo "[*] Fail2ban setup complete!"
echo ""
echo "[!] IMPORTANT REMINDERS:"
echo "    - Port 22  (Cowrie) : NOT protected by fail2ban — attackers flow freely to honeypot"
echo "    - Port $REAL_SSH_PORT (Real SSH): Protected — brute force gets banned"
echo "    - Edit /etc/fail2ban/jail.d/whitelist.conf to add your team's IPs!"
echo ""
echo "[*] Live ban view : run 'scalpel-bans' anytime"
echo "[*] Service status: systemctl status fail2ban"