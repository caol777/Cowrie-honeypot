# Project SCALPEL — FAU Honeypot Stack
### eMERGE 2026 Hackathon | April 23–24 | Miami Beach Convention Center

---

## What This Is

A hybrid deception platform built on Raspberry Pi using the Cowrie honeypot framework.
The goal is to make a convincing fake SSH server that a skilled attacker can't identify as fake.

Judged on:
- **Deception Quality** — how long can you fool the red team
- **Efficiency** — how much is handled locally before hitting the cloud
- **Presentation** — 10 min presentation + 5 min Q&A on Day 3

---

## Day-Of Checklist (Do This Before Running Anything)

> Hackathon starts 10:00 AM. Honeypot IP must be in Slack by **10:20 AM**.

- [ ] Boot the Pi and get its IP address: `ip a`
- [ ] Post honeypot IP in the Slack group chat before 10:20 AM
- [ ] Find the IP of whichever laptop is serving the pickle file
- [ ] Open `bait.sh` and set `HOST_SERVER_IP` to that laptop's IP
- [ ] On the pickle-serving laptop, run: `python3 -m http.server 8000`
- [ ] Run scripts in order (see below)
- [ ] Verify Cowrie is running: `systemctl status cowrie`
- [ ] Check open ports look right: `scalpel-ports`

---

## Script Run Order

Run as **root** unless noted. Run in this exact order.

### 1. `harden_pi.sh`
Moves real SSH from port 22 → 2222. Redirects port 22 to Cowrie via iptables.
Hardens kernel, enables UFW, sets up log rotation.

> ⚠️ Run this first. Make sure you can reach port 2222 before closing your session.

```bash
sudo bash harden_pi.sh
```

### 2. `setup.sh`
Installs Cowrie and all dependencies. Creates the `cowrie` system user.
Clones the Cowrie repo and sets up the Python virtual environment.

```bash
sudo bash setup.sh
```

### 3. `bait.sh`
Run as the **cowrie user**. Configures all deception content:
- Spoofs hostname and SSH banner
- Downloads the custom filesystem pickle
- Populates honeyfs with fake passwd, shadow, crontabs, AWS credentials,
  bash history, auth logs, ARP neighbors, proc entries, and bait files

```bash
sudo -u cowrie bash bait.sh
```

### 4. `setup_vuln_scanner_decoys.sh`
Opens decoy services to make the Pi look like a real production server to scanners:
- Port 80 — fake Apache with admin panel, `.git` exposure, backup directory
- Port 21 — fake FTP with anonymous login
- Port 3306 — fake MySQL 5.7 banner
- Port 8080 — fake Tomcat Manager 401

```bash
sudo bash setup_vuln_scanner_decoys.sh
```

### 5. `setup_suricata.sh`
Installs Suricata in passive IDS mode (no blocking — attackers must reach Cowrie freely).
Loads custom rules for SSH brute force, recon scanning, reverse shells, and exfiltration attempts.

```bash
sudo bash setup_suricata.sh
```

### 6. `setup_fail2ban.sh`
Protects the **real SSH port (2222) only**.
Port 22 is intentionally left open — blocking it kills your deception score.
Also monitors Cowrie logs for malicious commands.

```bash
sudo bash setup_fail2ban.sh
```

> ⚠️ After this runs, edit `/etc/fail2ban/jail.d/whitelist.conf` and add your team's IPs
> so you don't ban yourselves.

### 7. `service.sh`
Registers Cowrie as a systemd service so it starts on boot and restarts on failure.

```bash
sudo bash service.sh
```

---

## Port Map

| Port | Service | Purpose |
|------|---------|---------|
| 22 | Cowrie (via iptables redirect) | Honeypot — attackers connect here |
| 2222 | Real SSH | Team access only |
| 80 | Fake Apache | Decoy web server |
| 21 | Fake FTP | Decoy FTP with anonymous login |
| 3306 | Fake MySQL | Decoy database banner |
| 8080 | Fake Tomcat | Decoy management interface |

---

## Useful Commands

```bash
# Check what ports are open and what nmap will see
scalpel-ports

# Live IDS alert feed from Suricata (great for demo during judging)
scalpel-alerts

# Show all fail2ban active bans
scalpel-bans

# Watch Cowrie attacker sessions in real time
tail -f /home/cowrie/cowrie/var/log/cowrie/cowrie.log

# Watch Cowrie JSON events (better for parsing)
tail -f /home/cowrie/cowrie/var/log/cowrie/cowrie.json | jq .

# Restart Cowrie after config changes
sudo systemctl restart cowrie

# Check Cowrie status
sudo systemctl status cowrie

# Check Suricata status
sudo systemctl status suricata-ids

# Manually restart Cowrie as cowrie user
sudo -u cowrie /home/cowrie/cowrie/bin/cowrie restart
```

---

## What Attackers Will See

When the red team scans or connects they should find:

- **SSH on port 22** — OpenSSH 8.4p1 Debian banner, hostname `pi-sensor-gateway`
- **Web on port 80** — Apache 2.4.51, admin panel, exposed `.git`, backup directory listing
- **FTP on port 21** — ProFTPD 1.3.5e, anonymous login, fake files
- **MySQL on port 3306** — MySQL 5.7.38 greeting
- **Tomcat on port 8080** — Tomcat 9.0.58 401 auth challenge

Once inside Cowrie via SSH they will find:

- Realistic Raspberry Pi 4 `/proc/cpuinfo`
- Populated `/etc/passwd`, `/etc/shadow`, `/etc/hosts`
- Fake crontabs referencing sensor scripts and database backups
- `.bash_history` showing prior admin activity
- `/var/www/html/config.php` with a database password
- `/root/.aws/credentials` with a plausible AWS key
- `/root/.ssh/known_hosts` showing connections to other nodes
- `/var/log/auth.log` showing prior legitimate logins
- ARP neighbors at `10.1.10.21`, `10.1.10.22`, `10.1.10.55`

---

## Key Variables (Day-Of)

| Variable | File | What It Is |
|----------|------|------------|
| `HOST_SERVER_IP` | `bait.sh` line 28 | IP of laptop serving the pickle file |
| Whitelist IPs | `/etc/fail2ban/jail.d/whitelist.conf` | Your team's IPs — add after running fail2ban setup |
| AWS endpoint | TBD day-of | Whatever AWS gives you — add to your cloud tier script |

---

## Contact

Victoria Jolly — jollyv@usf.edu | 919.886.8963

For questions during the event use the **eMERGE 2026 Hackathon** Slack group.