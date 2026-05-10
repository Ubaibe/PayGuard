# 💸 PayGuard - Onchain Autonomous Payment Agent

**PayGuard** is an AI agent that lets you send **one-time** and **recurring** USDC payments on Arbitrum Sepolia using natural language.

Built with LangGraph + APScheduler + SQLite for persistence.

---

## ✨ Features

- **Natural Language Interface** - Send 50 USDC to 0x.../ENS every Friday
- **Advanced Recurring Scheduling** - daily, weekly, monthly, business days, first Monday, every 2 weeks, etc.
- **Persistent Job Store** - APScheduler with SQLAlchemy
- **Full Payment History** - SQLite-backed with dashboard metrics and charts
- **Real onchain execution** - USDC transfers via Web3.py
- **Cancel scheduled jobs** - from sidebar or chat
- **Live metrics** - Total volume, success rate, daily volume chart
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

##  How to Use
Chat with PayGuard on payments you would like to schedule
**Example**
- Pay my team 100 USDC every Friday
- Schedule 10 USDC to 0xabc... every 2 weeks
- Show me my payment history
- List all scheduled jobs
- Cancel pay_abc12345...

## Sidebar
- Wallet address
- Active scheduled jobs with Cancel buttons
- Recent transactions

---

##  Future Improvements: Multi-token support **(USDT, DAI, etc.)**
- User confirmation step before sending real payments
- Email/SMS notifications on payment execution
- Deploy as public web app with user accounts

