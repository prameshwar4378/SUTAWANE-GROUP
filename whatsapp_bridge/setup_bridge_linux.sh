#!/bin/bash
# ====================================================================
# Sutawane Classes - WhatsApp Gateway Linux Auto-Setup Script
# Compatible with Ubuntu 24.04 (Noble), Ubuntu 22.04 (Jammy), and Debian
# ====================================================================

set -e

echo "=== [1/4] Installing Linux Libraries for Headless Browser ==="
sudo apt-get update

# Detect Ubuntu 24.04 Noble (t64 package transition) vs Ubuntu 22.04
if apt-cache show libasound2t64 >/dev/null 2>&1; then
    echo "Detected Ubuntu 24.04 (noble) - installing t64 libraries..."
    sudo apt-get install -y \
        libasound2t64 \
        libatk-bridge2.0-0t64 \
        libgtk-3-0t64 \
        libnss3 \
        libxss1 \
        libgbm1 \
        fonts-liberation \
        ca-certificates \
        xdg-utils \
        wget \
        curl
else
    echo "Detected Ubuntu 22.04 or earlier - installing standard libraries..."
    sudo apt-get install -y \
        libasound2 \
        libatk-bridge2.0-0 \
        libgtk-3-0 \
        libnss3 \
        libxss1 \
        libgbm1 \
        fonts-liberation \
        ca-certificates \
        xdg-utils \
        wget \
        curl
fi

# Ensure Google Chrome Stable is installed (no snap dependency)
if ! command -v google-chrome &>/dev/null && ! command -v google-chrome-stable &>/dev/null && ! command -v chromium-browser &>/dev/null && ! command -v chromium &>/dev/null; then
    echo "=== Installing Official Google Chrome Stable (.deb) ==="
    wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo apt-get install -y /tmp/google-chrome.deb || (sudo dpkg -i /tmp/google-chrome.deb && sudo apt-get install -f -y)
    rm -f /tmp/google-chrome.deb
fi

echo "=== [2/4] Installing Node.js Bridge Dependencies ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Install npm dependencies
npm install

# Download Puppeteer Chrome as secondary fallback
npx puppeteer browsers install chrome || true

# Fix directory ownership so 'sutawane' user has full read/write access
sudo chown -R sutawane:sutawane "$SCRIPT_DIR"

echo "=== [3/4] Enabling and Restarting systemd Service ==="
SERVICE_FILE="/etc/systemd/system/sutawane-whatsapp.service"
NODE_PATH="$(which node || echo '/usr/bin/node')"
CHROME_PATH="$(which google-chrome-stable || which google-chrome || which chromium-browser || which chromium || echo '/usr/bin/google-chrome-stable')"

echo "Using Node: $NODE_PATH"
echo "Using Chrome: $CHROME_PATH"

echo "Updating systemd service file at $SERVICE_FILE..."
sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=Sutawane Classes WhatsApp Gateway Service
After=network.target

[Service]
User=sutawane
Group=sutawane
WorkingDirectory=$SCRIPT_DIR
Environment=PORT=3000
Environment=PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=false
Environment=PUPPETEER_EXECUTABLE_PATH=$CHROME_PATH
ExecStart=$NODE_PATH $SCRIPT_DIR/server.js
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable sutawane-whatsapp
sudo systemctl restart sutawane-whatsapp
echo "Service sutawane-whatsapp restarted successfully!"

echo "=== [4/4] Verifying WhatsApp Gateway Status ==="
sleep 4
STATUS_OUTPUT=$(curl -s http://localhost:3000/health || true)
echo "Health check response: $STATUS_OUTPUT"

echo ""
echo "===================================================================="
echo "  WhatsApp Gateway Service is ACTIVE on http://localhost:3000"
echo " Open your browser to Settings -> WhatsApp tab to scan the QR code:"
echo " http://173.249.33.152:8080/settings/?tab=whatsapp#tab-whatsapp"
echo "===================================================================="
