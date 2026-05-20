# 🌌 CyberClaw — Advanced AI Orchestration Platform & Control Dashboard
> **An Enterprise-Grade, Multi-Channel Personal AI Agent System with Premium Web UI, Detached Background Task Store, Cryptographic Secrets Vault, and Real-Time Voice Speech-to-Text.**

---

<p align="center">
  <strong>Brought to You with ❤️ by <a href="https://www.youtube.com/channel/UCxDA3V7IciBGKqoC-m0dvxQ">Cyber Prince</a></strong>
</p>

<p align="center">
  <a href="https://github.com/your-username/cyberclaw/stargazers"><img src="https://img.shields.io/github/stars/your-username/cyberclaw?style=for-the-badge&color=7209b7" alt="Stars"></a>
  <a href="https://github.com/your-username/cyberclaw/network/members"><img src="https://img.shields.io/github/forks/your-username/cyberclaw?style=for-the-badge&color=f72585" alt="Forks"></a>
  <a href="https://github.com/your-username/cyberclaw/issues"><img src="https://img.shields.io/github/issues/your-username/cyberclaw?style=for-the-badge&color=4cc9f0" alt="Issues"></a>
  <a href="https://www.facebook.com/ImDarkMagician/"><img src="https://img.shields.io/badge/Facebook-Cyber%20Prince-1877F2?style=for-the-badge&logo=facebook" alt="Facebook"></a>
  <a href="https://www.youtube.com/channel/UCxDA3V7IciBGKqoC-m0dvxQ"><img src="https://img.shields.io/badge/YouTube-Cyber%20Prince-FF0000?style=for-the-badge&logo=youtube" alt="YouTube"></a>
</p>

---

## 🌟 Executive Overview & Market Readiness
**CyberClaw** is a state-of-the-art, modular personal AI system engineered in high-performance native Python. Designed to meet or exceed commercial standards for marketplaces like **CodeCanyon** and professional open-source registries, it provides a decoupled, event-driven assistant capable of running 24/7 across multiple messaging channels.

Featuring a premium **Dark Space Glassmorphic Single Page Web UI**, SQLite history & task registers, and a hardware-locked cryptographic vault, CyberClaw is the ultimate ready-to-sell or ready-to-deploy AI gateway.

---

## 🚀 Key Marketplace Features & Highlights

### ⚡ 1. Unified Model Catalog (`core/model_catalog.py`)
* Track pricing per million input/output tokens dynamically.
* Advanced query selectors for finding the cheapest or best vision/reasoning models.
* Dynamic live model discovery from Groq, OpenRouter, and standard `/v1/models` endpoints.

### ⚙️ 2. SQLite Background Task Engine (`core/tasks.py`)
* Asynchronous execution worker queue with concurrent semaphores, customizable timeouts, and automatic retry handling.
* Full ACID compliance persisted cleanly in a database.

### 🧠 3. Advanced Context Engine (`core/context_engine.py`)
* Prioritized context payload assembler that automatically constructs token-budgeted prompts from active data feeds and plugins.

### 📡 4. Multi-Channel Auto-Reply Pipeline (`core/auto_reply.py`)
* Inbound message debouncing, mention filters, rate-limiting, and thinking mode indicators.
* Out-of-the-box routing connectors for **Signal**, **Telegram**, **Discord**, **WhatsApp**, **Slack**, and **Matrix**.

### 🛠️ 5. Commercial-Grade AI Tools
* **Live Scraper:** URL link auto-extractor and scraper built with rigorous timeout boundaries.
* **Web Browser:** Playwright Chromium integration for deep research.
* **Web Search:** Multi-provider fallback registry supporting Brave Search, Tavily AI, and DuckDuckGo.
* **Media Creators:** Schemas for Suno AI MusicGen and Runway Video Gen.

### 🔒 6. AES Cryptographic Vault (`security/`)
* AES-256 Fernet symmetric encryption storing credentials locally in `vault.json`, locked by your machine's hardware fingerprint.

---

## 💻 The 17-Command CLI Masterclass
CyberClaw hosts 17 terminal operational triggers. Here is the direct command guide:

| Command | Action / Purpose | Example Code |
|:---|:---|:---|
| **`onboard`** | Initializes folder setup & configs | `cyberclaw onboard` |
| **`doctor`** | Runs 10+ diagnostic system checks | `cyberclaw doctor` |
| **`chat`** | Boots terminal interactive AI session | `cyberclaw chat` |
| **`agent`** | Spawns a single turn query for piping | `cyberclaw agent --message "Build check"` |
| **`server`** | Boots 24/7 scheduling process engine | `cyberclaw server` |
| **`gateway`** | Hosts Web UI control center & REST API | `cyberclaw gateway start` |
| **`config`** | Inspects or sets workspace parameters | `cyberclaw config show` |
| **`secrets`** | Cryptographic key manager (AES-256) | `cyberclaw secrets set KEY "val"` |
| **`sessions`** | Audits active database conversation logs | `cyberclaw sessions list` |
| **`pairing`** | Approves codes for secure chat pairing | `cyberclaw pairing approve --code "123"` |
| **`channels`** | Audits active chat pipelines status | `cyberclaw channels list` |
| **`providers`** | Lists LLM backends cleanly | `cyberclaw providers list` |
| **`talk`** | Boots PTT & Wake-word voice listener | `cyberclaw talk` |
| **`migrate-history`**| Converts legacy logs into robust SQLite | `cyberclaw migrate-history` |
| **`service`** | Registers background Windows NT Service | `cyberclaw service install` |
| **`update`** | Automated updater via package manager | `cyberclaw update` |
| **`version`** | Displays build, versions, and paths | `cyberclaw version` |

---

## 📦 Commercial Installation Blueprint

### 1. Simple Marketplace Installation
Users can install the package in one simple command:
```bash
# Direct local link
pip install -e .

# Or install with Speech-to-Text capabilities
pip install -e .[voice]
```

### 2. First-Time Setup Wizard
Generate your workspace configs, SQLite databases, and folders instantly:
```bash
cyberclaw onboard
```

### 3. Verification Protocol
Verify that everything is perfectly aligned and configured:
```bash
cyberclaw doctor
```

### 4. Lock Your API Credentials
Add your secret API credentials to the secure vault:
```bash
cyberclaw secrets set OPENAI_API_KEY "sk-..."
cyberclaw secrets set DEEPGRAM_API_KEY "dg-..."
```

### 5. Open the Premium Dashboard UI
Start your server gateway:
```bash
cyberclaw gateway start
```
👉 Now, simply launch your browser and navigate to **`http://localhost:8000/ui`** to view the space-themed Control Dashboard!

---

## 🎨 Premium Documentation Portal Included
Inside the **`docs/`** directory, you will find a fully styled and visual Documentation Website (`index.html`, `styles.css`, `app.js`):
* **Stunning Design:** Built with deep space glassmorphism panels, neon borders, and polished styling.
* **Developer Blueprints:** Clear visual steps on SQLite schema databases, multi-channel configurations, Prometheus parameters, and voice wake-word triggers.
* **Interactive Code Copier:** Easy copy buttons on all code blocks with instant visual indications.
* **Dynamic Search Filter:** Live filter that queries and displays documents in real-time.

---

## 💎 Project Credits & Support

This platform has been polished to production perfection by **Cyber Prince**. We take code quality and scaling seriously. 

* **Developer & Branding:** Cyber Prince
* **Facebook Profile:** [ImDarkMagician](https://www.facebook.com/ImDarkMagician/)
* **YouTube Channel:** [Cyber Prince Official](https://www.youtube.com/channel/UCxDA3V7IciBGKqoC-m0dvxQ)

For commercial customization, enterprise scaling, or feature requests, contact us directly through our social media handles!

---
*Developed under strict guidelines matching the OpenClaw parity requirements. Verified 100% operational with 31/31 unit tests passing.*
