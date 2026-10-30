/**
 * Local Self-Hosted WhatsApp Web Gateway
 * For Sutawane Classes Management Software ERP
 * 100% Free, Zero Cloud API, Runs Locally on Windows/Linux
 */

const express = require('express');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode');
const qrcodeTerminal = require('qrcode-terminal');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json({ limit: '25mb' }));
app.use(express.urlencoded({ extended: true, limit: '25mb' }));

// CORS headers for local Django access
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, Authorization');
    if (req.method === 'OPTIONS') return res.sendStatus(200);
    next();
});

// Bridge State
let bridgeState = {
    status: 'INITIALIZING', // INITIALIZING | QR_READY | AUTHENTICATING | READY | DISCONNECTED
    qrString: null,
    qrDataUrl: null,
    connectedPhone: null,
    connectedName: null,
    lastActive: new Date().toISOString(),
    error: null
};

// Auto-detect Linux Chromium / Chrome binaries
function getChromiumExecutablePath() {
    if (process.env.PUPPETEER_EXECUTABLE_PATH && fs.existsSync(process.env.PUPPETEER_EXECUTABLE_PATH)) {
        return process.env.PUPPETEER_EXECUTABLE_PATH;
    }
    if (process.platform === 'linux') {
        const candidatePaths = [
            '/usr/bin/google-chrome-stable',
            '/usr/bin/google-chrome',
            '/usr/bin/chromium-browser',
            '/usr/bin/chromium',
            '/snap/bin/chromium',
            '/usr/bin/brave-browser'
        ];
        for (const candidate of candidatePaths) {
            try {
                if (fs.existsSync(candidate)) {
                    return candidate;
                }
            } catch (e) {}
        }
    }
    return undefined;
}

const detectedChromium = getChromiumExecutablePath();
if (detectedChromium) {
    console.log(`[WhatsApp Bridge] Detected Chromium at: ${detectedChromium}`);
}

const puppeteerArgs = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-accelerated-2d-canvas',
    '--no-first-run',
    '--no-zygote',
    '--disable-gpu'
];

const puppeteerConfig = {
    headless: true,
    args: puppeteerArgs
};

if (detectedChromium) {
    puppeteerConfig.executablePath = detectedChromium;
}

// Initialize WhatsApp Client with Local Session Storage
const client = new Client({
    authStrategy: new LocalAuth({
        dataPath: path.join(__dirname, '.wwebjs_auth')
    }),
    puppeteer: puppeteerConfig
});

// Event: QR Code Received
client.on('qr', async (qr) => {
    bridgeState.status = 'QR_READY';
    bridgeState.qrString = qr;
    bridgeState.error = null;

    try {
        bridgeState.qrDataUrl = await qrcode.toDataURL(qr, { width: 300, margin: 2 });
    } catch (err) {
        console.error('Failed to generate QR data URL:', err);
    }

    console.log('\n============================================================');
    console.log(' [WhatsApp Bridge] QR CODE RECEIVED: Scan with WhatsApp phone');
    console.log(' Open WhatsApp on phone -> Settings -> Linked Devices -> Link a Device');
    console.log('============================================================\n');
    qrcodeTerminal.generate(qr, { small: true });
});

// Event: Authenticating
client.on('authenticating', () => {
    bridgeState.status = 'AUTHENTICATING';
    console.log('[WhatsApp Bridge] Authenticating session...');
});

// Event: Ready (Connected and synced)
client.on('ready', () => {
    bridgeState.status = 'READY';
    bridgeState.qrString = null;
    bridgeState.qrDataUrl = null;
    bridgeState.error = null;
    bridgeState.lastActive = new Date().toISOString();

    const info = client.info;
    if (info) {
        bridgeState.connectedPhone = info.wid ? info.wid.user : null;
        bridgeState.connectedName = info.pushname || 'Sutawane Classes Admin';
    }

    console.log('\n============================================================');
    console.log(' ✅ [WhatsApp Bridge] READY & CONNECTED TO LOCAL WHATSAPP!');
    console.log(` Connected Account: ${bridgeState.connectedName} (${bridgeState.connectedPhone})`);
    console.log('============================================================\n');
});

// Event: Disconnected
client.on('disconnected', (reason) => {
    bridgeState.status = 'DISCONNECTED';
    bridgeState.error = reason;
    console.warn(`[WhatsApp Bridge] Disconnected: ${reason}. Restarting client...`);
    setTimeout(() => {
        client.initialize().catch(err => console.error('Failed to reinitialize:', err));
    }, 5000);
});

client.on('auth_failure', (msg) => {
    bridgeState.status = 'DISCONNECTED';
    bridgeState.error = msg;
    console.error('[WhatsApp Bridge] Auth failure:', msg);
});

// -------------------------------------------------------------
// REST API Endpoints
// -------------------------------------------------------------

// 1. Health / Status Check
app.get('/health', (req, res) => {
    res.json({
        success: true,
        bridge: 'Sutawane Classes WhatsApp Local Gateway',
        status: bridgeState.status,
        isReady: bridgeState.status === 'READY',
        connectedPhone: bridgeState.connectedPhone,
        connectedName: bridgeState.connectedName,
        platform: process.platform,
        chromiumPath: detectedChromium || 'bundled',
        error: bridgeState.error,
        timestamp: new Date().toISOString()
    });
});

app.get('/status', (req, res) => {
    res.json({
        success: true,
        status: bridgeState.status,
        isReady: bridgeState.status === 'READY',
        connectedPhone: bridgeState.connectedPhone,
        connectedName: bridgeState.connectedName,
        qrAvailable: Boolean(bridgeState.qrDataUrl),
        timestamp: new Date().toISOString()
    });
});

// 2. View QR Code (HTML or JSON)
app.get('/qr', (req, res) => {
    const wantsJson = req.query.json === 'true' || req.headers.accept?.includes('application/json');

    if (wantsJson) {
        return res.json({
            success: true,
            status: bridgeState.status,
            isReady: bridgeState.status === 'READY',
            connectedPhone: bridgeState.connectedPhone,
            connectedName: bridgeState.connectedName,
            qrString: bridgeState.qrString,
            qrDataUrl: bridgeState.qrDataUrl,
            error: bridgeState.error
        });
    }

    if (bridgeState.status === 'READY') {
        return res.send(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>WhatsApp Bridge Connected</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #f0fdf4; }
                    .card { background: white; border-radius: 16px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); text-align: center; max-width: 400px; }
                    .badge { display: inline-block; padding: 6px 14px; background: #dcfce7; color: #166534; font-weight: bold; border-radius: 9999px; font-size: 13px; margin-bottom: 12px; }
                    h2 { margin: 8px 0; color: #0f172a; }
                    p { color: #64748b; font-size: 14px; margin: 6px 0; }
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="badge">● ONLINE & ACTIVE</div>
                    <h2>WhatsApp Connected</h2>
                    <p>Linked Device: <strong>${bridgeState.connectedName || 'Sutawane Classes'}</strong></p>
                    <p>Phone: <strong>+${bridgeState.connectedPhone || ''}</strong></p>
                    <p style="margin-top: 16px; font-size: 12px; color: #94a3b8;">You can now send automated student receipts and reminders directly from the software without API charges.</p>
                </div>
            </body>
            </html>
        `);
    }

    if (bridgeState.qrDataUrl) {
        if (req.query.json === 'true' || req.headers.accept?.includes('application/json')) {
            return res.json({
                success: true,
                status: bridgeState.status,
                qrString: bridgeState.qrString,
                qrDataUrl: bridgeState.qrDataUrl
            });
        }

        return res.send(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Scan WhatsApp QR Code</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <meta http-equiv="refresh" content="5">
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #f8fafc; }
                    .card { background: white; border-radius: 16px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); text-align: center; max-width: 420px; }
                    .qr-box { padding: 12px; background: #ffffff; border: 2px dashed #cbd5e1; border-radius: 12px; display: inline-block; margin: 16px 0; }
                    h2 { margin: 8px 0; color: #0f172a; font-size: 20px; }
                    p { color: #64748b; font-size: 13px; line-height: 1.5; margin: 6px 0; }
                    ol { text-align: left; font-size: 12px; color: #475569; padding-left: 20px; margin: 16px 0; }
                    li { margin-bottom: 6px; }
                    .pulse { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #22c55e; margin-right: 6px; animation: pulse 1.5s infinite; }
                    @keyframes pulse { 0% { opacity: 0.4; } 50% { opacity: 1; } 100% { opacity: 0.4; } }
                </style>
            </head>
            <body>
                <div class="card">
                    <span style="font-size: 11px; font-weight: 700; color: #3b82f6; text-transform: uppercase;"><span class="pulse"></span>Waiting for Phone Scan</span>
                    <h2>Link Institute WhatsApp</h2>
                    <p>Scan this QR code with your phone to link your WhatsApp directly to Sutawane Classes ERP:</p>
                    <div class="qr-box">
                        <img src="${bridgeState.qrDataUrl}" alt="WhatsApp QR Code" style="width: 260px; height: 260px; display: block;" />
                    </div>
                    <ol>
                        <li>Open WhatsApp on your phone</li>
                        <li>Tap <strong>Settings</strong> or <strong>Menu (⋮)</strong></li>
                        <li>Tap <strong>Linked Devices</strong> &rarr; <strong>Link a Device</strong></li>
                        <li>Point your phone camera at this screen</li>
                    </ol>
                    <p style="font-size: 11px; color: #94a3b8;">This page refreshes automatically once connected.</p>
                </div>
            </body>
            </html>
        `);
    }

    return res.status(503).send(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>Initializing Bridge</title>
            <meta http-equiv="refresh" content="3">
            <style>
                body { font-family: sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #f8fafc; }
                .card { background: white; padding: 24px; border-radius: 12px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
            </style>
        </head>
        <body>
            <div class="card">
                <h3>Initializing Local WhatsApp Bridge...</h3>
                <p>Generating QR code, please wait a moment. (Auto-refreshing...)</p>
            </div>
        </body>
        </html>
    `);
});

// 3. Send Message API (Text and Optional Media / PDF)
app.post('/send', async (req, res) => {
    try {
        if (bridgeState.status !== 'READY') {
            return res.status(503).json({
                success: false,
                error: `WhatsApp Bridge is not ready (Current Status: ${bridgeState.status}). Please link your phone via /qr first.`
            });
        }

        const { to, phone, recipient, message, text, file_base64, file_url, filename, mimetype } = req.body;
        const targetNumber = to || phone || recipient;
        const msgText = message || text || '';

        if (!targetNumber) {
            return res.status(400).json({ success: false, error: 'Recipient phone number is required.' });
        }

        // Format chatId (e.g. "919876543210@c.us")
        let cleanNumber = String(targetNumber).replace(/\D/g, '');
        if (cleanNumber.length === 10) cleanNumber = '91' + cleanNumber;
        const chatId = cleanNumber.includes('@c.us') ? cleanNumber : `${cleanNumber}@c.us`;

        let sendResult;

        if (file_base64) {
            const media = new MessageMedia(
                mimetype || 'application/pdf',
                file_base64,
                filename || 'document.pdf'
            );
            sendResult = await client.sendMessage(chatId, media, { caption: msgText });
        } else {
            sendResult = await client.sendMessage(chatId, msgText);
        }

        bridgeState.lastActive = new Date().toISOString();
        return res.json({
            success: true,
            status: 'SENT',
            messageId: sendResult?.id?._serialized || (sendResult?.id ? String(sendResult.id) : ('msg_' + Date.now())),
            recipient: cleanNumber,
            timestamp: new Date().toISOString()
        });

    } catch (err) {
        console.error('[WhatsApp Bridge] Error sending message:', err);
        return res.status(500).json({
            success: false,
            status: 'FAILED',
            error: err.message || String(err)
        });
    }
});

// 4. Logout / Disconnect Device & Hard Reset Session
app.post(['/logout', '/unlink', '/reset'], async (req, res) => {
    try {
        console.log('[WhatsApp Bridge] Received unlink/reset command...');

        // 1. Try graceful client logout if possible
        try {
            await client.logout();
        } catch (e) {
            console.log('[WhatsApp Bridge] Graceful logout bypassed:', e.message);
        }

        // 2. Destroy running browser instance
        try {
            await client.destroy();
        } catch (e) {
            console.log('[WhatsApp Bridge] Client destroy warning:', e.message);
        }

        // 3. Completely delete .wwebjs_auth directory to wipe all previous sessions
        const sessionPath = path.join(__dirname, '.wwebjs_auth');
        try {
            if (fs.existsSync(sessionPath)) {
                fs.rmSync(sessionPath, { recursive: true, force: true });
                console.log('[WhatsApp Bridge] Deleted .wwebjs_auth session storage.');
            }
        } catch (e) {
            console.warn('[WhatsApp Bridge] Could not delete .wwebjs_auth:', e.message);
        }

        // 4. Reset state
        bridgeState.status = 'INITIALIZING';
        bridgeState.connectedPhone = null;
        bridgeState.connectedName = null;
        bridgeState.qrString = null;
        bridgeState.qrDataUrl = null;
        bridgeState.error = null;

        // 5. Reinitialize client for a brand-new QR scan
        setTimeout(() => {
            console.log('[WhatsApp Bridge] Re-initializing client to generate brand-new QR code...');
            client.initialize().catch(err => {
                console.error('Failed to reinitialize:', err);
                bridgeState.status = 'DISCONNECTED';
                bridgeState.error = err.message || String(err);
            });
        }, 1000);

        return res.json({
            success: true,
            message: 'WhatsApp session unlinked and wiped. Generating brand-new QR code...'
        });
    } catch (err) {
        console.error('[WhatsApp Bridge] Unlink error:', err);
        return res.status(500).json({ success: false, error: err.message || String(err) });
    }
});

// 5. Restart Bridge
app.post('/restart', async (req, res) => {
    try {
        bridgeState.status = 'INITIALIZING';
        bridgeState.error = null;
        bridgeState.qrDataUrl = null;
        try { await client.destroy(); } catch (e) {}
        setTimeout(() => {
            client.initialize().catch(err => {
                console.error('Failed to initialize WhatsApp Web client on restart:', err);
                bridgeState.status = 'DISCONNECTED';
                bridgeState.error = err.message || String(err);
            });
        }, 1000);
        return res.json({ success: true, message: 'Bridge restart triggered' });
    } catch (err) {
        return res.status(500).json({ success: false, error: err.message });
    }
});

// Start Express HTTP Server
app.listen(PORT, '0.0.0.0', () => {
    console.log(`\n============================================================`);
    console.log(` 🚀 [WhatsApp Gateway] HTTP Server running on http://localhost:${PORT}`);
    console.log(` Health: http://localhost:${PORT}/health`);
    console.log(` QR Code: http://localhost:${PORT}/qr`);
    console.log(` Send API: POST http://localhost:${PORT}/send`);
    console.log(`============================================================\n`);

    client.initialize().catch(err => {
        console.error('❌ Failed to initialize WhatsApp Web client:', err);
        bridgeState.status = 'DISCONNECTED';
        bridgeState.error = err.message || String(err);
    });
});
