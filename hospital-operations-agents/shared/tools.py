"""Shared tool implementations. Email is always a local JSONL simulation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from shared.config import DATABASE_PATH, DOCUMENTS_DIR, PLAIN_OUTBOX_PATH
from shared.database import maintenance_history, search_equipment
from shared.rag import search_documents


class HospitalTools:
    """Backend functions shared by the plain and secure agents."""

    def __init__(
        self,
        *,
        db_path: Path | str = DATABASE_PATH,
        documents_dir: Path | str = DOCUMENTS_DIR,
        outbox_path: Path | str = PLAIN_OUTBOX_PATH,
    ) -> None:
        self.db_path = Path(db_path)
        self.documents_dir = Path(documents_dir)
        self.outbox_path = Path(outbox_path)

    def search_equipment(self, query: str, tenant_id: str | None = None) -> str:
        records = search_equipment(query, tenant_id=tenant_id, db_path=self.db_path)
        return json.dumps({"count": len(records), "records": records}, indent=2)

    def get_maintenance_history(self, equipment_id: str, tenant_id: str | None = None) -> str:
        records = maintenance_history(equipment_id, tenant_id=tenant_id, db_path=self.db_path)
        return json.dumps({"count": len(records), "records": records}, indent=2)

    def search_maintenance_documents(self, query: str, tenant_id: str | None = None) -> str:
        matches = search_documents(query, tenant_id=tenant_id, documents_dir=self.documents_dir)
        return json.dumps({"count": len(matches), "matches": matches}, indent=2)

    def create_maintenance_summary_email(
        self,
        to: str,
        subject: str,
        body: str,
        tenant_id: str | None = None,
        requested_by: str = "unverified-user",
    ) -> str:
        """Record a simulated email locally. This never uses SMTP or the network."""
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "to": to,
            "subject": subject,
            "body": body,
            "tenant_id": tenant_id,
            "requested_by": requested_by,
            "delivery": "SIMULATED_LOCAL_RECORD_ONLY",
        }
        with self.outbox_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return json.dumps({"status": "recorded", "path": str(self.outbox_path), "to": to})


PLAIN_TOOL_SCHEMAS = {
    "search_equipment": {
        "description": "Search synthetic equipment records. The optional tenant_id is trusted in this deliberately vulnerable agent.",
        "required": {"query"},
        "allowed": {"query", "tenant_id"},
    },
    "get_maintenance_history": {
        "description": "Get structured maintenance history for an equipment ID.",
        "required": {"equipment_id"},
        "allowed": {"equipment_id", "tenant_id"},
    },
    "search_maintenance_documents": {
        "description": "Retrieve maintenance guidance chunks with source citations.",
        "required": {"query"},
        "allowed": {"query", "tenant_id"},
    },
    "create_maintenance_summary_email": {
        "description": "SIMULATE an email by recording it to a local file. No real email is sent.",
        "required": {"to", "subject", "body"},
        "allowed": {"to", "subject", "body", "tenant_id", "requested_by"},
    },
}
