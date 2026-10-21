"""Compatibility helpers for local models that print tool calls as JSON text.

Native LangChain ``AIMessage.tool_calls`` remains the preferred path.  These
helpers recover only a narrowly defined, complete JSON object and never execute
anything themselves.  The selected agent dispatcher still owns execution and,
for the secure agent, authorization.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


EMAIL_TOOL = "create_maintenance_summary_email"
TOOL_ALIASES = {
    "send_email": EMAIL_TOOL,
    EMAIL_TOOL: EMAIL_TOOL,
}
EMAIL_ADDRESS_RE = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+", re.IGNORECASE)
EMAIL_ACTION_RE = re.compile(r"\b(?:send|email|e-mail|record|create)\b", re.IGNORECASE)
FENCED_JSON_RE = re.compile(r"^```(?:json)?\s*(\{.*\})\s*```$", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class RecoveredToolCall:
    name: str
    arguments: dict[str, Any]
    source: str


def normalize_tool_name(name: object) -> str:
    """Map the common instructor/Ollama email alias to the real tool name."""
    if not isinstance(name, str):
        return ""
    cleaned = name.strip()
    return TOOL_ALIASES.get(cleaned, cleaned)


def message_content_text(content: object) -> str:
    """Return text from the string or block-list formats used by chat models."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        pieces: list[str] = []
        for block in content:
            if isinstance(block, str):
                pieces.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                pieces.append(block["text"])
        return "\n".join(pieces).strip()
    return ""


def recover_text_tool_call(content: object) -> RecoveredToolCall | None:
    """Parse one complete JSON tool proposal from model output.

    Arbitrary prose containing JSON is deliberately rejected.  Accepted shapes:
    ``{"name": ..., "parameters": {...}}``, ``arguments`` instead of
    ``parameters``, or Ollama's nested ``{"function": ...}`` shape.
    """
    text = message_content_text(content)
    if not text:
        return None
    fenced = FENCED_JSON_RE.fullmatch(text)
    candidate = fenced.group(1) if fenced else text
    try:
        payload = json.loads(candidate)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if set(payload) == {"function"} and isinstance(payload["function"], dict):
        payload = payload["function"]
    if set(payload) == {"name", "parameters"}:
        arguments = payload["parameters"]
    elif set(payload) == {"name", "arguments"}:
        arguments = payload["arguments"]
    else:
        return None
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    if not isinstance(arguments, dict):
        return None
    name = normalize_tool_name(payload.get("name"))
    if not name:
        return None
    return RecoveredToolCall(name=name, arguments=arguments, source="model_text_json")


def recover_email_intent(user_message: str) -> RecoveredToolCall | None:
    """Build a conservative email proposal when a local model omits tool syntax.

    The user must explicitly request an email-like action and include a recipient.
    Defaults are displayed for approval if the recipient is otherwise authorized.
    """
    if not EMAIL_ACTION_RE.search(user_message):
        return None
    recipient_match = EMAIL_ADDRESS_RE.search(user_message)
    if not recipient_match:
        return None
    subject_match = re.search(
        r"\bsubject\s*(?::|is)?\s*(.+?)(?=\s+(?:and\s+)?body\s*(?::|is)?\s*|$)",
        user_message,
        re.IGNORECASE | re.DOTALL,
    )
    body_match = re.search(r"\bbody\s*(?::|is)?\s*(.+)$", user_message, re.IGNORECASE | re.DOTALL)
    subject = subject_match.group(1).strip(" .,\n") if subject_match else "Maintenance email request"
    body = body_match.group(1).strip() if body_match else user_message.strip()
    return RecoveredToolCall(
        name=EMAIL_TOOL,
        arguments={
            "to": recipient_match.group(0),
            "subject": subject[:120],
            "body": body[:2000],
        },
        source="user_email_intent_fallback",
    )


def format_verified_email_result(result: str) -> str:
    """Describe only the backend result, without asking the LLM to reinterpret it."""
    if result.startswith("DENIED:"):
        return f"{result}\nNo simulated email record was created."
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return f"NOT EXECUTED: backend email result was not verifiable: {result}"
    if payload.get("status") == "recorded" and isinstance(payload.get("to"), str):
        return (
            f"SIMULATED EMAIL RECORDED: a local record was created for {payload['to']}. "
            "No real email was sent."
        )
    return "NOT EXECUTED: the backend did not confirm a simulated email record."
