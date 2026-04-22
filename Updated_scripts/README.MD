# Project SCALPEL — FAU Honeypot Stack
### eMERGE 2026 Hackathon | April 23–24 | Miami Beach Convention Center

---

## Scoring (Know This Cold)

| Category | Weight | What It Means |
|----------|--------|---------------|
| Interaction Realism | 40% | How convincing your responses are to the red team |
| Edge Efficiency | 40% | How many commands you handle locally vs escalating to AWS |
| Presentation | 20% | 10 min presentation + 5 min Q&A |

**Final Score = 0.4 × realism + 0.4 × edge_efficiency + 0.2 × presentation**

Every cloud escalation is detectable via latency spike. Minimize them.
Teams start with 50 realism points — each red team finding costs 1 point.
A system crash costs 10 points.

---

## What The Pi Has Pre-Installed

- Cowrie honeypot (already installed, already running)
- Cowrie user: `cowrie` / password: `honeypot`
- Honeypot credentials the red team uses: `root` / `root` on port `2222`
- Real Pi access: `pi` / `raspberry` on port `22`
- Filesystem pickle already at: `~/cowrie/share/cowrie/fs.pickle`

**Do not reimage the Pi. Do not change the credentials.**

---

## Four-Tier Intelligence Architecture

```
Attacker command
      │
      ▼
┌─────────────────────────────────┐
│ Tier 1 — Static Lookup Table    │  ~0ms   whoami, uname, cat /etc/passwd...
│ tier1_static.py                 │
└────────────────┬────────────────┘
                 │ miss
                 ▼
┌─────────────────────────────────┐
│ Tier 2 — Rule-Based Classifier  │  ~1ms   ps aux, netstat, systemctl...
│ tier2_classifier.py             │
└────────────────┬────────────────┘
                 │ miss
                 ▼
┌─────────────────────────────────┐
│ Tier 3 — Local Ollama LLM       │  1-3s   dynamic, unpredictable commands
│ tier3_ollama_tier4_cloud.py     │
└────────────────┬────────────────┘
                 │ too complex / too slow
                 ▼
┌─────────────────────────────────┐
│ Tier 4 — AWS Bedrock            │  cloud  last resort only
│ tier3_ollama_tier4_cloud.py     │
└─────────────────────────────────┘
```

Goal: handle 80%+ of commands in Tier 1/2. Tier 4 should be rare.

---

## Scripts — What Each One Does

| Script | Run As | Purpose |
|--------|--------|---------|
| `bait.sh` | cowrie user | Configures honeyfs, hostname, SSH banner |
| `install_ollama.sh` | root | Installs Ollama, pulls model, warms it up |
| `cowrie_intercept.py` | — | Core routing logic — copy to Cowrie commands dir |
| `tier1_static.py` | — | Static lookup table for instant responses |
| `tier2_classifier.py` | — | Rule-based handler for structured commands |
| `tier3_ollama_tier4_cloud.py` | — | Local LLM + AWS Bedrock escalation |
| `health_check.sh` | root | Verify everything works before gauntlet |

---

## Run Order (Day Of)

### Step 1 — Get Pi IP and post to Slack (before 10:20 AM)
```bash
ip a
# Post IP in the eMERGE 2026 Hackathon Slack channel immediately
```

### Step 2 — Run bait.sh as cowrie user
```bash
ssh cowrie@<pi_ip>          # password: honeypot
bash bait.sh
```

### Step 3 — Install Ollama as root
```bash
ssh pi@<pi_ip>              # password: raspberry
sudo bash install_ollama.sh
```

### Step 4 — Install intercept layer
```bash
cp cowrie_intercept.py ~/cowrie/cowrie/commands/
cp tier1_static.py ~/cowrie/cowrie/commands/
cp tier2_classifier.py ~/cowrie/cowrie/commands/
cp tier3_ollama_tier4_cloud.py ~/cowrie/cowrie/commands/
~/cowrie/bin/cowrie restart
```

### Step 5 — Fill in AWS endpoint (once organizers give credentials)
```bash
# Edit tier3_ollama_tier4_cloud.py
# Update AWS_BEDROCK_ENDPOINT and AWS_API_KEY at the top
```

### Step 6 — Run health check
```bash
sudo bash health_check.sh
```

---

## Day-Of Checklist

- [ ] Pi IP posted in Slack before 10:20 AM
- [ ] bait.sh run as cowrie user
- [ ] Ollama installed and model loaded in memory
- [ ] Tier files copied to ~/cowrie/cowrie/commands/
- [ ] Cowrie restarted after tier files installed
- [ ] AWS endpoint filled in once provided
- [ ] health_check.sh passes with no FAIL items
- [ ] Manual verify: ssh root@<pi_ip> -p 2222 (password: root)

---

## Useful Commands

```bash
# Watch live attacker activity
tail -f ~/cowrie/var/log/cowrie/cowrie.log

# Watch JSON events
tail -f ~/cowrie/var/log/cowrie/cowrie.json | python3 -m json.tool

# Replay an attacker session
~/cowrie/bin/playlog ~/cowrie/var/lib/cowrie/tty/<session_file>

# Cowrie control
~/cowrie/bin/cowrie start|stop|restart|status

# Check Ollama model is in memory
curl http://localhost:11434/api/ps

# View SCALPEL metrics (tier hit rates, latency, cloud escalation %)
cat ~/cowrie/var/log/cowrie/scalpel_metrics.json

# Inspect virtual filesystem
~/cowrie/bin/fsctl ~/cowrie/share/cowrie/fs.pickle
```

---

## Team Roles

| Person | Role | Responsibility |
|--------|------|----------------|
| 1 | Pi Operator | Runs scripts, fixes errors |
| 2 | Network Lead | Gets IP, posts to Slack, handles AWS config |
| 3 | Monitor | Watches cowrie.log during gauntlet |
| 4 | Presentation | Builds slides, documents decisions as they happen |

---

## Credentials Reference

| Access | Username | Password | Port |
|--------|----------|----------|------|
| Cowrie user | cowrie | honeypot | 22 |
| Real Pi user | pi | raspberry | 22 |
| Honeypot (red team) | root | root | 2222 |

**Do not change any of these.**

---

## Key File Locations (On The Pi)

| File | Location |
|------|----------|
| Main config | ~/cowrie/etc/cowrie.cfg |
| Virtual filesystem | ~/cowrie/share/cowrie/fs.pickle |
| HoneyFS content | ~/cowrie/honeyfs/ |
| Live log | ~/cowrie/var/log/cowrie/cowrie.log |
| JSON log | ~/cowrie/var/log/cowrie/cowrie.json |
| TTY recordings | ~/cowrie/var/lib/cowrie/tty/ |
| SCALPEL metrics | ~/cowrie/var/log/cowrie/scalpel_metrics.json |
| Tier files | ~/cowrie/cowrie/commands/ |

---

## Contact

Victoria Jolly — jollyv@usf.edu | 919.886.8963
Slack: eMERGE 2026 Hackathon channel

Cowrie docs: https://docs.cowrie.org/en/stable/
Ollama docs: https://docs.ollama.com/api/introduction