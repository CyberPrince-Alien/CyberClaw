# CyberClaw Full Feature Roadmap

This is the practical path to grow CyberClaw from a lightweight Python assistant into an OpenClaw-like personal AI system.

## Current State

- CLI chat
- Foreground gateway/server
- Multi-provider LLM failover
- Tools and skills
- Long-term file memory through Vault
- Cron jobs
- WebSocket API
- Telegram and Discord channels
- DM pairing and allowlists for Telegram/Discord
- Global `cyberclaw` command launcher

## Priority 1: Core Operator Experience

- [x] `cyberclaw onboard`
- [x] `cyberclaw config`
- [x] `cyberclaw doctor`
- [x] `cyberclaw gateway start/status/restart`
- [x] Global `cyberclaw` command
- [x] One-shot `cyberclaw agent --message` command
- [x] Windows startup task helper scripts
- [ ] Built-in `cyberclaw gateway install-service` wrapper
- [ ] Log viewer command
- [ ] Built-in config profiles
- [ ] Safer secret storage

## Priority 2: Channels

- [x] Telegram
- [x] Discord
- [x] Pairing/allowlist security
- [ ] WhatsApp with QR login
- [ ] Slack
- [ ] Signal
- [ ] Google Chat
- [ ] Matrix
- [ ] Channel message send command
- [ ] Channel diagnostics

## Priority 3: Web Dashboard

- [ ] Dashboard server route
- [ ] Chat UI
- [ ] Session/history viewer
- [ ] Provider config page
- [ ] Channel config page
- [ ] Agent/skill browser
- [ ] Gateway status page

## Priority 4: Advanced Agent Runtime

- [ ] Tool approval policy
- [ ] Sandbox modes
- [x] CLI session list/show commands
- [ ] Session send tool
- [ ] Subagent run tracking
- [ ] Better token usage reporting
- [ ] Streaming responses
- [ ] Attachment support

## Priority 5: Voice And Media

- [ ] Speech-to-text provider
- [ ] Text-to-speech provider
- [ ] Audio message handling
- [ ] Image understanding
- [ ] File upload handling

## Priority 6: Production Hardening

- [ ] Encrypted secrets
- [ ] Audit logs
- [ ] Health endpoints
- [ ] Metrics
- [ ] Update/migration command
- [ ] Backup/export command
- [ ] Test suite expansion

## Next Recommended Build Order

1. Background service mode for Windows.
2. WhatsApp channel prototype.
3. Web dashboard MVP.
4. Session/history commands.
5. Safer secrets and channel diagnostics.
