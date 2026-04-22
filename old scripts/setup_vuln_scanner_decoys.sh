#!/bin/bash

# ==============================================================================
# Vulnerability Scanner Decoy Setup for Project SCALPEL
# FAU Team - eMERGE 2026 Hackathon
#
# PURPOSE: Make your Raspberry Pi honeypot look like a real, slightly-
#          vulnerable production server to any vulnerability scanner
#          (nmap, Nikto, Shodan, OpenVAS, etc.)
#
# This DIRECTLY improves your Deception Quality score — the red team
# will see a convincing target, not a bare Pi.
#
# Opens decoy ports with realistic banners:
#   80   — Apache web server (fake admin panel)
#   3306 — MySQL (fake, banner only)
#   8080 — Tomcat management (irresistible to attackers)
#   21   — FTP (vsftpd with anonymous login lure)
#
# Run as root. Run AFTER setup.sh and bait.sh.
# ==============================================================================

set -e

COWRIE_DIR="/home/cowrie/cowrie"

echo "[*] Installing decoy service dependencies..."
apt-get update -y
apt-get install -y apache2 socat netcat-openbsd python3 vsftpd

# ==============================================================================
# DECOY 1: Apache Web Server — Port 80
# Serve a realistic-looking IoT/sensor dashboard with juicy fake content
# ==============================================================================
echo "[*] Setting up fake web server on port 80..."

# Fake index page (looks like a real sensor management portal)
cat << 'EOF' > /var/www/html/index.html
<!DOCTYPE html>
<html>
<head><title>Sensor Gateway - Admin Portal</title></head>
<body>
<h2>Distributed Sensor Network - Node Alpha</h2>
<p>Management Interface v2.3.1</p>
<p><a href="/admin/">Admin Panel</a> | <a href="/api/status">API Status</a> | <a href="/phpmyadmin/">Database</a></p>
<p style="color:gray;font-size:0.8em;">Apache/2.4.51 (Debian) PHP/7.4.26</p>
</body>
</html>
EOF

mkdir -p /var/www/html/admin
cat << 'EOF' > /var/www/html/admin/index.html
<!DOCTYPE html>
<html>
<head><title>Admin Login</title></head>
<body>
<h2>Admin Login</h2>
<form method="post" action="/admin/login.php">
  Username: <input type="text" name="user"><br>
  Password: <input type="password" name="pass"><br>
  <input type="submit" value="Login">
</form>
</body>
</html>
EOF

# Fake robots.txt — attackers ALWAYS check this
cat << 'EOF' > /var/www/html/robots.txt
User-agent: *
Disallow: /admin/
Disallow: /backup/
Disallow: /api/internal/
Disallow: /.git/
Disallow: /config/
EOF

# Fake backup file listing (extremely attractive to scanners)
mkdir -p /var/www/html/backup
cat << 'EOF' > /var/www/html/backup/index.html
<!DOCTYPE html>
<html><head><title>Index of /backup</title></head>
<body>
<h1>Index of /backup</h1>
<pre>
      Name              Last modified      Size
---------------------------------------------------------------------------
      db_backup_2026-04-01.sql.gz        01-Apr-2026 03:00   2.4M
      config_backup.tar.gz               15-Mar-2026 12:00   841K
      users_export.csv                   28-Feb-2026 08:00   124K
</pre>
</body>
</html>
EOF

# Fake .git exposure (top scanner finding)
mkdir -p /var/www/html/.git
cat << 'EOF' > /var/www/html/.git/config
[core]
    repositoryformatversion = 0
    filemode = true
    bare = false
[remote "origin"]
    url = git@github.com:sensor-corp/node-alpha.git
    fetch = +refs/heads/*:refs/refs/remotes/origin/*
[branch "main"]
    remote = origin
    merge = refs/heads/main
EOF

# Set Apache server header to look like a slightly old version
cat << 'EOF' > /etc/apache2/conf-available/scalpel-headers.conf
ServerTokens Full
ServerSignature On
Header set Server "Apache/2.4.51 (Debian)"
Header set X-Powered-By "PHP/7.4.26"
EOF

a2enconf scalpel-headers 2>/dev/null || true
a2enmod headers 2>/dev/null || true
systemctl enable apache2
systemctl restart apache2

# ==============================================================================
# DECOY 2: Fake MySQL Banner — Port 3306
# Socat listens and sends a realistic MySQL greeting packet
# Scanners will report "MySQL 5.7.x detected"
# ==============================================================================
echo "[*] Setting up fake MySQL banner on port 3306..."

# MySQL greeting bytes: realistic 5.7.38 server greeting
MYSQL_BANNER=$'\x4a\x00\x00\x00\x0a\x35\x2e\x37\x2e\x33\x38\x2d\x30\x75\x62\x75\x6e\x74\x75\x30\x2e\x31\x38\x2e\x30\x34\x2e\x31\x00'

cat << 'SCRIPT' > /usr/local/bin/fake-mysql
#!/bin/bash
# Sends a fake MySQL greeting to any connection then closes
while true; do
    echo -ne "\x4a\x00\x00\x00\x0a5.7.38-0ubuntu0.18.04.1\x00\x01\x00\x00\x00\x52\x7a\x7e\x7c\x77\x76\x5b\x4a\x00\xff\xf7\x08\x02\x00\x7f\x80\x15\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x72\x6f\x6f\x74\x00\x00\x00" \
    | nc -l -p 3306 -q 1 2>/dev/null
done
SCRIPT
chmod +x /usr/local/bin/fake-mysql

cat << 'EOF' > /etc/systemd/system/fake-mysql.service
[Unit]
Description=SCALPEL Fake MySQL Decoy - Port 3306
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/fake-mysql
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

# ==============================================================================
# DECOY 3: Fake Tomcat Manager — Port 8080
# Apache Tomcat management interface is one of the most targeted services
# ==============================================================================
echo "[*] Setting up fake Tomcat on port 8080..."

cat << 'SCRIPT' > /usr/local/bin/fake-tomcat
#!/bin/bash
# Minimal HTTP server that returns a convincing Tomcat manager page
RESPONSE='HTTP/1.1 401 Unauthorized\r\nWWW-Authenticate: Basic realm="Tomcat Manager Application"\r\nServer: Apache-Coyote/1.1\r\nContent-Type: text/html;charset=utf-8\r\nContent-Length: 2474\r\n\r\n<!DOCTYPE html><html><head><title>401 Unauthorized</title></head><body><h1>401 Unauthorized</h1><p>You are not authorized to view this page. Please check your credentials and try again.</p><hr/><address>Apache Tomcat/9.0.58</address></body></html>'

while true; do
    echo -e "$RESPONSE" | nc -l -p 8080 -q 1 2>/dev/null
done
SCRIPT
chmod +x /usr/local/bin/fake-tomcat

cat << 'EOF' > /etc/systemd/system/fake-tomcat.service
[Unit]
Description=SCALPEL Fake Tomcat Decoy - Port 8080
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/fake-tomcat
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

# ==============================================================================
# DECOY 4: FTP with anonymous login (vsftpd)
# Anonymous FTP is a classic scanner finding — also logs credentials tried
# ==============================================================================
echo "[*] Setting up fake FTP on port 21..."

cat << 'EOF' > /etc/vsftpd.conf
listen=YES
anonymous_enable=YES
local_enable=NO
write_enable=NO
anon_upload_enable=NO
anon_mkdir_write_enable=NO
dirmessage_enable=YES
xferlog_enable=YES
xferlog_file=/var/log/vsftpd.log
connect_from_port_20=YES
ftpd_banner=220 ProFTPD 1.3.5e Server (Sensor Node FTP) [sensor-gateway]
# Log all attempts
log_ftp_protocol=YES
vsftpd_log_file=/var/log/vsftpd.log
EOF

# Create some enticing fake files in the FTP root
mkdir -p /srv/ftp/pub
cat << 'EOF' > /srv/ftp/pub/README.txt
Sensor Network Data Archive
Node: Alpha | Region: Southeast
Contact: admin@sensor-corp.local
EOF
echo "node_config_backup_2026.tar.gz placeholder" > /srv/ftp/pub/node_config_backup_2026.tar.gz
chmod -R 755 /srv/ftp

systemctl enable vsftpd
systemctl restart vsftpd

# ==============================================================================
# Enable all decoy services
# ==============================================================================
systemctl daemon-reload
systemctl enable fake-mysql fake-tomcat
systemctl start fake-mysql fake-tomcat

# ==============================================================================
# UFW rules — OPEN decoy ports, keep real SSH (2222) restricted
# Note: port 22 must stay open for Cowrie — do not firewall it
# ==============================================================================
echo "[*] Configuring firewall rules for decoy ports..."
if command -v ufw &>/dev/null; then
    ufw allow 22/tcp    comment 'Cowrie honeypot SSH'
    ufw allow 80/tcp    comment 'Decoy Apache'
    ufw allow 21/tcp    comment 'Decoy FTP'
    ufw allow 3306/tcp  comment 'Decoy MySQL'
    ufw allow 8080/tcp  comment 'Decoy Tomcat'
    ufw allow 2222/tcp  comment 'Real SSH (team access only)'
fi

# ==============================================================================
# Scanner profile summary script — shows what nmap will see
# ==============================================================================
cat << 'SCRIPT' > /usr/local/bin/scalpel-ports
#!/bin/bash
echo "=== SCALPEL Open Decoy Ports ==="
echo ""
ss -tlnp | grep -E ":(22|80|21|3306|8080|2222) " | awk '{print $4, $6}' | sort
echo ""
echo "=== Expected nmap profile against this host ==="
echo "  22/tcp   open  ssh     OpenSSH 8.4p1 Debian (Cowrie)"
echo "  21/tcp   open  ftp     ProFTPD 1.3.5e"
echo "  80/tcp   open  http    Apache httpd 2.4.51 (Debian)"
echo "  3306/tcp open  mysql   MySQL 5.7.38"
echo "  8080/tcp open  http    Apache Tomcat 9.0.58"
echo "  2222/tcp open  ssh     OpenSSH (real, team access)"
SCRIPT
chmod +x /usr/local/bin/scalpel-ports

echo ""
echo "[*] Vulnerability scanner decoy setup complete!"
echo ""
echo "  Port 22   - Cowrie SSH honeypot (main deception surface)"
echo "  Port 80   - Fake Apache with admin panel, .git, backups"
echo "  Port 21   - Fake vsftpd with anonymous login"
echo "  Port 3306 - Fake MySQL 5.7 banner"
echo "  Port 8080 - Fake Tomcat Manager 401"
echo "  Port 2222 - Real SSH (your team access)"
echo ""
echo "[*] Port status: run 'scalpel-ports' anytime"