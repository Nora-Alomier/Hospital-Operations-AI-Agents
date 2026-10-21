"""Application-owned authentication, authorization, validation, and auditing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from shared.config import AUDIT_LOG_PATH, SECURE_OUTBOX_PATH
from shared.tools import HospitalTools


@dataclass(frozen=True)
class Identity:
    username: str
    display_name: str
    role: str
    tenant_id: str


# The CLI selects one of these application-owned identities. Chat text cannot alter it.
USERS = {
    "admin_a": Identity("admin_a", "Amina Admin", "Administrator", "HOSP-A"),
    "engineer_a": Identity("engineer_a", "Elias Engineer", "Maintenance Engineer", "HOSP-A"),
    "viewer_a": Identity("viewer_a", "Vera Viewer", "Viewer", "HOSP-A"),
    "admin_b": Identity("admin_b", "Bilal Admin", "Administrator", "HOSP-B"),
    "viewer_b": Identity("viewer_b", "Victor Viewer", "Viewer", "HOSP-B"),
}

READ_TOOLS = {"search_equipment", "get_maintenance_history", "search_maintenance_documents"}
EMAIL_TOOL = "create_maintenance_summary_email"
ROLE_PERMISSIONS = {
    "Administrator": READ_TOOLS | {EMAIL_TOOL},
    "Maintenance Engineer": READ_TOOLS | {EMAIL_TOOL},
    "Viewer": READ_TOOLS,
}
APPROVED_RECIPIENTS = {
    "HOSP-A": {"maintenance@northstar.test", "audit@northstar.test"},
    "HOSP-B": {"maintenance@lakeside.test", "audit@lakeside.test"},
}

EQUIPMENT_ID_RE = re.compile(r"^[A-Z]{2}-[A-Z]+-[0-9]{3}$")
EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+$")


def authenticate(username: str) -> Identity:
    """Return a backend identity, never an identity claimed in a prompt."""
    try:
        return USERS[username]
    except KeyError as error:
        raise ValueError(f"Unknown demo user: {username}") from error


def visible_tools(identity: Identity) -> set[str]:
    return set(ROLE_PERMISSIONS[identity.role])


def _validate_text(value: object, field: str, *, minimum: int = 1, maximum: int = 200) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = value.strip()
    if not minimum <= len(cleaned) <= maximum:
        raise ValueError(f"{field} must contain {minimum}-{maximum} characters")
    return cleaned


def validate_arguments(tool_name: str, arguments: object) -> dict[str, str]:
    """Strict allowlist schemas; model-supplied tenant/user fields are rejected."""
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    if tool_name in {"search_equipment", "search_maintenance_documents"}:
        if set(arguments) != {"query"}:
            raise ValueError("arguments must contain exactly: query")
        return {"query": _validate_text(arguments["query"], "query")}
    if tool_name == "get_maintenance_history":
        if set(arguments) != {"equipment_id"}:
            raise ValueError("arguments must contain exactly: equipment_id")
        equipment_id = _validate_text(arguments["equipment_id"], "equipment_id", maximum=24).upper()
        if not EQUIPMENT_ID_RE.fullmatch(equipment_id):
            raise ValueError("equipment_id has an invalid format")
        return {"equipment_id": equipment_id}
    if tool_name == EMAIL_TOOL:
        if set(arguments) != {"to", "subject", "body"}:
            raise ValueError("arguments must contain exactly: to, subject, body")
        recipient = _validate_text(arguments["to"], "to", maximum=120).casefold()
        subject = _validate_text(arguments["subject"], "subject", maximum=120)
        body = _validate_text(arguments["body"], "body", maximum=2000)
        if not EMAIL_RE.fullmatch(recipient):
            raise ValueError("recipient address has an invalid format")
        if "\n" in subject or "\r" in subject:
            raise ValueError("subject must not contain line breaks")
        return {"to": recipient, "subject": subject, "body": body}
    raise ValueError("unknown tool")


class AuditLogger:
    def __init__(self, path: Path | str = AUDIT_LOG_PATH) -> None:
        self.path = Path(path)

    def write(
        self,
        *,
        identity: Identity,
        tool: str,
        authorized: bool,
        approval: str,
        status: str,
        result: str,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "username": identity.username,
            "role": identity.role,
            "tenant_id": identity.tenant_id,
            "tool": tool,
            "authorized": authorized,
            "approval": approval,
            "status": status,
            "result": result[:300],
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


ApprovalCallback = Callable[[str, dict[str, str]], bool]


class SecureToolGateway:
    """The only route from model-proposed calls to backend side effects."""

    def __init__(
        self,
        *,
        tools: HospitalTools | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.tools = tools or HospitalTools(outbox_path=SECURE_OUTBOX_PATH)
        self.audit = audit_logger or AuditLogger()

    def execute(
        self,
        identity: Identity,
        tool_name: str,
        arguments: object,
        *,
        approval_callback: ApprovalCallback | None = None,
    ) -> str:
        if tool_name not in ROLE_PERMISSIONS.get(identity.role, set()):
            result = "DENIED: role is not permitted to use this tool"
            self.audit.write(identity=identity, tool=tool_name, authorized=False, approval="not_requested", status="denied", result=result)
            return result
        try:
            clean = validate_arguments(tool_name, arguments)
        except ValueError as error:
            result = f"DENIED: invalid arguments: {error}"
            self.audit.write(identity=identity, tool=tool_name, authorized=False, approval="not_requested", status="denied", result=result)
            return result

        if tool_name == EMAIL_TOOL:
            if clean["to"] not in APPROVED_RECIPIENTS.get(identity.tenant_id, set()):
                result = "DENIED: recipient is not approved for the authenticated hospital"
                self.audit.write(identity=identity, tool=tool_name, authorized=False, approval="not_requested", status="denied", result=result)
                return result
            approved = bool(approval_callback and approval_callback(tool_name, clean))
            if not approved:
                result = "DENIED: explicit human approval was not granted"
                self.audit.write(identity=identity, tool=tool_name, authorized=True, approval="denied", status="denied", result=result)
                return result
            result = self.tools.create_maintenance_summary_email(
                **clean, tenant_id=identity.tenant_id, requested_by=identity.username
            )
            self.audit.write(identity=identity, tool=tool_name, authorized=True, approval="approved", status="executed", result=result)
            return result

        if tool_name == "search_equipment":
            result = self.tools.search_equipment(**clean, tenant_id=identity.tenant_id)
        elif tool_name == "get_maintenance_history":
            result = self.tools.get_maintenance_history(**clean, tenant_id=identity.tenant_id)
        else:
            result = self.tools.search_maintenance_documents(**clean, tenant_id=identity.tenant_id)
        self.audit.write(identity=identity, tool=tool_name, authorized=True, approval="not_required", status="executed", result=result)
        return result
