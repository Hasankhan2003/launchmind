"""
main.py - LaunchMind Multi-Agent System Entry Point

EXECUTION FLOW:
  1. Load environment variables
  2. Initialize MessageBus
  3. Initialize all agents (CEO, Product, Engineer, Marketing, QA)
  4. CEO orchestrator kicks off pipeline with the startup idea
  5. Enter the main event loop:
     - Agents process their inboxes asynchronously and react
     - The CEO coordinates dependencies and evaluates output quality
  6. Pipeline exits when CEO posts final launch announcement
  7. Print history summary and save artifacts

ARCHITECTURE:
  - 100% Message-Driven: No function chaining or hardcoded agent connections
  - Autonomous Reasoning: LLMs are used for strategic evaluation, not just generation
  - Feedback Loops: Output quality < threshold triggers auto-revisions
"""

import sys
import time
import json
import argparse
from datetime import datetime

# Prevent unicode encoding errors on Windows terminal
if sys.stdout.encoding != 'utf-8':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from dotenv import load_dotenv

# Load .env first
load_dotenv()

from message_bus import MessageBus
from agents.ceo_agent import CEOAgent
from agents.product_agent import ProductAgent
from agents.engineer_agent import EngineerAgent
from agents.marketing_agent import MarketingAgent
from agents.qa_agent import QAAgent
from config import TICK_DELAY, MAX_TICKS, HISTORY_FILE, DEFAULT_STARTUP_IDEA


def print_banner() -> None:
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║           🚀  L A U N C H M I N D  🚀                        ║
║         AI-Powered Multi-Agent Startup System                ║
║                                                              ║
║  Agents: CEO · Product · Engineer · Marketing · QA           ║
║  Architecture:  Autonomous Message Bus & Feedback Loops      ║
║  Integrations:  GitHub, Slack, SendGrid                      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def print_history_summary(bus: MessageBus) -> None:
    """Print a clean table of all agent communication."""
    history = bus.history()
    print("\n" + "="*70)
    print(f"  📋 MESSAGE HISTORY  ({len(history)} messages total)")
    print("="*70)
    print(f"  {'#':<4} {'FROM':<12} {'TO':<12} {'TYPE':<20} {'ID':<10}")
    print("-" * 70)
    
    for i, msg in enumerate(history, 1):
        mid   = msg.get("message_id", "")[:8]
        frm   = msg.get("from_agent", "?")
        to    = msg.get("to_agent",   "?")
        mtype = msg.get("message_type", "?")
        print(f"  {i:<4} {frm:<12} {to:<12} {mtype:<20} {mid:<10}")
        
    print("="*70)

    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        print(f"\n  💾 Full structured history saved to: {HISTORY_FILE}")
    except Exception as e:
        print(f"  ⚠  Could not save history to json: {e}")


def main() -> None:
    # Command-line interface to allow overriding the startup idea
    parser = argparse.ArgumentParser(description="LaunchMind Multi-Agent System")
    parser.add_argument(
        "--idea", 
        type=str, 
        default=DEFAULT_STARTUP_IDEA,
        help="The startup idea to build. Overrides the default AI Study Planner."
    )
    args = parser.parse_args()

    start_time = datetime.now()
    print_banner()
    print(f"  Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. Initialize core bus
    bus = MessageBus(persist_path=HISTORY_FILE)

    # 2. Instantiate agents
    print("[System] Initialising multi-agent workforce...")
    ceo       = CEOAgent(bus, idea=args.idea)
    product   = ProductAgent(bus)
    engineer  = EngineerAgent(bus)
    marketing = MarketingAgent(bus)
    qa        = QAAgent(bus)
    print("[System] ✅ All agents online and listening.\n")

    # 3. Boot up the system via CEO
    ceo.kickoff()

    print("\n[System] 🔄 Entering autonomous event loop...\n")
    tick = 0

    # 4. Main Event Loop
    try:
        while not ceo.is_complete and tick < MAX_TICKS:
            tick += 1
            print(f"\n[System] ── Tick {tick:03d} ─────────────────────────────")

            # Autonomous processing: Agents drain their inboxes and react
            product.process()
            engineer.process()
            marketing.process()
            qa.process()

            # CEO processes responses and makes strategic pipeline decisions
            done = ceo.process()
            if done:
                print("\n[System] 🏁 CEO has marked the project as complete.")
                break

            time.sleep(TICK_DELAY)

        if tick >= MAX_TICKS:
            print("\n[System] ⚠ Maximum ticks reached. Terminating early to prevent infinite loop.")

    except KeyboardInterrupt:
        print("\n\n[System] ⚠ Interrupted by user. Shutting down gracefully...")

    # 5. Summarise execution
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n[System] ⏱  Total execution time: {elapsed:.1f}s across {tick} ticks")
    print_history_summary(bus)
    print("\n✅ LaunchMind run complete.\n")


if __name__ == "__main__":
    main()
