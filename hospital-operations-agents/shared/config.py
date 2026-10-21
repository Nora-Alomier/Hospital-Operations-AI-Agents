"""Project paths and non-secret demo configuration."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "shared" / "hospital.db"
DOCUMENTS_DIR = PROJECT_ROOT / "shared" / "documents"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
PLAIN_OUTBOX_PATH = RUNTIME_DIR / "plain_sent_emails.jsonl"
SECURE_OUTBOX_PATH = RUNTIME_DIR / "secure_sent_emails.jsonl"
AUDIT_LOG_PATH = RUNTIME_DIR / "secure_audit.jsonl"

OLLAMA_MODEL = "llama3.2:latest"
MAX_AGENT_STEPS = 6
