# 📡 CyberClaw Channel Setup Guide

> Connect CyberClaw to **8 messaging platforms** so your AI agent can answer messages from Telegram, Discord, WhatsApp, Slack, Signal, Matrix, IRC, and the built-in WebChat — all at once.

---

## Table of Contents

- [How Channels Work](#how-channels-work)
- [Quick Reference Table](#quick-reference-table)
- [DM Policy & Pairing](#dm-policy--pairing)
- [Channel Setup Guides](#channel-setup-guides)
  - [📱 Telegram](#-telegram)
  - [🎮 Discord](#-discord)
  - [📲 WhatsApp (Local QR)](#-whatsapp-local-qr)
  - [📲 WhatsApp (Cloud API)](#-whatsapp-cloud-api)
  - [💬 Slack](#-slack)
  - [🔒 Signal](#-signal)
  - [🏠 Matrix](#-matrix)
  - [📡 IRC](#-irc)
  - [🌐 WebChat](#-webchat)
- [CLI Commands](#cli-commands)
- [Troubleshooting](#troubleshooting)

---

## How Channels Work

CyberClaw uses a **worker-based architecture** for messaging:

```
                    ┌──────────────┐
  Telegram ─────►  │              │     ┌─────────────┐     ┌────────────────┐
  Discord  ─────►  │ ChannelWorker├────►│  AgentWorker ├────►│ DeliveryWorker │
  WhatsApp ─────►  │  (ingests)   │     │  (LLM reply) │     │  (sends reply) │
  Slack    ─────►  │              │     └─────────────┘     └────────────────┘
  ...      ─────►  └──────────────┘
```

1. **ChannelWorker** receives messages from all enabled platforms
2. Checks **DM policy** and **access control** (pairing, allowlist, or open)
3. Creates an **InboundEvent** and publishes it to the EventBus
4. **AgentWorker** picks up the event, runs it through the LLM agent
5. **DeliveryWorker** sends the LLM's reply back to the same platform

### Enabling Channels

Add a `channels` section to your `workspace/config.user.yaml`:

```yaml
channels:
  enabled: true    # ← Master switch — MUST be true
  telegram:        # ← Add any channels you want below
    enabled: true
    bot_token: "..."
```

> **Important:** `channels.enabled: true` is the master switch. Without it, no channels will start even if individual ones are configured.

---

## Quick Reference Table

| Channel | Connection Method | Requires | Free? | Setup Time |
|---------|------------------|----------|-------|------------|
| **Telegram** | Long polling | Bot token from @BotFather | ✅ Free | 2 min |
| **Discord** | WebSocket gateway | Bot token from Developer Portal | ✅ Free | 5 min |
| **WhatsApp (Local)** | Node.js subprocess (Baileys) | Node.js installed | ✅ Free | 3 min |
| **WhatsApp (Cloud)** | Webhook | Meta Business API credentials | 💰 Paid | 30 min |
| **Slack** | Socket Mode WebSocket | Bot token + App token | ✅ Free | 10 min |
| **Signal** | HTTP polling | signal-cli-rest-api Docker | ✅ Free | 15 min |
| **Matrix** | Long sync | Matrix account + access token | ✅ Free | 5 min |
| **IRC** | Raw TCP socket | Nothing — IRC is open | ✅ Free | 1 min |
| **WebChat** | Built-in (gateway) | Nothing | ✅ Free | 0 min |

---

## DM Policy & Pairing

Every channel supports a **DM policy** that controls who can talk to your agent:

| Policy | Behavior |
|--------|----------|
| `open` | **Anyone** can message your agent. No restrictions. |
| `allowlist` | Only users listed in `allow_from` can message. Others are silently ignored. |
| `pairing` | Unknown users get a **pairing code**. You approve them via CLI before they can chat. |

### How Pairing Works

1. **Unknown user** sends a message to your bot
2. Bot replies: *"CyberClaw pairing required. Approve this sender with: `/pairing approve telegram A3F1B2`"*
3. **You** run from your terminal:
   ```bash
   cyberclaw pairing approve telegram A3F1B2
   ```
4. User is now **approved** and can freely chat with the agent

### `allow_from` Wildcard

To skip all access control and let everyone in:

```yaml
allow_from:
  - '*'
```

---

## Channel Setup Guides

---

### 📱 Telegram

The easiest channel to set up. Uses long-polling — no server or webhook needed.

#### Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a **name** (e.g., "CyberClaw Agent")
4. Choose a **username** (e.g., `cyberclaw_agent_bot`)
5. BotFather gives you a **bot token** like:
   ```
   123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
   ```

#### Step 2: Configure

Add to `workspace/config.user.yaml`:

```yaml
channels:
  enabled: true
  telegram:
    enabled: true
    bot_token: "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
    dm_policy: open           # or "pairing" for approval-based access
    allow_from:
      - '*'                   # allow everyone (or list specific user IDs)
```

#### Step 3: Start Server

```bash
cyberclaw server
```

#### Step 4: Test

Open Telegram → search for your bot's username → send "Hello" → get a reply! 🎉

#### Optional: Restrict to Specific Users

```yaml
    dm_policy: allowlist
    allowed_user_ids:
      - "123456789"          # Your Telegram numeric user ID
```

> **Tip:** To find your Telegram user ID, message @userinfobot on Telegram.

---

### 🎮 Discord

Uses Discord's WebSocket gateway for real-time message handling.

#### Step 1: Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"** → name it "CyberClaw"
3. Go to **Bot** tab → click **"Add Bot"**
4. Under **Token**, click **"Reset Token"** → copy the bot token
5. Under **Privileged Gateway Intents**, enable:
   - ✅ **Message Content Intent**
6. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`
   - Bot Permissions: `Send Messages`, `Read Message History`
7. Copy the generated URL → paste in browser → invite bot to your server

#### Step 2: Configure

```yaml
channels:
  enabled: true
  discord:
    enabled: true
    bot_token: "your-discord-bot-token"
    channel_id: null          # null = respond in any channel, or set a specific channel ID
    dm_policy: open
    allow_from:
      - '*'
```

#### Step 3: Start & Test

```bash
cyberclaw server
```

Message the bot in your Discord server → get a reply! 🎮

#### Optional: Restrict to One Channel

```yaml
    channel_id: "1234567890123456789"   # Right-click channel → Copy Channel ID
```

---

### 📲 WhatsApp (Local QR)

**Recommended mode.** Uses your own WhatsApp account via QR code linking — no Business API needed.

#### Prerequisites

- **Node.js** installed (v16+)

#### Step 1: Link Your Device

```bash
cyberclaw channels login --channel whatsapp
```

A QR code appears in your terminal. Scan it:

1. Open **WhatsApp** on your phone
2. Go to **Settings → Linked Devices → Link a Device**
3. Scan the QR code

You'll see: `✔ WhatsApp successfully linked to 8801234567890`

#### Step 2: Configure

```yaml
channels:
  enabled: true
  whatsapp:
    enabled: true
    mode: local
    dm_policy: open
    allow_from:
      - '*'
```

#### Step 3: Start Server

```bash
cyberclaw server
```

Now when someone messages your WhatsApp number, CyberClaw will reply! 📱

> **Note:** Auth sessions persist in `~/.cyberclaw/whatsapp_auth/`. You only need to scan the QR code once.

---

### 📲 WhatsApp (Cloud API)

Uses Meta's official WhatsApp Business API. Requires a Meta Business account.

#### Step 1: Set Up Meta Business

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Create an App → select **Business** type
3. Add **WhatsApp** product
4. Get your **Phone Number ID** and **Access Token** from the API Setup page
5. Set up a **webhook URL** pointing to your server's public address

#### Step 2: Configure

```yaml
channels:
  enabled: true
  whatsapp:
    enabled: true
    mode: cloud
    phone_number_id: "your-phone-number-id"
    access_token: "your-permanent-access-token"
    verify_token: "cyberclaw-verify"       # Must match webhook config
    dm_policy: open
    allow_from:
      - '*'
```

#### Step 3: Register Webhook

Your server must be publicly accessible. Register the webhook URL:
```
https://your-domain.com/webhook/whatsapp
```

With verify token: `cyberclaw-verify`

---

### 💬 Slack

Uses Socket Mode (WebSocket) — no public server needed.

#### Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"** → **"From scratch"**
3. Name it "CyberClaw" → select your workspace

#### Step 2: Enable Socket Mode

1. Go to **Settings → Socket Mode** → enable it
2. Generate an **App-Level Token** with scope `connections:write`
   - This gives you a token starting with `xapp-...`

#### Step 3: Set Bot Permissions

Go to **OAuth & Permissions → Bot Token Scopes**, add:
- `chat:write`
- `channels:history`
- `im:history`
- `groups:history`

#### Step 4: Subscribe to Events

Go to **Event Subscriptions** → enable → Subscribe to bot events:
- `message.channels`
- `message.im`
- `message.groups`

#### Step 5: Install to Workspace

Go to **Install App** → click **"Install to Workspace"**. Copy the **Bot User OAuth Token** (`xoxb-...`).

#### Step 6: Configure

```yaml
channels:
  enabled: true
  slack:
    enabled: true
    bot_token: "xoxb-your-bot-token"
    app_token: "xapp-your-app-level-token"
    dm_policy: open
    allow_from:
      - '*'
```

> **Note:** Slack replies are thread-aware — if someone messages in a thread, the bot replies in the same thread.

---

### 🔒 Signal

Uses the `signal-cli-rest-api` Docker container as a bridge.

#### Step 1: Run signal-cli Docker

```bash
docker run -d \
  --name signal-api \
  -p 8080:8080 \
  -v $HOME/.signal-cli:/home/.local/share/signal-cli \
  bbernhard/signal-cli-rest-api
```

#### Step 2: Register / Link a Phone Number

```bash
# Register a new number
curl -X POST "http://localhost:8080/v1/register/+8801234567890"

# Or link to existing Signal account
curl -X GET "http://localhost:8080/v1/qrcodelink?device_name=CyberClaw"
```

#### Step 3: Configure

```yaml
channels:
  enabled: true
  signal:
    enabled: true
    api_url: "http://localhost:8080"
    phone_number: "+8801234567890"
    dm_policy: open
    allow_from:
      - '*'
```

---

### 🏠 Matrix

Connects to any Matrix homeserver (Element, matrix.org, self-hosted).

#### Step 1: Get Access Token

**Option A:** Via Element client:
1. Log in to Element → Settings → Help & About → scroll down → **"Access Token"**

**Option B:** Via API:
```bash
curl -X POST "https://matrix.org/_matrix/client/r0/login" \
  -H "Content-Type: application/json" \
  -d '{"type":"m.login.password","user":"@cyberclaw:matrix.org","password":"yourpassword"}'
```

#### Step 2: Configure

```yaml
channels:
  enabled: true
  matrix:
    enabled: true
    homeserver: "https://matrix.org"
    user_id: "@cyberclaw:matrix.org"
    access_token: "your-matrix-access-token"
    allowed_rooms: []              # Empty = all rooms
    allow_from:
      - '*'
```

---

### 📡 IRC

Pure TCP socket connection — no libraries, no tokens, no authentication.

#### Configure

```yaml
channels:
  enabled: true
  irc:
    enabled: true
    server: "irc.libera.chat"
    port: 6667
    nick: "CyberClaw"
    channels:
      - "#cyberclaw"
    use_ssl: false
    allow_from:
      - '*'
```

That's it! CyberClaw will connect, join the channel, and respond to messages.

---

### 🌐 WebChat

Built-in browser chat — zero configuration. Just enable it and visit the Web UI.

#### Configure

```yaml
channels:
  enabled: true
  webchat:
    enabled: true
```

#### Access

```bash
cyberclaw gateway start
# or
cyberclaw server
```

Then visit: **http://localhost:8000/ui**

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `cyberclaw channels list` | Show all configured channels with status |
| `cyberclaw channels login -c whatsapp` | Interactive WhatsApp QR code pairing |
| `cyberclaw pairing list` | Show pending and approved pairings |
| `cyberclaw pairing approve <channel> <code>` | Approve a user's pairing request |
| `cyberclaw pairing revoke <channel> <sender>` | Revoke an approved user |
| `cyberclaw server` | Start server with all enabled channels |
| `cyberclaw doctor` | Health check (warns about insecure DM policies) |

### Example: Full Pairing Flow

```bash
# 1. Start server
cyberclaw server

# 2. User messages your Telegram bot → gets pairing code "A3F1B2"
# 3. In another terminal:
cyberclaw pairing list
#   → Shows: telegram | user:123456 | A3F1B2 | pending

cyberclaw pairing approve telegram A3F1B2
#   → "Approved: platform-telegram:123456:789"

# 4. User can now freely chat with the agent!
```

---

## Multi-Channel Example

Run Telegram, WhatsApp, and WebChat simultaneously:

```yaml
channels:
  enabled: true

  telegram:
    enabled: true
    bot_token: "123456789:ABCdef..."
    dm_policy: pairing
    allow_from: []

  whatsapp:
    enabled: true
    mode: local
    dm_policy: open
    allow_from:
      - '*'

  webchat:
    enabled: true
```

```bash
cyberclaw server
# → ChannelWorker started with 3 channel(es)
```

---

## Troubleshooting

### "No channels configured"
Make sure you have `channels.enabled: true` (the master switch) AND at least one sub-channel with `enabled: true`.

### WhatsApp: "QR code not showing"
Run `cyberclaw channels login -c whatsapp` separately first. The QR only shows during the login flow, not during `cyberclaw server`.

### WhatsApp: "Messages received but no reply"
Check the log for `Received WhatsApp message from...` and `Session completed`. If sessions complete but delivery fails, your LLM provider might be down.

### Telegram: "Bot doesn't respond"
1. Make sure the bot token is correct (test with `curl https://api.telegram.org/bot<TOKEN>/getMe`)
2. Check `dm_policy` — if set to `pairing`, you need to approve yourself first

### Discord: "Bot is online but doesn't respond"
1. Enable **Message Content Intent** in the Developer Portal
2. Make sure the bot has `Send Messages` and `Read Message History` permissions

### Port 8000 already in use
Kill the old process or change the API port in config:
```yaml
api:
  host: "127.0.0.1"
  port: 8001    # Use a different port
```

### LLM provider errors
If all providers fail (rate limited, invalid key), the agent can't generate a reply. Check:
```bash
cyberclaw providers list
cyberclaw doctor
```
