const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const pino = require('pino');
const path = require('path');
const fs = require('fs');
const qrcode = require('qrcode-terminal');

let sock = null;

async function start() {
    const authDir = process.argv[2] || path.join(__dirname, 'auth_info');
    
    // Ensure authDir exists
    if (!fs.existsSync(authDir)) {
        fs.mkdirSync(authDir, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(authDir);

    // Use a completely silent logger for pino to prevent JSON logging clutter
    const logger = pino({ level: 'silent' });
    
    // Attempt to fetch the latest WhatsApp version to avoid 405 Method Not Allowed error
    let version = [2, 3000, 1035194821]; // Solid known-good fallback
    try {
        const latest = await fetchLatestBaileysVersion();
        if (latest && latest.version) {
            version = latest.version;
        }
    } catch (err) {
        // Fallback silently to our defined working version array
    }

    sock = makeWASocket({
        auth: state,
        logger: logger,
        version: version
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr) {
            // Write a structured JSON line so Python knows a QR code is generated
            console.log(JSON.stringify({ type: 'qr', qr: qr }));
            // Manually render the QR code in terminal using qrcode-terminal
            qrcode.generate(qr, { small: true });
        }

        if (connection === 'close') {
            const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log(JSON.stringify({ 
                type: 'connection', 
                status: 'close', 
                reconnect: shouldReconnect,
                reason: lastDisconnect?.error?.message || 'Unknown'
            }));
            
            if (shouldReconnect) {
                // Wait 5 seconds and restart the client socket connection
                setTimeout(start, 5000);
            } else {
                console.log(JSON.stringify({ type: 'logout_success' }));
                process.exit(0);
            }
        } else if (connection === 'open') {
            const phone = sock.user.id.split(':')[0];
            console.log(JSON.stringify({ 
                type: 'connection', 
                status: 'open', 
                phone: phone, 
                name: sock.user.name || '' 
            }));
        }
    });

    // Helper function to extract text robustly from any WhatsApp message type
    function extractText(message) {
        if (!message) return '';
        if (message.conversation) return message.conversation;
        if (message.extendedTextMessage && message.extendedTextMessage.text) {
            return message.extendedTextMessage.text;
        }
        if (message.ephemeralMessage && message.ephemeralMessage.message) {
            return extractText(message.ephemeralMessage.message);
        }
        if (message.viewOnceMessage && message.viewOnceMessage.message) {
            return extractText(message.viewOnceMessage.message);
        }
        if (message.viewOnceMessageV2 && message.viewOnceMessageV2.message) {
            return extractText(message.viewOnceMessageV2.message);
        }
        if (message.imageMessage && message.imageMessage.caption) return message.imageMessage.caption;
        if (message.videoMessage && message.videoMessage.caption) return message.videoMessage.caption;
        if (message.documentMessage && message.documentMessage.caption) return message.documentMessage.caption;
        return '';
    }

    sock.ev.on('messages.upsert', async (m) => {
        // Output debug line so user can see raw message arriving in the server logs
        console.log("DEBUG_UPSERT: Received message upsert event: " + JSON.stringify(m));
        
        if (m.type !== 'notify') return;
        
        for (const msg of m.messages) {
            const from = msg.key.remoteJid;
            if (!from) continue;
            
            // Skip status broadcasts
            if (from === 'status@broadcast') continue;

            // Skip messages sent by us (our own outgoing messages).
            // We ONLY want to process messages sent TO us by other people.
            if (msg.key.fromMe) continue;

            const fromNumber = from.split('@')[0];
            
            // Extract text message content robustly
            const text = extractText(msg.message);
            const displayName = msg.pushName || '';

            if (text) {
                console.log(JSON.stringify({
                    type: 'message',
                    from: fromNumber,
                    jid: from,
                    body: text,
                    name: displayName
                }));
            }
        }
    });
}

// Register stdin command listener ONCE globally to prevent MaxListenersExceeded memory leaks
process.stdin.on('data', async (data) => {
    if (!sock) return;
    try {
        const line = data.toString().trim();
        if (!line) return;
        const cmd = JSON.parse(line);
        
        if (cmd.type === 'send') {
            const jid = cmd.to.includes('@') ? cmd.to : `${cmd.to}@s.whatsapp.net`;
            await sock.sendMessage(jid, { text: cmd.body });
            console.log(JSON.stringify({ type: 'send_success', to: cmd.to }));
        } else if (cmd.type === 'logout') {
            await sock.logout();
            console.log(JSON.stringify({ type: 'logout_success' }));
            process.exit(0);
        }
    } catch (err) {
        console.error(JSON.stringify({ type: 'error', message: err.message }));
    }
});

// Start the client thread
start();
