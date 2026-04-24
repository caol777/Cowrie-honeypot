#!/bin/bash
# ==============================================================================
# Ollama Install & Model Setup — Project SCALPEL v2
# Run as root:  sudo bash install_ollama.sh
#
# Hardened vs v1:
#   - No `set -e` around `curl | sh` — installers can emit non-fatal warnings.
#   - Waits for the ollama.service unit to be registered before enabling.
#   - Uses keep_alive=-1 during gauntlet (never unload model).
#   - Installs boto3 for Tier 4 Bedrock client.
#   - Pre-pulls both qwen2.5:1.5b (default) and qwen2.5:0.5b (speed fallback).
# ==============================================================================

set -u
set -o pipefail

MODEL_MAIN="${SCALPEL_MODEL:-qwen2.5:1.5b}"
MODEL_FAST="qwen2.5:0.5b"

echo "================================================================"
echo " SCALPEL Ollama Setup v2"
echo " Primary model: $MODEL_MAIN"
echo " Fallback model: $MODEL_FAST"
echo "================================================================"

# ---- 1. Install Ollama ----
if command -v ollama >/dev/null 2>&1; then
    echo "[+] Ollama already installed ($(ollama --version 2>/dev/null | head -n1))"
else
    echo "[*] Installing Ollama..."
    # DO NOT fail the whole script if the installer emits warnings
    curl -fsSL https://ollama.com/install.sh | sh || {
        echo "[!] Ollama install script returned non-zero. Verifying binary..."
    }
fi

if ! command -v ollama >/dev/null 2>&1; then
    echo "[!] ollama binary not on PATH after install — aborting."
    exit 1
fi

# ---- 2. Wait for systemd unit to be registered ----
echo "[*] Waiting for ollama.service to register..."
for i in $(seq 1 20); do
    if systemctl list-unit-files 2>/dev/null | grep -q "^ollama.service"; then
        echo "[+] ollama.service is registered"
        break
    fi
    sleep 1
done

systemctl enable ollama 2>/dev/null || true
systemctl restart ollama 2>/dev/null || systemctl start ollama 2>/dev/null || true

# ---- 3. Wait for API to become reachable ----
echo "[*] Waiting for Ollama API on :11434..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "[+] API responding"
        break
    fi
    sleep 1
done

if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "[!] Ollama API not reachable after 30s. Check: systemctl status ollama"
    exit 1
fi

# ---- 4. Pull models ----
echo "[*] Pulling $MODEL_MAIN (this can take several minutes on first run)..."
ollama pull "$MODEL_MAIN"

echo "[*] Pulling $MODEL_FAST (fallback for speed)..."
ollama pull "$MODEL_FAST" || echo "[!] Fallback pull failed — not critical"

# ---- 5. Warm the main model into memory with keep_alive=-1 ----
echo "[*] Warming $MODEL_MAIN into memory (keep_alive=-1, never unload)..."
curl -s -X POST http://localhost:11434/api/generate \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"$MODEL_MAIN\",
        \"prompt\": \"true\",
        \"stream\": false,
        \"keep_alive\": -1,
        \"options\": {\"num_predict\": 4}
    }" > /dev/null
echo "[+] Model loaded"

# ---- 6. Verify loaded ----
LOADED=$(curl -s http://localhost:11434/api/ps | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin); print(d.get('models', [{}])[0].get('name', 'none'))
except Exception:
    print('error')
" 2>/dev/null)
if [ -n "$LOADED" ] && [ "$LOADED" != "none" ] && [ "$LOADED" != "error" ]; then
    echo "[+] Resident: $LOADED"
else
    echo "[!] No model currently resident — warm-up may have raced. Retry manually:"
    echo "    curl -s -X POST http://localhost:11434/api/generate -d '{\"model\":\"$MODEL_MAIN\",\"prompt\":\"true\",\"stream\":false,\"keep_alive\":-1}'"
fi

# ---- 7. Install boto3 for Tier 4 Bedrock ----
echo "[*] Installing boto3 for AWS Bedrock (Tier 4)..."
pip3 install --break-system-packages --quiet boto3 || \
    pip3 install --user --quiet boto3 || \
    echo "[!] boto3 install failed — Tier 4 will fall back to _safe_fallback"

# ---- 8. Benchmark ----
echo ""
echo "[*] Latency benchmark..."
bench() {
    local p="$1"
    local start end ms resp
    start=$(date +%s%N)
    curl -s -X POST http://localhost:11434/api/generate \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$MODEL_MAIN\",
            \"prompt\": \"$p\",
            \"stream\": false,
            \"keep_alive\": -1,
            \"options\": {\"num_predict\": 32}
        }" > /tmp/ollama_bench.json
    end=$(date +%s%N)
    ms=$(( (end - start) / 1000000 ))
    resp=$(python3 -c "import json; print(json.load(open('/tmp/ollama_bench.json')).get('response','').strip()[:40])" 2>/dev/null)
    printf "  [%5d ms] %-20s -> %s\n" "$ms" "$p" "$resp"
}
bench "whoami"
bench "uname -a"
bench "ls /etc"

echo ""
echo "================================================================"
echo " Ollama setup complete."
echo "   Main model : $MODEL_MAIN"
echo "   Fast model : $MODEL_FAST (swap by export SCALPEL_MODEL=$MODEL_FAST)"
echo "   Service    : systemctl status ollama"
echo "   Live logs  : journalctl -u ollama -f"
echo "   Resident   : curl -s http://localhost:11434/api/ps"
echo "================================================================"
