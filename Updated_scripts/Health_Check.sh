#!/bin/bash

# ==============================================================================
# Health Check — Project SCALPEL
# FAU Team - eMERGE 2026 Hackathon
#
# Run this before the red team gauntlet starts to confirm everything is up.
# Green = good. Red = fix it NOW.
#
# Usage: bash health_check.sh
# ==============================================================================

PASS=0
FAIL=0
WARN=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[PASS]${NC} $1"; ((PASS++)); }
fail() { echo -e "${RED}[FAIL]${NC} $1"; ((FAIL++)); }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; ((WARN++)); }

echo ""
echo "================================================================"
echo " SCALPEL Pre-Gauntlet Health Check"
echo " $(date)"
echo "================================================================"
echo ""

# ==============================================================================
# 1. Cowrie
# ==============================================================================
echo "--- Cowrie ---"

if systemctl is-active --quiet cowrie 2>/dev/null; then
    ok "Cowrie systemd service is running"
elif pgrep -f "cowrie" > /dev/null; then
    ok "Cowrie process is running (not via systemd)"
else
    fail "Cowrie is NOT running — start it: ~/cowrie/bin/cowrie start"
fi

# Check Cowrie is listening on port 2222
if ss -tlnp 2>/dev/null | grep -q ":2222"; then
    ok "Cowrie is listening on port 2222"
else
    fail "Nothing listening on port 2222 — Cowrie may not have started correctly"
fi

# Check red team can connect with expected credentials
echo -n "    Testing SSH connection on port 2222... "
if timeout 5 ssh -o StrictHostKeyChecking=no \
                 -o ConnectTimeout=3 \
                 -o PasswordAuthentication=yes \
                 -p 2222 root@localhost \
                 "exit" 2>/dev/null; then
    ok "SSH login root@localhost:2222 works"
else
    # sshpass method if available
    if command -v sshpass &>/dev/null; then
        if sshpass -p root timeout 5 ssh -o StrictHostKeyChecking=no \
                                         -o ConnectTimeout=3 \
                                         -p 2222 root@localhost \
                                         "exit" 2>/dev/null; then
            ok "SSH login root/root on port 2222 works (via sshpass)"
        else
            fail "Cannot SSH into Cowrie on port 2222 with root/root — RED TEAM CANNOT SCORE YOU"
        fi
    else
        warn "Could not auto-test SSH login — manually verify: ssh root@<pi_ip> -p 2222 (password: root)"
    fi
fi

# Check cowrie.cfg exists and has correct hostname
if grep -q "hostname = pi-sensor-gateway" ~/cowrie/etc/cowrie.cfg 2>/dev/null || \
   grep -q "hostname = pi-sensor-gateway" ~/cowrie/cowrie.cfg 2>/dev/null; then
    ok "Cowrie hostname set to pi-sensor-gateway"
else
    warn "Cowrie hostname may not be set — run bait.sh"
fi

# Check pickle file exists
if [ -f ~/cowrie/share/cowrie/fs.pickle ]; then
    ok "Filesystem pickle exists: ~/cowrie/share/cowrie/fs.pickle"
else
    fail "Filesystem pickle missing — honeyfs will use default (bad for realism score)"
fi

echo ""

# ==============================================================================
# 2. Ollama / Local LLM
# ==============================================================================
echo "--- Ollama (Tier 3 Local LLM) ---"

if systemctl is-active --quiet ollama 2>/dev/null; then
    ok "Ollama service is running"
else
    fail "Ollama service is NOT running — start it: systemctl start ollama"
fi

if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    ok "Ollama API is responsive"
else
    fail "Ollama API not reachable at localhost:11434"
fi

# Check model is loaded in memory
LOADED=$(curl -s http://localhost:11434/api/ps 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    models = data.get('models', [])
    print(models[0]['name'] if models else 'none')
except:
    print('error')
" 2>/dev/null)

if [ "$LOADED" = "none" ] || [ -z "$LOADED" ] || [ "$LOADED" = "error" ]; then
    warn "No model currently loaded in memory — cold start penalty on first command"
    warn "     Fix: curl -s -X POST http://localhost:11434/api/generate -d '{\"model\":\"qwen2.5:1.5b\",\"prompt\":\"hi\",\"stream\":false,\"keep_alive\":\"60m\"}'"
else
    ok "Model in memory: $LOADED"
fi

# Quick latency test
echo -n "    Testing Ollama response latency... "
START=$(date +%s%N)
RESP=$(curl -s -X POST http://localhost:11434/api/generate \
    -H "Content-Type: application/json" \
    -d '{"model":"qwen2.5:1.5b","prompt":"whoami","stream":false,"keep_alive":"60m","options":{"num_predict":16}}' \
    2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('response','').strip()[:30])" 2>/dev/null)
END=$(date +%s%N)
LATENCY=$(( (END - START) / 1000000 ))

if [ $LATENCY -lt 3000 ]; then
    ok "Ollama latency: ${LATENCY}ms (good)"
elif [ $LATENCY -lt 8000 ]; then
    warn "Ollama latency: ${LATENCY}ms (acceptable but consider qwen2.5:0.5b for speed)"
else
    fail "Ollama latency: ${LATENCY}ms (too slow — switch to smaller model or check Pi load)"
fi

echo ""

# ==============================================================================
# 3. Intercept layer
# ==============================================================================
echo "--- Intelligence Stack ---"

INTERCEPT_DIR=~/cowrie/cowrie/commands
if [ -f "$INTERCEPT_DIR/cowrie_intercept.py" ]; then
    ok "cowrie_intercept.py installed in Cowrie commands directory"
else
    warn "cowrie_intercept.py not found in $INTERCEPT_DIR — copy it there"
fi

if [ -f "$INTERCEPT_DIR/tier1_static.py" ]; then
    ok "tier1_static.py installed"
else
    warn "tier1_static.py not found in $INTERCEPT_DIR"
fi

if [ -f "$INTERCEPT_DIR/tier2_classifier.py" ]; then
    ok "tier2_classifier.py installed"
else
    warn "tier2_classifier.py not found in $INTERCEPT_DIR"
fi

if [ -f "$INTERCEPT_DIR/tier3_ollama_tier4_cloud.py" ]; then
    ok "tier3_ollama_tier4_cloud.py installed"
    # Check if AWS is configured
    if grep -q "CHANGE_ME" "$INTERCEPT_DIR/tier3_ollama_tier4_cloud.py" 2>/dev/null; then
        warn "AWS Bedrock endpoint not configured yet in tier3_ollama_tier4_cloud.py (fill in day-of)"
    else
        ok "AWS Bedrock endpoint is configured"
    fi
else
    warn "tier3_ollama_tier4_cloud.py not found in $INTERCEPT_DIR"
fi

echo ""

# ==============================================================================
# 4. Network & Pi reachability
# ==============================================================================
echo "--- Network ---"

PI_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')
if [ -n "$PI_IP" ]; then
    ok "Pi IP address: $PI_IP"
    echo "    >>> POST THIS IN SLACK BY 10:20 AM: $PI_IP <<<"
else
    fail "Could not determine Pi IP address — check network connection"
fi

if ping -c 1 -W 2 8.8.8.8 > /dev/null 2>&1; then
    ok "Internet connectivity confirmed"
else
    warn "No internet connectivity — AWS escalation will fail"
fi

echo ""

# ==============================================================================
# 5. Cowrie log directory
# ==============================================================================
echo "--- Logs ---"

LOG_DIR=~/cowrie/var/log/cowrie
if [ -d "$LOG_DIR" ]; then
    ok "Cowrie log directory exists: $LOG_DIR"
else
    fail "Cowrie log directory missing: $LOG_DIR"
fi

if [ -f "$LOG_DIR/cowrie.log" ]; then
    LINES=$(wc -l < "$LOG_DIR/cowrie.log")
    ok "cowrie.log exists ($LINES lines)"
else
    warn "cowrie.log not found yet — will appear once first connection is made"
fi

echo ""

# ==============================================================================
# Summary
# ==============================================================================
echo "================================================================"
echo " Health Check Complete"
printf " ${GREEN}PASS: $PASS${NC}  ${RED}FAIL: $FAIL${NC}  ${YELLOW}WARN: $WARN${NC}\n"
echo "================================================================"
echo ""

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}[!] $FAIL critical issues must be fixed before the gauntlet starts${NC}"
    exit 1
elif [ $WARN -gt 0 ]; then
    echo -e "${YELLOW}[!] $WARN warnings — system will work but may not score optimally${NC}"
    exit 0
else
    echo -e "${GREEN}[+] All checks passed — you are ready for the gauntlet!${NC}"
    exit 0
fi