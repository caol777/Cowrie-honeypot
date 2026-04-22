#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Ensure the script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "[-] Error: Please run this script as root (use sudo)."
  exit 1
fi

echo "[*] Creating the systemd service file for Cowrie..."

# Write the service definition
cat << 'EOF' > /etc/systemd/system/cowrie.service
[Unit]
Description=Cowrie SSH/Telnet Honeypot
Documentation=https://cowrie.readthedocs.io/
After=network.target

[Service]
Type=forking
User=cowrie
Group=cowrie
WorkingDirectory=/home/cowrie/cowrie
# Ensure it uses the virtual environment binary
ExecStart=/home/cowrie/cowrie/cowrie-env/bin/cowrie start
ExecStop=/home/cowrie/cowrie/cowrie-env/bin/cowrie stop
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "[*] Setting correct permissions on the service file..."
chmod 644 /etc/systemd/system/cowrie.service

echo "[*] Reloading systemd daemon to read the new service..."
systemctl daemon-reload

echo "[*] Enabling Cowrie to start automatically on boot..."
systemctl enable cowrie

echo "[*] Starting the Cowrie service now..."
systemctl start cowrie

echo "[+] Setup complete! Cowrie is now running as a service."
echo "[+] Checking status..."
systemctl status cowrie --no-pager
