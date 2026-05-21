const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const pino = require('pino');
const path = require('path');
const fs = require('fs');

async function start() {
    const authDir = process.argv[2] || path.join(__dirname, 'auth_info');
    
    // Ensure authDir exists
    if (!fs.existsSync(authDir)) {
        fs.mkdirSync(authDir, { recursive: true });
    }

    const { state, saveCreds } = await useMultiFileAuthState(authDir);

    // Use a completely silent logger for pino to prevent JSON logging clutter
    const logger = pino({ level: 'silent' });
    
    const sock = makeWASocket({
        auth: state,
        logger: logger,
        printQRInTerminal: true // Prints the QR code directly to terminal via qrcode-terminal
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr) {
            // Write a structured JSON line so Python knows a QR code is generated
            console.log(JSON.stringify({ type: 'qr', qr: qr }));
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

    sock.ev.on('messages.upsert', async (m) => {
        if (m.type !== 'notify') return;
        
        for (const msg of m.messages) {
            // Ignore messages sent by ourselves to avoid agent feedback loops
            if (msg.key.fromMe) continue;

            const from = msg.key.remoteJid;
            const fromNumber = from.split('@')[0];
            
            // Extract text message content
            const text = msg.message?.conversation || msg.message?.extendedTextMessage?.text;
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

    // Listen on stdin for commands from Python subprocess manager
    process.stdin.on('data', async (data) => {
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
}

// Start the client thread
start();
