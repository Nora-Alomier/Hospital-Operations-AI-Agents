"""Plain hospital agent with a deliberate missing-authorization weakness.

All data is synthetic. Email actions write only to a local JSONL file.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_ollama import ChatOllama

from shared.config import MAX_AGENT_STEPS, OLLAMA_MODEL, PLAIN_OUTBOX_PATH
from shared.tool_calling import (
    EMAIL_TOOL,
    format_verified_email_result,
    normalize_tool_name,
    recover_email_intent,
    recover_text_tool_call,
)
from shared.tools import HospitalTools

SYSTEM_PROMPT = """You are a hospital equipment operations assistant using synthetic data only.
Use tools for equipment records, maintenance history, document guidance, and simulated email.
When document search is used, cite each returned source exactly as supplied.
Never claim that a simulated email was delivered: it is only a local record.
For every requested action, issue a native tool call. Do not print a tool name or JSON as ordinary text.
"""


class PlainHospitalAgent:
    """LangChain/Ollama agent whose dispatch deliberately has no authorization."""

    def __init__(
        self,
        *,
        tools: HospitalTools | None = None,
        model_name: str = OLLAMA_MODEL,
        model: Any | None = None,
    ) -> None:
        self.tools = tools or HospitalTools(outbox_path=PLAIN_OUTBOX_PATH)
        self.model_name = model_name
        self.model = model
        self._dispatch = {
            "search_equipment": self.tools.search_equipment,
            "get_maintenance_history": self.tools.get_maintenance_history,
            "search_maintenance_documents": self.tools.search_maintenance_documents,
            "create_maintenance_summary_email": self.tools.create_maintenance_summary_email,
        }
        self.langchain_tools = self._build_langchain_tools()

    def _build_langchain_tools(self) -> list[StructuredTool]:
        return [
            StructuredTool.from_function(
                func=self.tools.search_equipment,
                name="search_equipment",
                description="Search the synthetic SQLite equipment records. tenant_id is optional.",
            ),
            StructuredTool.from_function(
                func=self.tools.get_maintenance_history,
                name="get_maintenance_history",
                description="Get SQLite maintenance history for an equipment_id. tenant_id is optional.",
            ),
            StructuredTool.from_function(
                func=self.tools.search_maintenance_documents,
                name="search_maintenance_documents",
                description="Retrieve maintenance document chunks and citations. tenant_id is optional.",
            ),
            StructuredTool.from_function(
                func=self.tools.create_maintenance_summary_email,
                name="create_maintenance_summary_email",
                description="Record a simulated maintenance-summary email locally; no real delivery occurs.",
            ),
        ]

    def dispatch_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """VULNERABLE: executes any advertised operation without identity or RBAC."""
        try:
            function = self._dispatch[name]
            return str(function(**arguments))
        except (KeyError, TypeError, ValueError) as error:
            return f"Tool execution failed: {type(error).__name__}: {error}"

    def run(self, user_message: str) -> str:
        base_model = self.model or ChatOllama(model=self.model_name, temperature=0)
        model = base_model.bind_tools(self.langchain_tools)
        messages: list[Any] = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_message)]
        for step in range(1, MAX_AGENT_STEPS + 1):
            reply = model.invoke(messages)
            messages.append(reply)
            calls = [
                (normalize_tool_name(call["name"]), call["args"], call.get("id"), "native")
                for call in reply.tool_calls
            ]
            if not calls:
                recovered = recover_text_tool_call(reply.content) or recover_email_intent(user_message)
                if recovered:
                    calls = [(recovered.name, recovered.arguments, None, recovered.source)]
            if not calls:
                return str(reply.content)
            for name, arguments, call_id, source in calls:
                print(f"  [plain tool request] step={step} source={source} {name}({arguments})")
                result = self.dispatch_tool(name, arguments)
                print(f"  [plain tool result] {result[:240]}")
                if name == EMAIL_TOOL:
                    return format_verified_email_result(result)
                if call_id is None:
                    return result
                messages.append(ToolMessage(content=result, tool_call_id=call_id))
        return "Stopped: model exceeded the tool-step limit."


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the intentionally vulnerable hospital agent.")
    parser.add_argument("--model", default=OLLAMA_MODEL)
    args = parser.parse_args()
    agent = PlainHospitalAgent(model_name=args.model)
    print("\nPlain Hospital Agent (intentionally vulnerable)")
    print("Synthetic data only. Simulated email evidence:", PLAIN_OUTBOX_PATH)
    print("Commands: quit\n")
    while True:
        try:
            prompt = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if prompt.casefold() in {"quit", "exit"}:
            break
        if not prompt:
            continue
        try:
            print("Agent:", agent.run(prompt), "\n")
        except Exception as error:  # Keep the teaching CLI usable if Ollama is stopped.
            print(f"[local integration error] {type(error).__name__}: {error}\n")


if __name__ == "__main__":
    main()
