#!/bin/bash

set -e

echo "[*] Creating the systemd service file for Cowrie..."

# Using 'cat << EOF' is a great bash trick to write multiple lines to a file at once
cat << 'EOF' > /etc/systemd/system/cowrie.service
[Unit]
Description=Cowrie SSH/Telnet Honeypot
After=network.target

[Service]
Type=forking
User=cowrie
Group=cowrie
WorkingDirectory=/home/cowrie/cowrie
ExecStart=/home/cowrie/cowrie/cowrie-env/bin/cowrie start
ExecStop=/home/cowrie/cowrie/cowrie-env/bin/cowrie stop
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "[*] Reloading systemd daemon..."
systemctl daemon-reload

echo "[*] Enabling Cowrie to start on boot..."
systemctl enable cowrie

echo "[*] Starting the Cowrie service..."
systemctl start cowrie

echo "[*] Setup complete! Here is the current status:"
systemctl status cowrie --no-pager
