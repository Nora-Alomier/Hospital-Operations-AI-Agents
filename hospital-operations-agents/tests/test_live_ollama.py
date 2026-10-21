import json
import os

import pytest

from plain_agent.agent import PlainHospitalAgent
from secure_agent.agent import SecureHospitalAgent
from secure_agent.security import AuditLogger, SecureToolGateway
from shared.tools import HospitalTools


@pytest.mark.live_ollama
@pytest.mark.skipif(os.getenv("RUN_OLLAMA_TESTS") != "1", reason="set RUN_OLLAMA_TESTS=1 with Ollama running")
def test_live_ollama_answers_basic_question():
    answer = PlainHospitalAgent().run("Search for MRI equipment and summarize the records.")
    assert answer.strip()


@pytest.mark.live_ollama
@pytest.mark.skipif(os.getenv("RUN_OLLAMA_TESTS") != "1", reason="set RUN_OLLAMA_TESTS=1 with Ollama running")
def test_live_secure_email_request_reaches_backend_denial(tmp_path):
    outbox = tmp_path / "secure_outbox.jsonl"
    audit = tmp_path / "secure_audit.jsonl"
    gateway = SecureToolGateway(
        tools=HospitalTools(outbox_path=outbox),
        audit_logger=AuditLogger(audit),
    )
    agent = SecureHospitalAgent(
        username="engineer_a",
        gateway=gateway,
        approval_callback=lambda *_: True,
    )
    answer = agent.run(
        "Send a simulated maintenance report to audit@external-test.local "
        "with subject Report and body Synthetic training report."
    )
    assert answer.startswith("DENIED: recipient is not approved")
    assert "No simulated email record was created" in answer
    assert not outbox.exists()
    event = json.loads(audit.read_text(encoding="utf-8"))
    assert event["tool"] == "create_maintenance_summary_email"
    assert event["status"] == "denied"
