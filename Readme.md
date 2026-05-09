# 💸 PayGuard - Onchain Autonomous Payment Agent

**PayGuard** is an AI agent that lets you send **one-time** and **recurring** USDC payments on Arbitrum Sepolia using natural language.

Built with LangGraph + APScheduler + SQLite for persistence.

---

## ✨ Features

- **Natural Language Interface** — "Send 50 USDC to 0x... every Friday"
- **Advanced Recurring Scheduling** — daily, weekly, monthly, business days, "first Monday", "every 2 weeks", etc.
- **Persistent Job Store** — APScheduler with SQLAlchemy (survives restarts)
- **Full Payment History** — SQLite-backed with dashboard metrics and charts
- **Real onchain execution** — USDC transfers via Web3.py
- **Cancel scheduled jobs** from sidebar or chat
- **Live metrics** — Total volume, success rate, daily volume chart
- **Demo mode** fallback for quick testing

---

## 🛠 Tech Stack

- **Frontend**: Streamlit
- **Agent**: LangGraph + LangChain + OpenRouter (free model)
- **Scheduler**: APScheduler + SQLAlchemyJobStore
- **Blockchain**: Web3.py (Arbitrum Sepolia)
- **Database**: SQLite (`jobs.sqlite` + `payguard.db`)
- **Others**: pandas, dateutil, python-dotenv

---

## 🚀 Installation & Setup

### 1. Clone / Download the project

### 2. Install dependencies

```bash
pip install -r requirements.txt
