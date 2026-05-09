import streamlit as st
from dotenv import load_dotenv
import os
from langgraph.graph import StateGraph, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from web3 import Web3
from pydantic import BaseModel, Field
from typing import List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
import time
from langchain_core.messages import AIMessage
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dateutil.rrule import *
import sqlite3
import re
from datetime import datetime
import pandas as pd

load_dotenv()

st.set_page_config(page_title="PayGuard • Arbitrum", page_icon="💸", layout="wide")
st.title("💸 PayGuard - Onchain Payment Agent")
st.caption("Autonomous recurring payments on Arbitrum")

w3 = Web3(Web3.HTTPProvider(os.getenv("ARBITRUM_SEPOLIA_RPC")))

YOUR_WALLET = w3.to_checksum_address("0x9faAd3d1B57C6Abe222792012662B7A128EBb5f8")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

WEEKDAY_MAP = {
    "monday": MO,
    "tuesday": TU,
    "wednesday": WE,
    "thursday": TH,
    "friday": FR,
    "saturday": SA,
    "sunday": SU,
}

llm = ChatOpenAI(
    model="openrouter/free",
    openai_api_key=os.getenv("OPENROUTER_API_KEY"),
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=0.0,
)

USDC_ADDRESS = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"

ERC20_ABI = [
    {"constant":False,"inputs":[{"name":"recipient","type":"address"},{"name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"}
]

conn = sqlite3.connect(
    "payguard.db",
    check_same_thread=False
)

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS payment_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    amount REAL,
    recipient TEXT,
    tx_hash TEXT,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# ============== SCHEDULER ==============

# if "scheduled_jobs" not in st.session_state:
#     st.session_state.scheduled_jobs = []
#
# # Make it bulletproof for tool/agent context
# if not isinstance(st.session_state.scheduled_jobs, list):
#     st.session_state.scheduled_jobs = []
# if "scheduler" not in st.session_state:
jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')
}

scheduler = BackgroundScheduler(jobstores=jobstores)

if not scheduler.running:
    scheduler.start()
st.session_state.scheduler = scheduler

scheduler = st.session_state.scheduler

def send_scheduled_payment(amount: float, recipient: str, job_id: str):
    """Background function to execute recurring payment"""
    try:
        wallet = w3.to_checksum_address(YOUR_WALLET)
        amount_wei = int(amount * 1_000_000)
        usdc = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
        tx = usdc.functions.transfer(recipient, amount_wei).build_transaction({
            'from': wallet,
            'nonce': w3.eth.get_transaction_count(wallet),
            'gas': 100000,
            'maxFeePerGas': w3.eth.gas_price * 2,
            'maxPriorityFeePerGas': w3.to_wei(0.1, 'gwei'),
            'type': 2
        })

        signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        st.toast(
            f"✅ Recurring payment sent!",
            icon="💸"
        )

        tx_hash_hex = tx_hash.hex()

        cursor.execute(
            """
            INSERT INTO payment_history
            (
                job_id,
                amount,
                recipient,
                tx_hash,
                status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                job_id,
                amount,
                recipient,
                tx_hash_hex,
                "success"
            )
        )

        conn.commit()

        print(f"""
        Recurring Payment Executed

        Amount: {amount} USDC
        Recipient: {recipient}

        Tx Hash:
        {tx_hash_hex}

        Explorer:
        https://sepolia.arbiscan.io/tx/{tx_hash_hex}
        """)
    except Exception as e:
        st.toast(f"❌ Scheduled payment failed: {str(e)[:80]}", icon="⚠️")


# ============== STRUCTURED OUTPUT MODEL ==============
class PaymentIntent(BaseModel):
    amount: float = Field(description="Payment amount per recipient")
    token: str = Field(description="Token symbol (USDC, USDT, DAI, etc.)")
    frequency: str = Field(description="Recurring frequency (e.g. every Friday, monthly, one-time)")
    recipients: List[str] = Field(description="List of recipients (names or addresses)")
    total_amount: Optional[float] = Field(description="Total if multiple recipients")
    description: Optional[str] = Field(description="Additional notes")

# ============== TOOLS ==============
@tool
def parse_payment_intent(query: str) -> str:
    """Parse natural language payment request"""
    structured_llm = llm.with_structured_output(PaymentIntent)
    try:
        result = structured_llm.invoke(query)
        return f"""
    **Parsed Payment Intent:**

    - **Amount per recipient**: {result.amount} {result.token}
    - **Frequency**: {result.frequency}
    - **Recipients**: {', '.join(result.recipients)}
    - **Total**: {result.total_amount or result.amount} {result.token}
    - **Description**: {result.description or 'None'}
            """
    except:
        return "Could not parse intent clearly. Please be more specific."

def get_next_nth_weekday(
    weekday,
    nth
):
    now = datetime.now()

    rule = rrule(
        freq=MONTHLY,
        byweekday=weekday(nth),
        dtstart=now,
        count=1
    )

    return rule[0]

def load_payment_data():

    query = """
    SELECT *
    FROM payment_history
    ORDER BY created_at DESC
    """

    return pd.read_sql_query(query, conn)

def parse_recurrence(frequency: str):

    freq = frequency.lower().strip()

    # Every X minutes
    match = re.search(r"every (\d+) minute", freq)
    if match:
        minutes = int(match.group(1))
        return IntervalTrigger(minutes=minutes), f"Every {minutes} minute(s)"

    # Every X hours
    match = re.search(r"every (\d+) hour", freq)
    if match:
        hours = int(match.group(1))
        return IntervalTrigger(hours=hours), f"Every {hours} hour(s)"

    # Every X days
    match = re.search(r"every (\d+) day", freq)
    if match:
        days = int(match.group(1))
        return IntervalTrigger(days=days), f"Every {days} day(s)"



    # Every X weeks
    match = re.search(r"every (\d+) week", freq)
    if match:
        weeks = int(match.group(1))
        return IntervalTrigger(weeks=weeks), f"Every {weeks} week(s)"

        # ----------------------------
        # Every weekday
        # ----------------------------

    if "business day" in freq or "weekday" in freq:
        return (
            CronTrigger(day_of_week="mon-fri", hour=10),
            "Every business day"
        )

    # Weekdays
    for day_name in WEEKDAY_MAP.keys():

        if f"every {day_name}" in freq:
            return (
                CronTrigger(
                    day_of_week=day_name[:3],
                    hour=10,
                    minute=0
                ),
                f"Every {day_name.capitalize()}"
            )

        # ----------------------------
        # First Monday of month
        # Second Tuesday
        # Last Friday
        # Third Wednesday
        # ----------------------------

        ordinal_map = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "last": -1
        }

        for ordinal_word, ordinal_num in ordinal_map.items():

            for day_name in WEEKDAY_MAP.keys():
                pattern = f"{ordinal_word} {day_name}"
                if pattern in freq:
                    weekday = WEEKDAY_MAP[day_name](ordinal_num)

                    return (
                        CronTrigger(
                            day="*",
                            day_of_week=day_name[:3],
                            hour=10,
                            minute=0
                        ),
                        f"{ordinal_word.capitalize()} {day_name.capitalize()} of every month"
                    )

    # Monthly
    if "monthly" in freq:
        return (
            CronTrigger(day=1, hour=10, minute=0),
            "Monthly on day 1"
        )

    # Quarterly
    if "quarterly" in freq:
        return (
            CronTrigger(month='1,4,7,10', day=1, hour=10),
            "Quarterly"
        )

        # ----------------------------
        # Yearly
        # ----------------------------

        if "yearly" in freq or "annually" in freq:
            return (
                CronTrigger(
                    month=1,
                    day=1,
                    hour=10
                ),
                "Yearly"
            )
    # Default fallback
    return (
        IntervalTrigger(minutes=1),
        "Every minute (fallback)"
    )

@tool
def execute_payment(amount: float, token: str, frequency: str, recipient: str) -> str:
    """Execute or schedule payment"""
    if not PRIVATE_KEY:
        return "❌ PRIVATE_KEY not set in .env"

    try:
        wallet = w3.to_checksum_address(YOUR_WALLET)
        amount_wei = int(amount * 1_000_000)  # USDC 6 decimals

        # Check ETH balance for gas
        eth_balance = w3.from_wei(w3.eth.get_balance(wallet), 'ether')
        if eth_balance < 0.001:
            return f"❌ Low ETH balance: {eth_balance:.4f} ETH. Need at least 0.001 ETH for gas."

        usdc = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)

        # Safe EIP-1559 gas parameters for Arbitrum Sepolia
        gas_price = w3.eth.gas_price
        max_priority_fee = w3.to_wei(0.1, 'gwei')
        max_fee = gas_price * 2

        # Transfer
        tx = usdc.functions.transfer(recipient, amount_wei).build_transaction({
            'from': wallet,
            'nonce': w3.eth.get_transaction_count(wallet),
            'gas': 100000,
            'maxFeePerGas': max_fee,
            'maxPriorityFeePerGas': max_priority_fee,
            'type': 2  # EIP-1559
        })
        signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

        tx_hash_hex = tx_hash.hex()

        cursor.execute(
            """
            INSERT INTO payment_history
            (
                job_id,
                amount,
                recipient,
                tx_hash,
                status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "one-time",
                amount,
                recipient,
                tx_hash_hex,
                "success"
            )
        )

        conn.commit()

        return f"""
    ✅ **Payment Sent Successfully!**

    **Amount**: {amount} USDC  
    **To**: {recipient}  
    **Tx Hash**: `{tx_hash.hex()[:20]}...`

    🔗 [View on Arbiscan](https://sepolia.arbiscan.io/tx/{tx_hash.hex()})
    """
    except Exception as e:
        return f"❌ Transfer failed: {str(e)[:200]}"

@tool
def schedule_recurring_payment(amount: float, recipient: str, frequency: str) -> str:
    """Schedule recurring payment using APScheduler"""
    try:
        safe_recipient = recipient[-8:] if recipient.startswith("0x") else recipient[:8]
        job_id = f"pay_{safe_recipient}_{int(time.time())}"
        job_id = f"pay_{safe_recipient}_{int(time.time())}"

        trigger, human_readable = parse_recurrence(frequency)

        scheduler.add_job(
            send_scheduled_payment,
            trigger=trigger,
            args=[amount, recipient, job_id],
            id=job_id,
            replace_existing=True
        )
        return f"""
✅ **Payment Scheduled Successfully!**

**Job ID**: `{job_id}`
**Amount**: {amount} USDC  
**To**: {recipient}
**Schedule**: {human_readable}
        """
    except Exception as e:
        return f"❌ Scheduling failed: {str(e)}"


@tool
def list_scheduled_jobs(dummy: str = "") -> str:
    """List all active scheduled jobs"""

    try:
        jobs = scheduler.get_jobs()

        if not jobs:
            return "No scheduled jobs found."

        output = "**📅 Active Scheduled Jobs:**\n\n"

        for job in jobs:
            amount = job.args[0]
            recipient = job.args[1]

            output += f"• **Job ID**: `{job.id}`\n"
            output += f"  **Amount**: {amount} USDC\n"
            output += f"  **Recipient**: {recipient}\n"
            output += f"  **Next Run**: {job.next_run_time}\n\n"

        output += f"**Total Jobs**: {len(jobs)}"

        return output

    except Exception as e:
        return f"❌ Error retrieving jobs: {str(e)}"
    # output = "**📅 Active Scheduled Jobs:**\n\n"
    # for job in st.session_state.scheduled_jobs:
    #     output += f"• **Job ID**: `{job['id']}`\n"
    #     output += f"  **Amount**: {job['amount']} USDC\n"
    #     output += f"  **To**: {job['to']}\n"
    #     output += f"  **Schedule**: {job['trigger']}\n\n"
    #
    # output += f"**Total Jobs**: {len(st.session_state.scheduled_jobs)}"
    # return output

@tool
def cancel_job(job_id: str) -> str:
    """Cancel a scheduled job"""
    try:
        scheduler.remove_job(job_id)
        return f"✅ Job `{job_id}` cancelled successfully."
    except Exception as e:
        return f"❌ Could not cancel job: {str(e)}"

tools = [parse_payment_intent, execute_payment, schedule_recurring_payment, list_scheduled_jobs, cancel_job]
tool_node = ToolNode(tools)
llm_with_tools = llm.bind_tools(
    tools,
    tool_choice="auto"
)


def agent_node(state: MessagesState):
    system_prompt = """
You are PayGuard, an autonomous payment agent.

CRITICAL RULES:
- If the user asks to view, show, check, list, inspect, or see scheduled jobs/payments,
  you MUST call the tool `list_scheduled_jobs`.

- If the user wants to **schedule**, **recurring**, **every**, **weekly**, **monthly**, **daily**, or similar ongoing payment → **MUST** call `schedule_recurring_payment`.

- If the user asks to schedule or create a recurring payment,
  you MUST call `schedule_recurring_payment`.

- If the user asks to send a one-time payment,
  you MUST call `execute_payment`.

- If the user asks to list or show jobs,
  call list_scheduled_jobs with an empty string.
  
- Never guess or fabricate scheduled jobs.
- Never answer from memory.
- Always use tools for payment or scheduling operations.
- After a tool returns results, summarize them naturally.
"""
    for attempt in range(3):  # Retry up to 3 times
        try:
            response = llm_with_tools.invoke([("system", system_prompt)] + state["messages"])
            return {
                "messages": state["messages"] + [response]
            }
        except Exception as e:
            if attempt == 2:  # Last attempt
                return {
            "messages": state["messages"] + [
                AIMessage(content=f"Error: {str(e)}")
            ]
        }
            time.sleep(2)

# Graph
graph = StateGraph(MessagesState)
graph.add_node("agent", agent_node)
graph.add_node("tools", tool_node)
graph.set_entry_point("agent")
graph.add_conditional_edges(
    "agent",
    tools_condition,
    {
        "tools": "tools",
        END: END,
    }
)

graph.add_edge("tools", "agent")
agent = graph.compile()

# ============== SIDEBAR ==============
with st.sidebar:
    st.header("💰 Wallet")
    st.code(YOUR_WALLET)
    st.caption("📅 Scheduled Jobs")
    jobs = scheduler.get_jobs()

    if jobs:
        for job in jobs:
            try:
                amount = job.args[0]
                recipient = job.args[1]

            except:
                amount = "Unknown"
                recipient = "Unknown"

            st.write(f"• **{amount} USDC** → {recipient}")
            if job.next_run_time:
                st.caption(f"Next Run: {job.next_run_time}")
            if st.button("Cancel", key=job.id):
                try:
                    scheduler.remove_job(job.id)
                    st.success(f"Cancelled {job.id}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not cancel job: {str(e)}")
    else:
        st.info("No active jobs yet.")

    df = load_payment_data()

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "Total Payments",
        f"{len(df)}"
    )

with col2:

    total_volume = (
        df["amount"].sum()
        if not df.empty
        else 0
    )

    st.metric(
        "Total USDC Sent",
        f"{total_volume:.2f}"
    )

with col3:

    success_count = (
        len(df[df["status"] == "success"])
        if not df.empty
        else 0
    )

    st.metric(
        "Successful Payments",
        success_count
    )

if not df.empty:

    df["created_at"] = pd.to_datetime(df["created_at"])

    daily = (
        df.groupby(
            df["created_at"].dt.date
        )["amount"]
        .sum()
        .reset_index()
    )

    st.subheader("📈 Daily Payment Volume")

    st.line_chart(
        daily,
        x="created_at",
        y="amount"
    )

st.subheader("💸 Recent Transactions")
if not df.empty:

    st.dataframe(
        df[
            [
                "created_at",
                "amount",
                "recipient",
                "tx_hash",
                "status"
            ]
        ],
        use_container_width=True
    )

st.subheader("📅 Upcoming Scheduled Payments")
jobs = scheduler.get_jobs()

for job in jobs:

    amount = job.args[0]
    recipient = job.args[1]

    st.info(
        f"""
        {amount} USDC
        → {recipient}

        Next Run:
        {job.next_run_time}
        """
    )

# ============== CHAT ==============
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I'm PayGuard. Try: 'Pay my team $500 USDC every Friday'"}]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Describe a payment..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Processing payment intent..."):
            result = agent.invoke({"messages": st.session_state.messages})
            final_message = result["messages"][-1]

            response = getattr(final_message, "content", str(final_message))

            if not response:
                response = str(final_message)

            st.success("Payment executed successfully")
            st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
