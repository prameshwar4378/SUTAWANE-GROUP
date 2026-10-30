#!/bin/bash
# ====================================================================
# Sutawane Classes - WhatsApp Gateway Linux Auto-Setup Script
# Configures Chromium dependencies & systemd service on Ubuntu 24.04/22.04
# ====================================================================

set -e

echo "=== [1/4] Installing Required Linux Chromium Dependencies ==="
sudo apt-get update
sudo apt-get install -y \
    chromium-browser \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libasound2t64 \
    libasound2 \
    libnss3 \
    libxss1 \
    libgbm1 \
    fonts-liberation \
    ca-certificates \
    xdg-utils 2>/dev/null || sudo apt-get install -y chromium libatk-bridge2.0-0 libgtk-3-0 libasound2 libnss3 libxss1 libgbm1 fonts-liberation ca-certificates

echo "=== [2/4] Installing Node.js Bridge Dependencies ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
npm install

echo "=== [3/4] Enabling and Restarting systemd Service ==="
if [ -f "/etc/systemd/system/sutawane-whatsapp.service" ]; then
    sudo systemctl daemon-reload
    sudo systemctl enable sutawane-whatsapp
    sudo systemctl restart sutawane-whatsapp
    echo "Service sutawane-whatsapp restarted successfully!"
else
    echo "Creating systemd service file at /etc/systemd/system/sutawane-whatsapp.service..."
    sudo bash -c "cat <<EOF > /etc/systemd/system/sutawane-whatsapp.service
[Unit]
Description=Sutawane Classes WhatsApp Gateway Service
After=network.target

[Service]
User=sutawane
Group=sutawane
WorkingDirectory=$SCRIPT_DIR
Environment=PORT=3000
Environment=PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=false
ExecStart=/usr/bin/node $SCRIPT_DIR/server.js
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"
    sudo systemctl daemon-reload
    sudo systemctl enable sutawane-whatsapp
    sudo systemctl restart sutawane-whatsapp
    echo "Service installed and started!"
fi

echo "=== [4/4] Checking WhatsApp Bridge Status ==="
sleep 3
curl -s http://localhost:3000/health || echo "Bridge starting up... please check: sudo systemctl status sutawane-whatsapp"
echo ""
echo "===================================================================="
echo "  WhatsApp Gateway setup complete!"
echo " Open your browser to Settings -> WhatsApp tab to scan the QR code."
echo "===================================================================="
