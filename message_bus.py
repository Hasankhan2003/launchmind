"""
message_bus.py - Central Message Bus for LaunchMind Multi-Agent System

Implements a structured messaging layer that all agents use to communicate.
Every message follows a strict JSON schema with full history preservation.
"""

import uuid
import json
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


# ─────────────────────────────────────────────
#  Message Schema
# ─────────────────────────────────────────────
# {
#   "message_id": "uuid",
#   "from_agent": "string",
#   "to_agent":   "string",
#   "message_type": "task | result | revision_request | confirmation | complete",
#   "payload": {},
#   "timestamp": "ISO 8601",
#   "parent_message_id": "uuid | null"
# }

VALID_TYPES = {"task", "result", "revision_request", "confirmation", "complete"}


def build_message(
    from_agent: str,
    to_agent: str,
    message_type: str,
    payload: Dict[str, Any],
    parent_message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a fully-formed message dict following the LaunchMind schema."""
    if message_type not in VALID_TYPES:
        raise ValueError(f"Invalid message_type '{message_type}'. Must be one of {VALID_TYPES}")

    return {
        "message_id": str(uuid.uuid4()),
        "from_agent": from_agent,
        "to_agent": to_agent,
        "message_type": message_type,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "parent_message_id": parent_message_id,
    }


class MessageBus:
    """
    Thread-safe in-memory message bus.

    Agents call:
      - send(message)       → enqueue a message
      - fetch(agent_name)   → retrieve all unread messages for that agent
      - history()           → full ordered history of every message
    """

    def __init__(self, persist_path: Optional[str] = None):
        self._lock = threading.Lock()
        self._messages: List[Dict[str, Any]] = []       # full history
        self._inbox: Dict[str, List[Dict]] = {}         # agent → unread queue
        self._persist_path = persist_path               # optional JSON dump

        print("[MessageBus] Initialized — ready for agent communication.")

    # ──────────────────────────────
    #  Public API
    # ──────────────────────────────

    def send(self, message: Dict[str, Any]) -> str:
        """
        Publish a message to the bus.

        Returns the message_id for tracking.
        """
        with self._lock:
            self._validate(message)
            self._messages.append(message)

            agent = message["to_agent"]
            if agent not in self._inbox:
                self._inbox[agent] = []
            self._inbox[agent].append(message)

            self._maybe_persist()

        print(
            f"[MessageBus] ✉  {message['from_agent']} → {message['to_agent']} "
            f"[{message['message_type']}] id={message['message_id'][:8]}"
        )
        return message["message_id"]

    def fetch(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Drain and return all pending messages for the given agent.
        Messages are removed from the inbox after retrieval (consumed once).
        """
        with self._lock:
            msgs = self._inbox.get(agent_name, []).copy()
            self._inbox[agent_name] = []
        return msgs

    def peek(self, agent_name: str) -> List[Dict[str, Any]]:
        """Return pending messages without consuming them (for debugging)."""
        with self._lock:
            return self._inbox.get(agent_name, []).copy()

    def history(self) -> List[Dict[str, Any]]:
        """Return a copy of the full message history."""
        with self._lock:
            return self._messages.copy()

    def history_for(self, agent_name: str) -> List[Dict[str, Any]]:
        """Return all messages sent TO or FROM a specific agent."""
        with self._lock:
            return [
                m for m in self._messages
                if m["from_agent"] == agent_name or m["to_agent"] == agent_name
            ]

    def dump(self) -> str:
        """Pretty-print full history as JSON string."""
        return json.dumps(self.history(), indent=2)

    # ──────────────────────────────
    #  Internals
    # ──────────────────────────────

    def _validate(self, message: Dict[str, Any]) -> None:
        required = {"message_id", "from_agent", "to_agent", "message_type", "payload", "timestamp"}
        missing = required - message.keys()
        if missing:
            raise ValueError(f"Message missing required fields: {missing}")
        if message["message_type"] not in VALID_TYPES:
            raise ValueError(f"Invalid message_type: {message['message_type']}")

    def _maybe_persist(self) -> None:
        if self._persist_path:
            try:
                with open(self._persist_path, "w", encoding="utf-8") as f:
                    json.dump(self._messages, f, indent=2)
            except Exception as e:
                print(f"[MessageBus] Warning: could not persist to {self._persist_path}: {e}")
