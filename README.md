# REKOV
```
 ██████╗ ███████╗██╗  ██╗ ██████╗ ██╗   ██╗
 ██╔══██╗██╔════╝██║ ██╔╝██╔═══██╗██║   ██║
 ██████╔╝█████╗  █████╔╝ ██║   ██║██║   ██║
 ██╔══██╗██╔══╝  ██╔═██╗ ██║   ██║╚██╗ ██╔╝
 ██║  ██║███████╗██║  ██╗╚██████╔╝ ╚████╔╝
 ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝   ╚═══╝
```
> **Hospital AI Queue Management System** — by **[pheonix14](https://github.com/pheonix14)**

[![GitHub release](https://img.shields.io/github/v/tag/pheonix14/rekov?label=release&color=teal)](https://github.com/pheonix14/rekov/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/frontend-Next.js-black.svg)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Supabase](https://img.shields.io/badge/database-Supabase-3ECF8E.svg)](https://supabase.com/)

---

## 📑 Table of Contents

- [What is REKOV?](#-what-is-rekov)
- [v10 Release Notes](#-v10-release-notes)
- [Architecture Overview](#-architecture-overview)
- [Complete File Structure](#-complete-file-structure)
- [User Guide — Getting Started](#-user-guide--getting-started)
- [Mode 1 — Web UI](#-mode-1--web-ui)
- [Mode 2 — RITMO Terminal](#-mode-2--ritmo-terminal)
- [Mode 3 — Backend Server](#-mode-3--backend-server-advanced)
- [RITMO In-Chat Commands](#-ritmo-in-chat-commands)
- [Offline Models (ONNX)](#-offline-models-onnx)
- [Configuration](#-configuration)
- [API Reference](#-api-reference)
- [Database & Supabase](#-database--supabase)
- [Credits](#-credits)

---

## 🏥 What is REKOV?

**REKOV** is a full-stack hospital queue management and AI assistant system. It handles patient check-in, ticket booking, queue management, receipt generation, and AI-powered symptom triage — all in one system.

Patients can interact through:

| Channel | Description |
|---------|-------------|
| **Web UI** | Next.js kiosk-style browser interface (desktop/tablet/mobile) |
| **RITMO Normal Mode** | Step-by-step terminal form — name → phone → department → book → receipt |
| **RITMO AI Mode** | AI-powered chat that understands symptoms and books appointments automatically |
| **RITMO Voice Mode** | Always-listening voice assistant — speak naturally, hands-free |

Everything runs from **one command**: `python main.py`

---

## 🚀 v10 Release Notes

### What's New in v10

#### 🎯 3-Mode RITMO Launcher (Major)
The RITMO AI assistant now has **3 distinct modes** accessible from a single sub-menu:

| # | Mode | What it does |
|---|------|-------------|
| **1** | **Normal Mode** | Guided step-by-step booking form in the terminal. Pick department, enter patient details, confirm, generate receipt — no AI needed |
| **2** | **RITMO AI Mode** | Chat with Qwen 72B (online via HuggingFace) or Qwen 0.5B–3B (offline via ONNX). Understands symptoms in English/Hindi/Hinglish, recommends departments, auto-books tickets |
| **3** | **Voice Mode** | Always-listening speech-to-text loop with 3 STT engine choices: Google Web Speech (online), Vosk (100% offline), or Manual Keyboard fallback |

#### 🔧 Menu Restructure
- **Option 2** is now **RITMO Terminal** (no ports, no uvicorn — pure terminal)
- **Option 3** is now **Backend Server** (advanced users — FastAPI on :4040)
- No more confusion: pressing `2` gives you an instant terminal experience

#### 📝 Independent Ticket Pipeline
- `ritmo/ticketflow.py` — Complete standalone ticket booking + HTML receipt + QR code generation
- Talks **directly** to Supabase REST API — no backend dependency
- Falls back to SQLite when Supabase is unreachable
- Receipts stored in Supabase Storage `receipts` bucket with scannable QR links
- ASCII QR art displayed in terminal after each booking

#### 📋 Normal Mode Features
- Department selector with 12 hospital departments (Cardiology, Neurology, ENT, etc.)
- Patient detail collection: name, phone, age, notes
- Confirmation box before booking
- Auto receipt generation with QR code
- Session ID tracking stored in Supabase

#### 🎤 Voice Mode Features
- STT Engine picker at startup (Google / Vosk / Keyboard)
- Auto-installs dependencies on first use (`SpeechRecognition`, `edge-tts`, `pygame`)
- Vosk downloads a 40MB offline model once — then works without internet forever
- TTS responses via `edge-tts` (Microsoft Edge neural voices)

#### 🏗️ Infrastructure
- `awake/` — Keep-alive system that prevents Render free-tier from sleeping
- `base/supabase/sbcheck.py` — Comprehensive Supabase health checker
- `base/migrations/` — Full SQL migration chain with RLS policies
- `ritmo/ritmoscan.py` — Live hospital data scanner
- `ritmo/ritmolog.py` — Session event logger

### Breaking Changes
- Main menu option numbers have changed: **2 = RITMO Terminal**, **3 = Backend Server**
- Old `requirements.txt` at root removed — use `rekov/requirements.txt` instead

---

## 🏗️ Architecture Overview

```
python main.py
       │
       ├─ [1] Web UI       →  rekov/ (FastAPI backend on :4040)
       │                      rekoviu/ (Next.js frontend on :3000)
       │
       ├─ [2] RITMO Term   →  interface.py → ritmo sub-menu
       │                      ├─ [1] Normal Mode  →  ritmo/normal_mode.py
       │                      ├─ [2] AI Mode      →  ritmo/ritmocli.py
       │                      └─ [3] Voice Mode   →  ritmo/voice.py
       │
       └─ [3] Backend Only  →  rekov/launcher.py → uvicorn :4040

Shared Layers:
  huggfaceonnx/  ←── HuggingFace API calls + ONNX offline inference
  base/          ←── Database, schemas, migrations, Supabase client
  data/          ←── Local receipts, logs, keywords, offline backups
  awake/         ←── Keep-alive pinger for cloud deployments
```

---

## 📁 Complete File Structure

> Every file and folder explained — so anyone can understand the project at a glance.

```
rekov-6.0.0/
│
├── main.py                          # 🚪 Root entry point — runs interface.py
├── interface.py                     # 🎛️  Interface Manager — shows banner, 3-mode menu
├── rekov_credits.py                 # 🏷️  ASCII banner + live GitHub contributor credits
├── config.json                      # 🔐 Credentials (HF token + Supabase — gitignored)
├── config.example.json              # 📋 Template for config.json (safe to commit)
├── .gitignore                       # 🚫 Git ignore rules
├── docker-compose.yml               # 🐳 Docker Compose for full-stack deployment
├── Dockerfile                       # 🐳 Root Dockerfile
├── render.yaml                      # ☁️  Render.com deployment config
├── README.md                        # 📖 This file
│
├── ritmo/                           # 🤖 RITMO AI Assistant (100% terminal — no ports)
│   ├── __init__.py                  #    Package init + version info
│   ├── __main__.py                  #    Allows `python -m ritmo` execution
│   ├── normal_mode.py               #    ✨ Normal Mode — step-by-step guided booking form
│   ├── ritmocli.py                  #    🧠 AI Mode — HuggingFace / ONNX offline chat
│   ├── voice.py                     #    🎤 Voice Mode — STT + TTS always-listening loop
│   ├── ticketflow.py                #    🎫 Ticket booking + receipt + QR pipeline (standalone)
│   ├── booking.py                   #    📋 Booking helpers shared across modes
│   ├── support.py                   #    🔧 Config checker + interactive fix wizard
│   ├── ritmoscan.py                 #    🔍 Live hospital data scanner
│   ├── ritmolog.py                  #    📊 Session event logger (tracks AI interactions)
│   ├── pull.py                      #    📥 Pull hospital data from Supabase
│   ├── spinner.py                   #    ⏳ Terminal spinner animation
│   └── pulldata/                    #    📂 Cached hospital data
│       ├── hospital_data.json       #       Departments, doctors, schedules
│       └── ritmoscan.py             #       Data scanner script
│
├── rekov/                           # ⚙️  FastAPI Backend Server
│   ├── main.py                      #    FastAPI app factory + CORS + router mounting
│   ├── launcher.py                  #    Uvicorn launcher with auto-install + port management
│   ├── requirements.txt             #    Python dependencies for the backend
│   ├── Dockerfile                   #    Backend-specific Docker image
│   ├── logger.py                    #    Structured logging setup
│   ├── generate_receipts.py         #    Server-side receipt PDF generator
│   ├── generate_api_receipts.py     #    API-triggered receipt generation
│   ├── test_receipts.py             #    Receipt generation tests
│   ├── test_supabase.py             #    Supabase connection tests
│   ├── test_voice.py                #    Voice endpoint tests
│   ├── test_offline.py              #    Offline model tests
│   │
│   ├── app/                         #    📦 FastAPI application package
│   │   ├── __init__.py
│   │   ├── core/                    #       Core config (settings, DB connections)
│   │   ├── routers/                 #       🛣️  API route handlers
│   │   │   ├── health.py            #          GET /api/v1/health
│   │   │   ├── kiosk.py             #          Kiosk ticket booking + receipt endpoints
│   │   │   ├── queue.py             #          Queue state + now-calling endpoints
│   │   │   ├── ai.py                #          AI chat endpoints (HF proxy)
│   │   │   ├── ai_voice.py          #          Voice-to-AI chat pipeline
│   │   │   ├── auth.py              #          Login / session auth
│   │   │   ├── doctor.py            #          Doctor schedule + availability
│   │   │   ├── receptionist.py      #          Receptionist dashboard endpoints
│   │   │   ├── mobile_session.py    #          Mobile patient session management
│   │   │   ├── session_log.py       #          Session event logging
│   │   │   ├── settings.py          #          Runtime settings management
│   │   │   ├── sync.py              #          Data sync endpoints
│   │   │   └── awake.py             #          Keep-alive ping endpoint
│   │   ├── schemas/                 #       📐 Pydantic request/response models
│   │   │   ├── auth.py              #          Auth schemas
│   │   │   └── kiosk.py             #          Kiosk ticket/receipt schemas
│   │   └── services/               #       🔨 Business logic layer
│   │
│   ├── docs/                        #    📚 Backend documentation
│   │   ├── COMPETITOR.md            #       Competitor analysis
│   │   └── clinical_software_weakness_mitigation_analysis.md
│   │
│   ├── rekovbot/                    #    🤖 Bot integrations
│   │   ├── session_manager.py       #       Multi-channel session management
│   │   ├── telegram/               #       Telegram bot router
│   │   └── whatsapp/               #       WhatsApp bot router
│   │
│   └── data/                        #    📊 Backend data storage
│       ├── database/               #       Session events CSV, local DB
│       ├── receipts_user/          #       Patient-facing receipt PDFs
│       └── receiptsour/            #       Hospital-copy receipt PDFs
│
├── rekoviu/                         # 🌐 Next.js Frontend (Web UI)
│   ├── package.json                 #    Node.js dependencies + scripts
│   ├── next.config.mjs              #    Next.js configuration
│   ├── tailwind.config.ts           #    Tailwind CSS configuration
│   ├── tsconfig.json                #    TypeScript configuration
│   ├── Dockerfile                   #    Frontend Docker image
│   ├── postcss.config.js            #    PostCSS configuration
│   ├── .eslintrc.json               #    ESLint rules
│   │
│   ├── public/                      #    Static assets (favicon, icons)
│   ├── scripts/                     #    Build helper scripts
│   │   └── patch-next-windows.js    #       Windows compatibility patch
│   │
│   └── src/
│       ├── app/                     #    📄 App Router pages
│       │   ├── page.tsx             #       / — Landing page
│       │   ├── layout.tsx           #       Root layout + providers
│       │   ├── globals.css          #       Global styles
│       │   ├── home/page.tsx        #       /home — Dashboard
│       │   ├── kiosk/page.tsx       #       /kiosk — Self-service kiosk
│       │   ├── voice-assistant/     #       /voice-assistant — RITMO web UI
│       │   ├── voice-splash/        #       /voice-splash — Voice intro screen
│       │   ├── queue-board/         #       /queue-board — Live queue display
│       │   ├── receptionist/        #       /receptionist — Staff dashboard
│       │   ├── doctor-desk/         #       /doctor-desk — Doctor view
│       │   ├── receipt/             #       /receipt — Receipt viewer
│       │   ├── history/             #       /history — Patient history
│       │   ├── schedules/           #       /schedules — Doctor schedules
│       │   ├── status/              #       /status — System status
│       │   ├── login/               #       /login — Authentication
│       │   ├── mobile-form/         #       /mobile-form — Mobile patient form
│       │   │   └── upload/          #          /mobile-form/upload — Document upload
│       │   └── awake/               #       /awake — Keep-alive status page
│       │
│       ├── components/              #    🧩 Reusable UI components
│       │   ├── common/              #       Shared components
│       │   │   ├── Header.tsx       #          Navigation header
│       │   │   ├── RekovNav.tsx     #          Main navigation bar
│       │   │   ├── MediVERSENav.tsx #          MediVERSE navigation
│       │   │   ├── SmartQRCard.tsx  #          QR code display card
│       │   │   ├── StatusBadge.tsx  #          Status indicator badge
│       │   │   ├── PageLoader.tsx   #          Loading spinner
│       │   │   ├── Marquee.tsx      #          Scrolling text marquee
│       │   │   ├── BackgroundLayer.tsx  # Background effects
│       │   │   ├── CursorEffect.tsx #          Custom cursor effects
│       │   │   └── GestureCursor.tsx#          Gesture-based cursor
│       │   ├── kiosk/               #       Kiosk-specific components
│       │   │   ├── CategoryNav.tsx  #          Department category selector
│       │   │   ├── DoctorCard.tsx   #          Doctor info card
│       │   │   ├── TicketModal.tsx  #          Ticket booking modal
│       │   │   ├── ComboCart.tsx    #          Multi-service cart
│       │   │   ├── PatientIdentity.tsx # Patient ID form
│       │   │   └── VitalsPicker.tsx #          Vitals input
│       │   ├── queue/               #       Queue display components
│       │   │   └── NowCallingCard.tsx#         Now-calling display
│       │   └── voice/               #       Voice UI components
│       │       └── VoiceCallOverlay.tsx # Voice call interface
│       │
│       ├── contexts/                #    🔄 React context providers
│       │   ├── CurrencyContext.tsx  #       Currency formatting
│       │   ├── GestureContext.tsx   #       Gesture handling
│       │   ├── LanguageContext.tsx  #       i18n language switching
│       │   └── VoiceCallContext.tsx #       Voice call state
│       │
│       ├── services/                #    🔌 API client layer
│       │   ├── api.ts              #       Axios API client + all endpoints
│       │   └── tts.ts              #       Text-to-speech service
│       │
│       └── types/                   #    📝 TypeScript type definitions
│           ├── index.ts            #       Shared types
│           └── modules.d.ts        #       Module declarations
│
├── huggfaceonnx/                    # 🧠 Shared HF + ONNX Layer
│   ├── __init__.py                  #    Package exports
│   ├── hfmanager.py                 #    HFManager — HuggingFace API calls (chat, health)
│   ├── onnx.py                      #    ONNX inference — model registry, load, generate
│   └── hugon.py                     #    ONNX model download + export utilities
│
├── base/                            # 🗄️  Database Layer + Model Cache
│   ├── __init__.py                  #    Package init + shared DB helpers
│   ├── README                       #    Database layer documentation
│   ├── database.py                  #    Supabase + SQLite connection manager
│   ├── models.py                    #    ORM model definitions
│   │
│   ├── schemas/                     #    📐 Database schemas
│   │   ├── auth.py                  #       Auth table schemas
│   │   └── kiosk.py                 #       Kiosk/ticket table schemas
│   │
│   ├── migrations/                  #    📦 SQL migrations (run in order)
│   │   ├── 001_initial.sql          #       Core tables: departments, doctors, tickets
│   │   ├── 002_supabase_schema.sql  #       Extended schema for Supabase
│   │   ├── create_receipts_bucket.sql#      Storage bucket for receipts
│   │   └── supabase_schema_rls.sql  #       Row Level Security policies
│   │
│   ├── seeds/                       #    🌱 Seed data
│   │   └── doctors.json             #       Default doctor records
│   │
│   ├── supabase/                    #    ☁️  Supabase utilities
│   │   └── sbcheck.py              #       Comprehensive Supabase health checker
│   │
│   ├── models/                      #    💾 ONNX model cache (auto-created)
│   │   └── Qwen2.5-*-onnx/        #       Downloaded ONNX models stored here
│   │
│   ├── data/                        #    📊 Local data files
│   └── logs/                        #    📋 Database operation logs
│
├── awake/                           # ⏰ Keep-Alive System
│   ├── __init__.py                  #    Package init
│   ├── keeper.py                    #    Pings backend periodically to prevent sleep
│   ├── cli.py                      #    CLI interface for keep-alive management
│   └── stats.py                     #    Uptime statistics tracker
│
├── data/                            # 📂 Shared Data Directory
│   ├── receipts/                    #    🎫 Generated HTML receipts + QR codes
│   │   └── TKT-XXXXXXXX/          #       Each ticket gets its own folder
│   │       ├── receipt.html        #          HTML receipt (uploadable to Supabase)
│   │       └── qr.png             #          QR code image
│   ├── database/                    #    📊 Session event data
│   ├── logs/                        #    📋 Application logs
│   ├── backup_offline/             #    💾 Offline backup data
│   ├── keywords.json               #    🔑 NLP keyword mappings
│   └── backupverifier_state.json   #    ✅ Backup verification state
│
└── leetcode_hard_50/                # 📝 Practice problems (not part of REKOV)
```

---

## 📖 User Guide — Getting Started

### Prerequisites

| Tool | Version | Required for |
|------|---------|-------------|
| Python | 3.10+ | Everything |
| Node.js | 18+ | Web UI only |
| pip | latest | Python packages |

### Install

```bash
# 1. Clone
git clone https://github.com/pheonix14/rekov.git
cd rekov

# 2. Python dependencies (backend + RITMO)
pip install fastapi uvicorn supabase requests

# 3. For RITMO Offline Mode (ONNX — optional):
pip install optimum[onnxruntime] onnxruntime transformers

# 4. For Voice Mode (auto-installs on first use, but you can pre-install):
pip install SpeechRecognition sounddevice edge-tts pygame

# 5. Frontend (only if using Web UI):
cd rekoviu && npm install && cd ..
```

### Configure

```bash
# Copy the example config
cp config.example.json config.json

# Edit with your credentials:
```

```jsonc
{
  "hf_token": "hf_YOUR_TOKEN_HERE",       // HuggingFace access token (free)
  "supabase": {
    "url":  "https://xxxx.supabase.co",    // Your Supabase project URL
    "key":  "eyJ..."                       // Your Supabase anon key
  }
}
```

> ⚠️ **Never commit `config.json` to git.** It is gitignored.

### Run

```bash
python main.py
```

You'll see:
```
  ██████╗ ███████╗██╗  ██╗ ██████╗ ██╗   ██╗
  ██╔══██╗██╔════╝██║ ██╔╝██╔═══██╗██║   ██║
  ...

    1  ->  Web UI          (browser — FastAPI + Next.js)
    2  ->  RITMO Terminal  (Normal / AI / Voice — no ports)
    3  ->  Backend Server  (FastAPI on :4040 — for advanced users)

  Enter choice [1/2/3]:
```

---

## 🌐 Mode 1 — Web UI

**What it does:** Launches the full browser experience — FastAPI backend on `:4040` + Next.js frontend on `:3000`.

```bash
python main.py → press 1
```

| Page | URL | Description |
|------|-----|-------------|
| Landing | `localhost:3000` | Home page |
| Kiosk | `localhost:3000/kiosk` | Self-service patient kiosk |
| Voice Assistant | `localhost:3000/voice-assistant` | RITMO in the browser |
| Queue Board | `localhost:3000/queue-board` | Live queue display |
| Receptionist | `localhost:3000/receptionist` | Staff dashboard |
| Doctor Desk | `localhost:3000/doctor-desk` | Doctor view |
| Receipt | `localhost:3000/receipt?id=TKT-XXX` | View/print receipt |

---

## 🤖 Mode 2 — RITMO Terminal

**What it does:** Pure terminal experience. **No ports. No uvicorn. No browser.** Just you and the terminal.

```bash
python main.py → press 2
```

You'll see:
```
  ╔══════════════════════════════════════╗
  ║   RITMO  —  Select Mode             ║
  ╚══════════════════════════════════════╝

    1  ->  Normal Mode   (guided form)
    2  ->  AI Mode       (chat with AI)
    3  ->  Voice Mode    (speech — always listening)
```

### 2.1 — Normal Mode

Step-by-step guided booking:
```
→ Select department (1-12)
→ Enter patient name
→ Enter phone number
→ Enter age
→ Add notes (optional)
→ Confirm booking
→ Receipt generated + QR code displayed in ASCII
→ Receipt uploaded to Supabase Storage
```

### 2.2 — AI Mode

Chat with RITMO AI. Describe your symptoms, and RITMO will:
1. Understand what's wrong (English, Hindi, Hinglish)
2. Ask clarifying questions
3. Recommend a department
4. Book the appointment when you're ready
5. Generate receipt + QR code

Engine choices at startup:
- **HuggingFace** — Qwen 72B via HF Inference API (needs internet + HF token)
- **Offline** — Qwen 0.5B–3B via ONNX Runtime (runs locally, no internet after first download)

### 2.3 — Voice Mode

Always-listening voice loop. Speak naturally — RITMO listens, understands, responds with TTS.

STT engine picker at startup:
| Option | Engine | Internet? | Notes |
|--------|--------|-----------|-------|
| A | Google Web Speech | Yes | Free, no API key needed |
| B | Vosk Offline | No | Downloads 40MB model once |
| C | Manual Keyboard | No | Type instead of speak (fallback) |

---

## ⚙️ Mode 3 — Backend Server (Advanced)

**What it does:** Launches only the FastAPI backend on `:4040`. For advanced users, API development, or bot integrations.

```bash
python main.py → press 3
```

---

## 💬 RITMO In-Chat Commands

| Command | Action |
|---------|--------|
| `/quit` or `/q` | Exit RITMO |
| `/clear` | Reset conversation history |
| `/history` | Show conversation history |
| `/model` | Show current AI model (offline mode) |
| `/support` | Live config + health check |
| `/help` | Show all commands |

### RITMO Action Tags

When RITMO detects a booking intent, it outputs:
```
[BOOK_TICKET] dept_id=dep_card doctor_id=dr_01 priority=STANDARD patient_name=John
[EMERGENCY]   → routes to dep_emg immediately
```

The CLI automatically parses these and triggers the booking pipeline.

---

## 🧠 Offline Models (ONNX)

| Option | Model | Download Size | RAM Needed |
|--------|-------|:------------:|:----------:|
| 1 (default) | `Qwen/Qwen2.5-0.5B-Instruct` | ~1 GB | ~1.5 GB |
| 2 | `Qwen/Qwen2.5-1.5B-Instruct` | ~3 GB | ~4 GB |
| 3 | `Qwen/Qwen2.5-3B-Instruct` | ~6 GB | ~8 GB |

- Models auto-download and export to ONNX on first run (one-time)
- Cached to `base/models/<model>-onnx/`
- No PyTorch needed — pure ONNX Runtime
- After first download: **100% offline, zero internet**

---

## ⚙️ Configuration

### config.json

| Key | Required | Description |
|-----|----------|-------------|
| `hf_token` | For AI Mode (HF) | HuggingFace access token — get one free at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |
| `supabase.url` | For cloud storage | Your Supabase project URL |
| `supabase.key` | For cloud storage | Your Supabase anon/public key |

### Check your config

```bash
python ritmo/support.py           # health check
python ritmo/support.py --fix     # interactive fix wizard
```

### Environment Variables (auto-set from config.json)

| Variable | Source | Used by |
|----------|--------|---------|
| `SUPABASE_URL` | config.json | Backend + RITMO |
| `SUPABASE_KEY` | config.json | Backend + RITMO |
| `NEXT_PUBLIC_SUPABASE_URL` | config.json | Frontend |
| `NEXT_PUBLIC_SUPABASE_KEY` | config.json | Frontend |
| `HF_TOKEN` | config.json | RITMO AI Mode |
| `NEXT_PUBLIC_API_URL` | auto (`localhost:4040`) | Frontend |

---

## 🔌 API Reference

Base URL: `http://localhost:4040/api/v1`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check — returns `{"status": "ok"}` |
| `/ai_voice/chat` | POST | Send text to RITMO AI, get response |
| `/kiosk/ticket` | POST | Book a new ticket |
| `/kiosk/receipt/{id}` | GET | Get receipt by ticket ID |
| `/kiosk/departments` | GET | List all departments |
| `/kiosk/doctors` | GET | List all doctors |
| `/queue` | GET | Current queue state |
| `/queue/now-calling` | GET | Currently called ticket numbers |
| `/doctor/schedule` | GET | Doctor schedule |
| `/receptionist/dashboard` | GET | Receptionist overview |
| `/auth/login` | POST | Staff login |
| `/session-log` | POST | Log session events |
| `/settings` | GET/PUT | Runtime settings |
| `/sync` | POST | Data sync trigger |
| `/awake/ping` | GET | Keep-alive ping |

---

## 🗄️ Database & Supabase

### Tables

| Table | Purpose |
|-------|---------|
| `departments` | Hospital departments (Cardiology, Neurology, etc.) |
| `doctors` | Doctor records + schedules |
| `tickets` | Patient tickets (booking records) |
| `queue` | Live queue state |
| `session_events` | AI interaction logs |
| `settings` | Runtime configuration |

### Storage Buckets

| Bucket | Purpose |
|--------|---------|
| `receipts` | HTML receipts with QR codes — publicly accessible via URL |

### Migrations

Run migrations in order in your Supabase SQL editor:
1. `base/migrations/001_initial.sql` — Core tables
2. `base/migrations/002_supabase_schema.sql` — Extended schema
3. `base/migrations/create_receipts_bucket.sql` — Storage bucket
4. `base/migrations/supabase_schema_rls.sql` — Row Level Security

### Offline Fallback

When Supabase is unreachable, REKOV automatically falls back to:
- **SQLite** for ticket storage
- **Local filesystem** for receipts (`data/receipts/`)
- All data syncs to Supabase when connection is restored

---

## 🐳 Docker

```bash
# Full stack
docker-compose up

# Backend only
docker build -t rekov-backend ./rekov
docker run -p 4040:4040 rekov-backend

# Frontend only
docker build -t rekov-frontend ./rekoviu
docker run -p 3000:3000 rekov-frontend
```

---

## ☁️ Deploy to Render

The `render.yaml` at the project root configures automatic deployment to [Render.com](https://render.com).

The `awake/` module keeps the free-tier service alive by pinging the backend periodically.

---

## 🙏 Credits

**REKOV** is built and maintained by:

**★ [pheonix14](https://github.com/pheonix14)** — Lead · Backend Architecture, AI Integration & RITMO Engine

> Live contributor list fetched at runtime from [github.com/pheonix14/rekov](https://github.com/pheonix14/rekov/graphs/contributors)

---

<sub>REKOV v10 · Hospital AI Queue Management System · [github.com/pheonix14/rekov](https://github.com/pheonix14/rekov)</sub>
