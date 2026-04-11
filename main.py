"""
main.py - LaunchMind Multi-Agent System Entry Point

EXECUTION FLOW:
  1. Load environment variables
  2. Initialize MessageBus
  3. Initialize all agents (CEO, Product, Engineer, Marketing, QA)
  4. CEO kicks off the pipeline with the startup idea
  5. Run the main event loop:
     - Each agent processes its pending messages
     - Loop continues until CEO marks the project complete
  6. Print final message history summary

ARCHITECTURE:
  - CEO orchestrates via message bus (not direct calls)
  - Agents are autonomous classes that consume and produce messages
  - Feedback loops are handled by CEO's quality evaluation
  - All real API calls happen inside the respective agents/utils
"""

import sys
import time
import json
from datetime import datetime

from dotenv import load_dotenv

# ─────────────────────────────────────────────
#  Load .env before anything else
# ─────────────────────────────────────────────
load_dotenv()

from message_bus import MessageBus
from agents.ceo_agent       import CEOAgent
from agents.product_agent   import ProductAgent
from agents.engineer_agent  import EngineerAgent
from agents.marketing_agent import MarketingAgent
from agents.qa_agent        import QAAgent


# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────
TICK_DELAY     = 1.5   # seconds between processing ticks
MAX_TICKS      = 120   # safety cap (~3 min at 1.5s/tick)
HISTORY_FILE   = "message_history.json"


def print_banner() -> None:
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║           🚀  L A U N C H M I N D  🚀                        ║
║         AI-Powered Multi-Agent Startup System                ║
║                                                              ║
║  Agents: CEO · Product · Engineer · Marketing · QA           ║
║  LLM:    Groq (llama-3.3-70b-versatile)                      ║
║  APIs:   GitHub · Slack · SendGrid                           ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def print_history_summary(bus: MessageBus) -> None:
    """Print a table of all messages exchanged during the run."""
    history = bus.history()
    print("\n" + "="*70)
    print(f"  📋 MESSAGE HISTORY  ({len(history)} messages total)")
    print("="*70)
    print(f"  {'#':<4} {'FROM':<12} {'TO':<12} {'TYPE':<20} {'ID':<10}")
    print("-"*70)
    for i, msg in enumerate(history, 1):
        mid   = msg.get("message_id", "")[:8]
        frm   = msg.get("from_agent", "?")
        to    = msg.get("to_agent",   "?")
        mtype = msg.get("message_type", "?")
        print(f"  {i:<4} {frm:<12} {to:<12} {mtype:<20} {mid:<10}")
    print("="*70)

    # Dump full history to JSON file for inspection
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        print(f"\n  Full history saved to: {HISTORY_FILE}")
    except Exception as e:
        print(f"  ⚠️  Could not save history: {e}")


def main() -> None:
    start_time = datetime.now()
    print_banner()
    print(f"  Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ── Initialize message bus ──
    bus = MessageBus(persist_path=HISTORY_FILE)

    # ── Initialize agents ──
    print("[Main] Initializing agents...")
    ceo       = CEOAgent(bus)
    product   = ProductAgent(bus)
    engineer  = EngineerAgent(bus)
    marketing = MarketingAgent(bus)
    qa        = QAAgent(bus)
    print("[Main] ✅ All agents initialized.\n")

    # ── Kick off the pipeline ──
    ceo.kickoff()

    # ── Main event loop ──
    print("\n[Main] 🔄 Starting main event loop...\n")
    tick = 0

    try:
        while not ceo.is_complete and tick < MAX_TICKS:
            tick += 1
            print(f"[Main] ── Tick {tick:03d} ──────────────────────────────")

            # Each agent processes its inbox (autonomous, non-blocking)
            product.process()
            engineer.process()
            marketing.process()
            qa.process()

            # CEO processes responses and orchestrates
            done = ceo.process()
            if done:
                print("\n[Main] 🏁 CEO marked project as complete.")
                break

            time.sleep(TICK_DELAY)

    except KeyboardInterrupt:
        print("\n\n[Main] ⚠️  Interrupted by user. Printing partial results...")

    # ── Final report ──
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n[Main] ⏱  Total execution time: {elapsed:.1f}s across {tick} ticks")
    print_history_summary(bus)
    print("\n✅ LaunchMind run complete.\n")


if __name__ == "__main__":
    main()
