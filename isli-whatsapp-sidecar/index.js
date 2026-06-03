const express = require('express');
const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion
} = require('@whiskeysockets/baileys');
const pino = require('pino');
const axios = require('axios');
const axiosRetry = require('axios-retry').default;
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

const app = express();
app.use(express.json({ limit: '10mb' }));

const logger = pino({ level: process.env.LOG_LEVEL || 'info' });
const PORT = process.env.PORT || 3001;
const AUTH_BASE_DIR = process.env.AUTH_BASE_DIR || '/auth/whatsapp';
const CHANNELS_WEBHOOK_URL = process.env.CHANNELS_WEBHOOK_URL || 'http://channels:8200/webhook/whatsapp';
const SIDECAR_WEBHOOK_SECRET = process.env.SIDECAR_WEBHOOK_SECRET || '';
const SIDECAR_API_TOKEN = process.env.SIDECAR_API_TOKEN || '';

// Configure axios with retries for webhook reliability
axiosRetry(axios, {
    retries: 3,
    retryDelay: axiosRetry.exponentialDelay,
    retryCondition: (error) => {
        return axiosRetry.isNetworkOrIdempotentRequestError(error)
            || (error.response && error.response.status >= 500)
            || (error.response && error.response.status === 429);
    }
});

// Per-agent session storage
const sessions = new Map();
const qrCodes = new Map();
const connectionStatus = new Map();
const deleting = new Set();

// --- Auth middleware ---
function requireAuth(req, res, next) {
    if (!SIDECAR_API_TOKEN) {
        // If no token is configured, allow requests (backward compat for dev)
        return next();
    }
    const authHeader = req.headers['authorization'] || '';
    const parts = authHeader.split(' ');
    if (parts.length !== 2 || parts[0].toLowerCase() !== 'bearer' || parts[1] !== SIDECAR_API_TOKEN) {
        return res.status(401).json({ error: 'Unauthorized' });
    }
    next();
}

async function forwardEvent(agentId, type, payload) {
    const url = `${CHANNELS_WEBHOOK_URL}/${agentId}`;
    const headers = { 'Content-Type': 'application/json' };
    const body = JSON.stringify({ type, payload });
    if (SIDECAR_WEBHOOK_SECRET) {
        const signature = crypto
            .createHmac('sha256', SIDECAR_WEBHOOK_SECRET)
            .update(body)
            .digest('hex');
        headers['X-Sidecar-Secret'] = signature;
    }
    try {
        await axios.post(url, body, { headers });
    } catch (error) {
        logger.error({ agentId, type, error: error.message }, 'Failed to forward event to channels');
    }
}

async function startSession(agentId) {
    if (sessions.has(agentId)) {
        logger.info({ agentId }, 'Session already exists');
        return;
    }

    const authFolder = path.join(AUTH_BASE_DIR, agentId);
    if (!fs.existsSync(authFolder)) {
        fs.mkdirSync(authFolder, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(authFolder);
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
        version,
        auth: state,
        printQRInTerminal: false,
        browser: (process.env.WHATSAPP_BROWSER || 'Ubuntu,Chrome,120.0.0.0').split(','),
        syncFullHistory: false,
        logger: logger.child({ agentId, service: 'baileys' })
    });

    sessions.set(agentId, sock);
    connectionStatus.set(agentId, 'connecting');

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            qrCodes.set(agentId, qr);
            logger.info({ agentId }, 'New QR code generated');
        }

        if (connection === 'close') {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            logger.info({ agentId, statusCode }, 'Connection closed');
            // If the session was intentionally deleted, don't restore a stale 'closed' status
            if (deleting.has(agentId)) {
                connectionStatus.delete(agentId);
            } else {
                connectionStatus.set(agentId, 'closed');
            }
            qrCodes.delete(agentId);

            if (shouldReconnect) {
                sessions.delete(agentId);
                setTimeout(() => {
                    startSession(agentId).catch(err => {
                        logger.error({ agentId, error: err.message }, 'Reconnection failed');
                    });
                }, 5000);
            } else {
                sessions.delete(agentId);
            }
        } else if (connection === 'open') {
            logger.info({ agentId }, 'Connection opened');
            connectionStatus.set(agentId, 'open');
            qrCodes.delete(agentId);
        }

        // Sanitize the update object to prevent axios crashing on circular JSON
        const safeUpdate = {
            connection,
            qr,
            lastDisconnect: lastDisconnect ? {
                error: lastDisconnect.error?.message || String(lastDisconnect.error)
            } : undefined
        };
        await forwardEvent(agentId, 'connection.update', safeUpdate);
    });

    sock.ev.on('messages.upsert', async (m) => {
        if (m.type === 'notify') {
            for (const msg of m.messages) {
                if (!msg.key.fromMe && msg.message) {
                    // Skip system/stub messages with no actual content
                    const hasText = msg.message.conversation || msg.message.extendedTextMessage?.text;
                    const hasAttachment = msg.message.imageMessage || msg.message.videoMessage || msg.message.audioMessage || msg.message.documentMessage;
                    if (!hasText && !hasAttachment) {
                        continue;
                    }
                    logger.info({ agentId, from: msg.key.remoteJid }, 'Inbound message received');
                    const safeMsg = {
                        key: msg.key,
                        message: msg.message
                    };
                    await forwardEvent(agentId, 'message', safeMsg);
                }
            }
        }
    });
}

// --- REST Endpoints ---

app.get('/health', (req, res) => {
    res.json({ status: 'ok', connections: connectionStatus.size });
});

app.post('/session/:agentId/start', requireAuth, async (req, res) => {
    const { agentId } = req.params;
    try {
        await startSession(agentId);
        res.json({ status: 'starting', agentId });
    } catch (err) {
        logger.error({ agentId, error: err.message }, 'Failed to start session');
        res.status(500).json({ status: 'error', error: err.message });
    }
});

app.get('/session/:agentId/status', requireAuth, (req, res) => {
    const { agentId } = req.params;
    let status = connectionStatus.get(agentId) || 'disconnected';
    if (status === 'closed') status = 'disconnected';
    res.json({
        agentId,
        status
    });
});

app.get('/session/:agentId/qr', requireAuth, (req, res) => {
    const { agentId } = req.params;
    res.json({
        agentId,
        qr: qrCodes.get(agentId) || null
    });
});

app.delete('/session/:agentId', requireAuth, async (req, res) => {
    const { agentId } = req.params;
    deleting.add(agentId);
    try {
        const sock = sessions.get(agentId);
        if (sock) {
            try {
                await sock.logout();
            } catch (err) {
                logger.warn({ agentId, error: err.message }, 'Logout failed');
            }
            sessions.delete(agentId);
            qrCodes.delete(agentId);
            connectionStatus.delete(agentId);
        }

        const authFolder = path.join(AUTH_BASE_DIR, agentId);
        if (fs.existsSync(authFolder)) {
            fs.rmSync(authFolder, { recursive: true, force: true });
        }

        res.json({ status: 'deleted', agentId });
    } finally {
        deleting.delete(agentId);
    }
});

app.post('/send', requireAuth, async (req, res) => {
    const { type, agentId, jid, text, audio_b64, caption } = req.body;
    const sock = sessions.get(agentId);

    if (!sock) {
        return res.status(404).json({ error: 'Session not found' });
    }

    try {
        if (type === 'audio' && audio_b64) {
            const tmpPath = path.join('/tmp', `isli_audio_${Date.now()}_${Math.random().toString(36).slice(2)}.wav`);
            try {
                fs.writeFileSync(tmpPath, Buffer.from(audio_b64, 'base64'));
                const sentMsg = await sock.sendMessage(jid, {
                    audio: { url: tmpPath },
                    ptt: true,
                    caption: caption || undefined,
                });
                res.json({ success: true, messageId: sentMsg.key.id });
            } finally {
                try {
                    fs.unlinkSync(tmpPath);
                } catch (e) {
                    // ignore cleanup errors
                }
            }
        } else {
            const sentMsg = await sock.sendMessage(jid, { text });
            res.json({ success: true, messageId: sentMsg.key.id });
        }
    } catch (error) {
        logger.error({ agentId, jid, type, error: error.message }, 'Failed to send message');
        res.status(500).json({ error: error.message });
    }
});

// Auto-start existing sessions
if (fs.existsSync(AUTH_BASE_DIR)) {
    const dirs = fs.readdirSync(AUTH_BASE_DIR);
    for (const agentId of dirs) {
        if (agentId.startsWith('.')) continue;
        const fullPath = path.join(AUTH_BASE_DIR, agentId);
        try {
            if (fs.statSync(fullPath).isDirectory()) {
                logger.info({ agentId }, 'Auto-restarting session');
                startSession(agentId).catch(err => {
                    logger.error({ agentId, error: err.message }, 'Auto-start failed');
                });
            }
        } catch (err) {
            logger.error({ agentId, error: err.message }, 'Auto-start stat failed');
        }
    }
}

// Graceful shutdown
process.on('SIGTERM', async () => {
    logger.info('SIGTERM received, closing sessions');
    for (const [agentId, sock] of sessions) {
        try {
            await sock.end(undefined);
        } catch (err) {
            logger.warn({ agentId, error: err.message }, 'Error closing socket');
        }
    }
    process.exit(0);
});

process.on('SIGINT', async () => {
    logger.info('SIGINT received, closing sessions');
    for (const [agentId, sock] of sessions) {
        try {
            await sock.end(undefined);
        } catch (err) {
            logger.warn({ agentId, error: err.message }, 'Error closing socket');
        }
    }
    process.exit(0);
});

app.listen(PORT, () => {
    logger.info(`WhatsApp sidecar listening on port ${PORT}`);
});
