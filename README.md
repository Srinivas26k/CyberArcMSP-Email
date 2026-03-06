# CyberArc Outreach — AI-Powered B2B Email Outreach Platform

[![CI](https://github.com/Srinivas26k/CyberArcMSP-Email/actions/workflows/ci.yml/badge.svg)](https://github.com/Srinivas26k/CyberArcMSP-Email/actions/workflows/ci.yml)
[![Build](https://github.com/Srinivas26k/CyberArcMSP-Email/actions/workflows/build.yml/badge.svg)](https://github.com/Srinivas26k/CyberArcMSP-Email/actions/workflows/build.yml)
[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)

> **⚠️ PROPRIETARY SOFTWARE — All rights reserved.**
> This repository is private. Cloning, forking, copying, or redistribution in any form is strictly prohibited without a valid paid license. See [LICENSE](LICENSE) for full terms.

## 1. Overview

CyberArc Outreach is a self-contained **Electron + FastAPI** desktop application for intelligent, secure B2B email outreach. It combines a local encrypted database, multi-provider LLM email generation, Apollo.io lead enrichment, and multi-account SMTP dispatching into a single installable app — no cloud backend required.

**Key principles:**
- 🔒 **Zero-Config Security** — AES-256 encrypted SQLCipher vault, hardware-locked key derivation, no `.env` files
- 🤖 **Multi-LLM Fallback** — Groq → OpenRouter → OpenAI → Anthropic → Gemini → Ollama Cloud with automatic failover
- 📧 **Multi-Account Sending** — Round-robin, parallel, or batch strategies across unlimited SMTP/Resend accounts
- 🔍 **Apollo.io Integration** — 2-step search (free) + bulk match (credits) for lead enrichment
- 📊 **Real-Time Progress** — Server-Sent Events (SSE) for live campaign status in the UI

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Electron Shell  (main.js / preload.js)                 │
│  ├── Spawns Python backend on app start                 │
│  └── Loads UI at http://127.0.0.1:PORT                  │
├─────────────────────────────────────────────────────────┤
│  FastAPI Backend  (app/)                                │
│  ├── REST API (v1)  —  leads, campaigns, settings       │
│  ├── SSE endpoint   —  real-time campaign progress      │
│  ├── CampaignService — async batch send loop            │
│  ├── LLM Client     — multi-provider email generation   │
│  ├── Email Engine    — SMTP / Resend dispatcher         │
│  └── SQLCipher Vault — encrypted settings & API keys    │
├─────────────────────────────────────────────────────────┤
│  SrvDB (srvdb/)     — semantic dedup & context search   │
├─────────────────────────────────────────────────────────┤
│  UI (ui/)           — vanilla HTML/CSS/JS SPA           │
└─────────────────────────────────────────────────────────┘
```

### 2.1. Secure Data Layer

- **SQLCipher vault** (`vault.db`) stores API keys, email accounts, lead data — all AES-256 encrypted at rest
- **Hardware-locked key** — encryption key derived from machine UUID; database is useless on another machine
- **No `.env` files** — all secrets managed through the UI → vault pipeline

### 2.2. Intelligence Layer

- **SrvDB** — local semantic vector database for pitch-overlap detection and dynamic context injection
- **Multi-provider LLM** — per-slot priority ordering with automatic fallback on failure
- **Dynamic prompt generation** — persona-aware prompts with knowledge-base context injection

## 3. Features

| Feature | Description |
|---|---|
| **Campaign Engine** | Async batch sender with adaptive delay, auto-retry, and SSE progress |
| **Craft & Preview** | Draft individual emails with LLM, preview before sending |
| **Multi-Identity** | Switch between B2B agency and personal/job-seeker personas |
| **Apollo Search** | Find leads by title, company, location with 1–100 employee range |
| **Outbox & Timeline** | Full send history with sender tracking, 5 sort modes |
| **Stuck-Lead Recovery** | Auto-resets "drafting" leads to "pending" on startup |
| **Email Templates** | HTML-wrapped emails with dynamic content injection |
| **Reply Detection** | IMAP-based reply checking across all sender accounts |

### 3.1. Supported LLM Providers

| Provider | Format | Notes |
|---|---|---|
| Groq | OpenAI-compat | Fastest inference, recommended for primary slot |
| OpenRouter | OpenAI-compat | Access to 100+ models |
| OpenAI | Native | GPT-4o, GPT-4o-mini |
| Anthropic | Messages API | Claude 3.5 Sonnet, Opus |
| Google Gemini | OpenAI-compat | Gemini 1.5 Pro / Flash |
| Ollama Cloud | Ollama API | Self-hosted models via Ollama |

## 4. Tech Stack

| Layer | Technology |
|---|---|
| Desktop | Electron 29 + Bun |
| Backend | Python 3.12, FastAPI, SQLModel, uvicorn |
| Database | SQLCipher (AES-256), SrvDB (vectors) |
| LLM | httpx async client, multi-provider |
| Email | smtplib / Resend API, IMAP reply check |
| Search | Apollo.io REST API |
| Build | electron-builder (NSIS, AppImage, DMG) |
| CI/CD | GitHub Actions (lint → test → build → release) |
| Package mgr | uv (Python), Bun (Node) |

## 5. Getting Started

> **Note:** You must have a valid license to use this software. Contact srinivasvarma764@gmail.com for licensing.

### 5.1. Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager
- **[Bun](https://bun.sh/)** — JavaScript runtime (for Electron)

### 5.2. Install

```bash
# Python dependencies
uv sync

# Node / Electron dependencies
bun install
```

### 5.3. Run (Development)

**Option A — Backend only** (API at `http://127.0.0.1:8000`):
```bash
uv run uvicorn app.main:app --reload
```

**Option B — Full desktop app** (Electron + backend):
```bash
bun run start
```

### 5.4. Build Installers

```bash
# Linux  → dist/*.AppImage + dist/*.deb
bun run dist:linux

# Windows → dist/*-Setup.exe + dist/*.zip
bun run dist:win

# macOS  → dist/*.dmg
bun run dist:mac
```

## 6. Project Structure

```
├── app/                    # FastAPI backend
│   ├── api/v1/             #   REST endpoints & controllers
│   ├── core/               #   config, db, SSE, vault, state
│   ├── models/             #   SQLModel table definitions
│   ├── repositories/       #   data access layer
│   ├── schemas/            #   Pydantic request/response schemas
│   ├── services/           #   campaign, lead, sequence services
│   └── utils/              #   LLM client, email engine, Apollo, prompts
├── electron/               # Electron shell (main.js, preload.js)
├── ui/                     # Frontend SPA
│   ├── index.html          #   single-page HTML
│   ├── css/                #   component & layout styles
│   └── js/                 #   api, router, SSE, page modules
├── srvdb/                  # Semantic vector database module
├── scripts/                # Build helpers (download_uv, build_send)
├── tests/                  # Pytest suite
├── .github/workflows/      # CI (lint/test) + Build & Release
├── package.json            # Electron/Bun config & build scripts
├── pyproject.toml          # Python project metadata & deps
├── LICENSE                 # Proprietary license — all rights reserved
└── main.py                 # CLI entry point
```

## 7. CI/CD

The repository includes two GitHub Actions workflows:

| Workflow | Trigger | Purpose |
|---|---|---|
| **CI** (`ci.yml`) | Push to `master`, PRs | Ruff lint, pytest, type checking |
| **Build & Release** (`build.yml`) | Version tags (`v*`), manual | Lint → test → build Win/Linux/macOS → GitHub Release |

### Release Process

```bash
# 1. Bump version in package.json
# 2. Commit and tag
git tag v2.3.9
git push origin v2.3.9
# 3. GitHub Actions builds all platforms and creates a Release
```

## 8. Configuration

All settings are managed through the **Settings** page in the UI:

- **LLM Providers** — add API keys for up to 3 priority slots
- **Email Accounts** — SMTP credentials (host, port, user, password)
- **Apollo API Key** — for lead search & enrichment
- **Email Defaults** — from name, subject prefix, signature

Settings are encrypted and stored locally in the SQLCipher vault — never transmitted externally.

## 9. Data Safety

Your data lives in the **user-data folder**, not the install directory:

| Platform | Path |
|---|---|
| Windows | `%APPDATA%\CyberArc Outreach\database.db` |
| macOS | `~/Library/Application Support/CyberArc Outreach/database.db` |
| Linux | `~/.config/CyberArc Outreach/database.db` |

Upgrading the app never touches your leads, accounts, or settings. Use **Records → Download Full Database Backup** for extra safety.

## 10. License

**Proprietary — © 2024-2026 CyberArc MSP. All rights reserved.**

This software is licensed under a **commercial proprietary license**. Unauthorized copying, cloning, forking, modification, distribution, or any form of redistribution is **strictly prohibited** and may result in civil and criminal penalties.

See [LICENSE](LICENSE) for the full license agreement.

For licensing inquiries: **cto.srinivas.nampalli@cyberarcmsp.com**
