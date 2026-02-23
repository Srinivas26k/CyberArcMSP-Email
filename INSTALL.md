# CyberArc MSP AI Outreach — Installation Guide

## Quick Install (All Platforms)

1. Download the file for your operating system from the **Releases** tab above
2. Install it (see instructions per OS below)
3. Launch the app, fill in your API keys in **Settings**
4. Start finding leads and sending emails!

---

## Windows

1. Download `CyberArc Outreach Setup 2.0.0.exe`
2. Double-click to run the installer
3. Allow the installer to run (click "More Info" → "Run anyway" if Windows SmartScreen appears)
4. Launch from Start Menu or Desktop shortcut

**Requires:** Python 3.12 + `uv` installed
- Install Python: https://python.org/downloads
- Install uv: open Command Prompt and run: `pip install uv`

---

## macOS

1. Download `CyberArc Outreach-2.0.0.dmg`
2. Open the `.dmg` and drag to Applications
3. Right-click the app → "Open" (first launch only, to bypass Gatekeeper)

**Requires:** Python 3.12 + `uv` installed
- Install via Homebrew: `brew install python uv`
- Or install Python from https://python.org/downloads, then: `pip install uv`

---

## Linux

1. Download `CyberArc Outreach-2.0.0.AppImage`
2. Make it executable: `chmod +x CyberArc\ Outreach*.AppImage`
3. Run it: `./CyberArc\ Outreach*.AppImage`

**Requires:** Python 3.12 + `uv` installed
- Ubuntu/Debian: `sudo apt install python3 python3-pip && pip install uv`

---

## API Keys Required

Set these in the **Settings** page after launching:

| Key | Where to get it |
|-----|----------------|
| **Groq API Key** | https://console.groq.com → API Keys |
| **Apollo.io API Key** | https://app.apollo.io/#/settings/integrations/api |
| **OpenRouter Key** *(optional fallback)* | https://openrouter.ai/keys |

Your email sender accounts are added in the **Email Accounts** page (use App Passwords, not your main password).
