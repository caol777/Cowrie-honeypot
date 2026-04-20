#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "[*] Updating system packages..."
apt-get update -y

echo "[*] Installing Cowrie dependencies and requested security/networking tools..."
apt-get install -y \
    git python3-venv libssl-dev libffi-dev build-essential \
    libpython3-dev python3-minimal authbind tshark \
    sudo net-tools iptables iproute2 sed curl wget bash gcc \
    debsums tmux htop nmap ufw rkhunter whowatch gzip make \
    procps socat tar auditd rsyslog tcpdump unhide strace

echo "[*] Creating 'cowrie' user account..."
# Create the user without a password and without prompting for user details
adduser --disabled-password --gecos "" cowrie

echo "[*] Switching to 'cowrie' user to clone and build environment..."
# Run the following block of commands as the cowrie user
sudo -u cowrie bash -c '
    cd /home/cowrie
    echo "[*] Cloning the Cowrie repository..."
    git clone https://github.com/cowrie/cowrie
    cd cowrie

    echo "[*] Setting up the Python virtual environment..."
    python3 -m venv cowrie-env
    source cowrie-env/bin/activate

    echo "[*] Upgrading pip and installing requirements..."
    pip install --upgrade pip
    pip install --upgrade -r requirements.txt
    
    echo "[*] Installing Cowrie package..."
    pip install -e .

    echo "[*] Copying default configuration file..."
    cp etc/cowrie.cfg.dist etc/cowrie.cfg
'

echo "[*] Cowrie installation complete!"
