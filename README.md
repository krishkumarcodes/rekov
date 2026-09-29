<div align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=009688&height=200&section=header&text=MediVERSE&fontSize=80&fontAlignY=35&desc=The%20Next-Gen%20Hospital%20Queue%20%26%20AI%20Assistant&descAlignY=55&descAlign=50" />
  
  <p align="center">
    <strong>Revolutionizing Healthcare Management with AI, Voice, and Seamless Automation</strong>
  </p>

  <p align="center">
    <a href="https://github.com/pheonix14/rekov/releases"><img src="https://img.shields.io/github/v/tag/pheonix14/rekov?label=release&color=009688&style=for-the-badge" alt="Release"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
    <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-Black?style=for-the-badge&logo=next.js&logoColor=white" alt="Next.js"></a>
    <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"></a>
    <a href="https://supabase.com/"><img src="https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase"></a>
  </p>
</div>

---

## 🌟 Why MediVERSE? (The Hackathon Hook)
**Imagine a hospital where queues manage themselves and AI triages patients before they even see a doctor.** 

MediVERSE (formerly REKOV) is a full-stack, AI-powered hospital management ecosystem. It seamlessly bridges the gap between physical hospital kiosks and advanced digital AI triage. Whether a patient uses the Next.js touch kiosk, chats with our LLM, or speaks directly to our Voice Assistant, MediVERSE handles check-in, dynamic queuing, and digital receipts (with instantly scannable QR codes) in real-time.

### ✨ Key Features That Wow
- 🚀 **Omnichannel Triage:** 
  - **Web UI:** Stunning Kiosk-style interface built on Next.js.
  - **AI Mode:** Understands symptoms in English, Hindi, and Hinglish using Qwen 72B (Online) or Qwen 0.5B-3B (100% Offline ONNX).
  - **Voice Mode:** Always-listening STT (Google/Vosk) + TTS (Edge-TTS).
- ⚡ **Digital Receipts via QR:** Instantly generates PDF receipts uploaded to Supabase Storage. Patients just scan a QR code and walk away.
- 🔋 **Resilient Architecture:** Fallback to local SQLite when offline. Once the internet returns, background threads seamlessly sync to Supabase.
- 🛠️ **Zero Config Launch:** Everything runs from one command: `python main.py`

---

## 📸 Sneak Peek
<div align="center">
  <img src="https://via.placeholder.com/800x400/009688/FFFFFF?text=Stunning+Next.js+Kiosk+UI" alt="Kiosk UI" width="48%">
  <img src="https://via.placeholder.com/800x400/121212/009688?text=RITMO+AI+Terminal" alt="RITMO AI Terminal" width="48%">
</div>

---

## 👨‍💻 Meet the Masterminds

<div align="center">
  <table>
    <tr>
      <td align="center">
        <a href="https://github.com/pheonix14">
          <img src="https://github.com/pheonix14.png" width="120px;" alt="Phoenix 14" style="border-radius:50%"/>
          <br />
          <b>Phoenix 14</b>
        </a>
        <br />
        <span style="color: #009688">Lead Developer</span><br/>
        <i>Backend Architecture, AI Integration & RITMO Engine</i>
      </td>
      <td align="center">
        <a href="https://github.com/krishkumarcodes">
          <img src="https://github.com/krishkumarcodes.png" width="120px;" alt="Shoden (Krish Kumar)" style="border-radius:50%"/>
          <br />
          <b>Shoden (Krish Kumar)</b>
        </a>
        <br />
        <span style="color: #009688">Second Developer</span><br/>
        <i>Frontend Wizardry, Web UI & UX Experience</i>
      </td>
      <td align="center">
        <a href="https://github.com/pheonix14/rekov/graphs/contributors">
          <img src="https://via.placeholder.com/120/1a1a1a/009688?text=Team" width="120px;" alt="Open Source Team" style="border-radius:50%"/>
          <br />
          <b>Contributors</b>
        </a>
        <br />
        <span style="color: #009688">Open Source Team</span><br/>
        <i>Thanks to everyone who contributed to MediVERSE!</i>
      </td>
    </tr>
  </table>
</div>

---

## 🛠️ Architecture

```mermaid
graph TD;
    Patient-->|Touches Screen| Kiosk[Next.js Frontend]
    Patient-->|Speaks/Chats| RITMO[RITMO Terminal/Voice]
    Kiosk-->|API Calls| FastAPI[FastAPI Backend]
    RITMO-->|Direct Logic| FastAPI
    FastAPI-->|Syncs| Supabase[(Supabase Cloud)]
    FastAPI-->|Fallback| SQLite[(Local SQLite)]
    FastAPI-->|Inference| HF[HuggingFace / ONNX]
```

---

## 🚀 Getting Started

### 1. Clone & Install
```bash
git clone https://github.com/pheonix14/rekov.git
cd rekov
pip install fastapi uvicorn supabase requests
```

### 2. Configure (Zero Leaks!)
Copy `config.example.json` to `config.json` and add your keys. **(Don't worry, `config.json` is gitignored so your keys are safe and will never be committed!)**
```jsonc
{
  "supabase": {
    "url": "https://xxxx.supabase.co",
    "key": "eyJ..."
  },
  "hf_token": "hf_..."
}
```

### 3. Launch
```bash
python main.py
```
*Choose between Web UI, RITMO Terminal, or Backend-only mode!*

---

## 📁 Complete File Structure (Simplified)
```text
rekov/
├── main.py              # Magic entry point
├── rekov/               # FastAPI Backend & System Launcher
├── rekoviu/             # Next.js Frontend
├── ritmo/               # RITMO AI / Voice Assistant 
├── base/                # DB Layer & Offline SQLite logic
└── data/                # Local data (Receipts, DBs, Offline Backups)
```

---

<div align="center">
  <b>Built with ❤️ for the future of healthcare.</b><br>
  <sub>MediVERSE v12.0.0 · Hospital AI Queue Management System</sub>
</div>
