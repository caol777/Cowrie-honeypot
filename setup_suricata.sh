#!/bin/bash

# ==============================================================================
# Suricata IDS Setup for Project SCALPEL Honeypot
# FAU Team - eMERGE 2026 Hackathon
#
# PURPOSE: Passive IDS only — logs attacker behavior without blocking
# honeypot traffic. Feeds intelligence to Cowrie and AWS (Tier 2).
#
# Run as root. Run AFTER setup.sh and bait.sh.
# ==============================================================================

set -e

SURICATA_LOG="/var/log/suricata"
RULES_DIR="/etc/suricata/rules"
COWRIE_LOG="/home/cowrie/cowrie/var/log/cowrie"
IFACE=$(ip route | grep default | awk '{print $5}' | head -1)

echo "[*] Detected network interface: $IFACE"
echo "[*] Installing Suricata..."
apt-get update -y
apt-get install -y suricata jq

# ------------------------------------------------------------------------------
# 1. Base Suricata config — passive/IDS mode only (af-packet, no inline/IPS)
# ------------------------------------------------------------------------------
echo "[*] Writing Suricata config..."
cat << EOF > /etc/suricata/suricata.yaml
%YAML 1.1
---

# Project SCALPEL - Suricata IDS Config (Pi-optimized, passive mode)

vars:
  address-groups:
    HOME_NET: "[192.168.0.0/16,10.0.0.0/8,172.16.0.0/12]"
    EXTERNAL_NET: "!\$HOME_NET"
  port-groups:
    SSH_PORTS: "22"
    HTTP_PORTS: "80"
    HTTPS_PORTS: "443"

default-log-dir: $SURICATA_LOG

outputs:
  - fast:
      enabled: yes
      filename: fast.log
      append: yes
  - eve-log:
      enabled: yes
      filename: eve.json
      filetype: regular
      types:
        - alert:
            payload: yes
            payload-printable: yes
            metadata: yes
        - http:
            extended: yes
        - ssh
        - flow
        - stats:
            totals: yes
            threads: no

af-packet:
  - interface: $IFACE
    threads: 1          # Pi-friendly: single thread
    cluster-id: 99
    cluster-type: cluster_flow
    defrag: yes
    use-mmap: yes
    tpacket-v3: yes

# Pi memory optimization
max-pending-packets: 512

logging:
  default-log-level: notice
  outputs:
    - console:
        enabled: no
    - file:
        enabled: yes
        level: info
        filename: /var/log/suricata/suricata.log

default-rule-path: $RULES_DIR
rule-files:
  - scalpel-ssh.rules
  - scalpel-recon.rules
  - scalpel-exfil.rules

app-layer:
  protocols:
    ssh:
      enabled: yes
    http:
      enabled: yes

# Disable unused protocols to save Pi CPU
    tls:
      enabled: no
    smtp:
      enabled: no
    ftp:
      enabled: no
    dns:
      tcp:
        enabled: no
      udp:
        enabled: no
EOF

# ------------------------------------------------------------------------------
# 2. Custom rules — SSH honeypot focused
# ------------------------------------------------------------------------------
echo "[*] Writing SSH detection rules..."
mkdir -p $RULES_DIR

cat << 'EOF' > $RULES_DIR/scalpel-ssh.rules
# SCALPEL SSH Rules — detect attacker behavior inside honeypot

# SSH brute force: >5 attempts in 60s
alert tcp $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Brute Force Attempt"; flow:to_server,established; content:"SSH"; threshold:type threshold, track by_src, count 5, seconds 60; sid:9000001; rev:1;)

# SSH version scanning (common scanner fingerprints)
alert tcp $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Scanner - Masscan"; flow:to_server; content:"SSH-2.0-masscan"; sid:9000002; rev:1;)
alert tcp $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Scanner - Nmap"; flow:to_server; content:"SSH-2.0-OpenSSH_"; content:"nmap"; nocase; sid:9000003; rev:1;)
alert tcp $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Scanner - Paramiko"; flow:to_server; content:"SSH-2.0-paramiko"; sid:9000004; rev:1;)
alert tcp $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Scanner - Golang"; flow:to_server; content:"SSH-2.0-Go"; sid:9000005; rev:1;)
alert tcp $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Scanner - libssh"; flow:to_server; content:"SSH-2.0-libssh"; sid:9000006; rev:1;)

# Empty password / short password attempts
alert tcp $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Auth with common credential"; flow:to_server,established; content:"root"; content:"password"; distance:0; sid:9000007; rev:1;)

# Attacker trying to escape (common post-exploitation commands via SSH)
alert ssh $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Command - wget/curl download"; flow:to_server,established; content:"wget "; sid:9000010; rev:1;)
alert ssh $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Command - curl download"; flow:to_server,established; content:"curl "; sid:9000011; rev:1;)
alert ssh $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Command - chmod+x"; flow:to_server,established; content:"chmod +x"; sid:9000012; rev:1;)
alert ssh $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Command - python reverse shell"; flow:to_server,established; content:"python"; content:"socket"; sid:9000013; rev:1;)
alert ssh $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Command - bash reverse shell"; flow:to_server,established; content:"/dev/tcp/"; sid:9000014; rev:1;)
alert ssh $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Command - cat /etc/passwd"; flow:to_server,established; content:"cat /etc/passwd"; sid:9000015; rev:1;)
alert ssh $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Command - cat /etc/shadow"; flow:to_server,established; content:"cat /etc/shadow"; sid:9000016; rev:1;)
alert ssh $EXTERNAL_NET any -> $HOME_NET 22 (msg:"SCALPEL SSH Command - AWS cred access"; flow:to_server,established; content:".aws/credentials"; sid:9000017; rev:1;)
EOF

cat << 'EOF' > $RULES_DIR/scalpel-recon.rules
# SCALPEL Recon Rules — detect port scanning & enumeration

# Nmap SYN scan (half-open)
alert tcp $EXTERNAL_NET any -> $HOME_NET any (msg:"SCALPEL Nmap SYN Scan Detected"; flags:S; threshold:type threshold, track by_src, count 20, seconds 5; sid:9001001; rev:1;)

# Nmap OS detection probe
alert tcp $EXTERNAL_NET any -> $HOME_NET any (msg:"SCALPEL Nmap OS Detection Probe"; flags:SF; sid:9001002; rev:1;)

# UDP port scan
alert udp $EXTERNAL_NET any -> $HOME_NET any (msg:"SCALPEL UDP Port Scan"; threshold:type threshold, track by_src, count 20, seconds 5; sid:9001003; rev:1;)

# HTTP directory busting (gobuster/dirb/dirbuster)
alert http $EXTERNAL_NET any -> $HOME_NET 80 (msg:"SCALPEL HTTP Directory Brute Force"; http.user_agent; content:"gobuster"; nocase; sid:9001010; rev:1;)
alert http $EXTERNAL_NET any -> $HOME_NET 80 (msg:"SCALPEL HTTP Dir Scan - dirb"; http.user_agent; content:"dirb"; nocase; sid:9001011; rev:1;)
alert http $EXTERNAL_NET any -> $HOME_NET 80 (msg:"SCALPEL HTTP Rapid Requests"; threshold:type threshold, track by_src, count 30, seconds 5; sid:9001012; rev:1;)

# Nikto web scanner
alert http $EXTERNAL_NET any -> $HOME_NET 80 (msg:"SCALPEL Nikto Web Scanner"; http.user_agent; content:"Nikto"; nocase; sid:9001013; rev:1;)
EOF

cat << 'EOF' > $RULES_DIR/scalpel-exfil.rules
# SCALPEL Exfiltration Rules — detect attacker trying to pull data out

# Large outbound data transfer (possible exfil)
alert tcp $HOME_NET any -> $EXTERNAL_NET any (msg:"SCALPEL Possible Data Exfiltration - Large Transfer"; dsize:>8000; threshold:type threshold, track by_dst, count 5, seconds 30; sid:9002001; rev:1;)

# DNS exfiltration attempt (long subdomain)
alert dns $HOME_NET any -> any 53 (msg:"SCALPEL DNS Exfiltration Attempt"; dns.query; content:"."; byte_test:1,>,50,0; sid:9002002; rev:1;)

# Attacker pulling files via HTTP from known paste sites
alert http $HOME_NET any -> $EXTERNAL_NET 80 (msg:"SCALPEL Outbound Pastebin Access"; http.host; content:"pastebin.com"; sid:9002010; rev:1;)
alert http $HOME_NET any -> $EXTERNAL_NET 80 (msg:"SCALPEL Outbound transfer.sh Access"; http.host; content:"transfer.sh"; sid:9002011; rev:1;)
EOF

# ------------------------------------------------------------------------------
# 3. Systemd service — start Suricata in IDS mode on boot
# ------------------------------------------------------------------------------
echo "[*] Configuring Suricata systemd service..."
cat << EOF > /etc/systemd/system/suricata-ids.service
[Unit]
Description=Suricata IDS - Project SCALPEL
After=network.target cowrie.service
Wants=cowrie.service

[Service]
Type=simple
ExecStart=/usr/bin/suricata -c /etc/suricata/suricata.yaml -i $IFACE --pidfile /run/suricata.pid
ExecReload=/bin/kill -USR2 \$MAINPID
Restart=on-failure
RestartSec=10
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable suricata-ids
systemctl start suricata-ids

# ------------------------------------------------------------------------------
# 4. Quick alert summary script (useful during judging demo)
# ------------------------------------------------------------------------------
cat << 'SCRIPT' > /usr/local/bin/scalpel-alerts
#!/bin/bash
# Show live Suricata alerts in a readable format — run this during demo
echo "=== SCALPEL Live IDS Alerts (last 50) ==="
if [ -f /var/log/suricata/eve.json ]; then
    cat /var/log/suricata/eve.json | \
        jq -r 'select(.event_type=="alert") | 
        "[\(.timestamp[11:19])] SRC:\(.src_ip):\(.src_port) -> DST:\(.dest_ip):\(.dest_port) | \(.alert.signature)"' \
        2>/dev/null | tail -50
else
    echo "No alerts yet. Is Suricata running? Check: systemctl status suricata-ids"
fi
SCRIPT
chmod +x /usr/local/bin/scalpel-alerts

echo ""
echo "[*] Suricata IDS setup complete!"
echo "[*] Interface monitored : $IFACE"
echo "[*] Logs                : /var/log/suricata/eve.json"
echo "[*] Live alert view     : run 'scalpel-alerts' anytime"
echo "[*] Service status      : systemctl status suricata-ids"