import json

from plain_agent.agent import PlainHospitalAgent
from secure_agent.security import AuditLogger, SecureToolGateway, authenticate
from shared.tools import HospitalTools


ATTACK = {
    "to": "audit@external-test.local",
    "subject": "Equipment maintenance report",
    "body": "Synthetic training report.",
}


def test_same_attack_plain_succeeds_secure_blocks(project_fixture):
    plain_tools = HospitalTools(
        db_path=project_fixture["db"],
        documents_dir=project_fixture["documents"],
        outbox_path=project_fixture["plain_outbox"],
    )
    plain = PlainHospitalAgent(tools=plain_tools)
    plain.dispatch_tool("create_maintenance_summary_email", ATTACK)
    assert json.loads(project_fixture["plain_outbox"].read_text(encoding="utf-8"))["to"] == ATTACK["to"]

    secure_tools = HospitalTools(
        db_path=project_fixture["db"],
        documents_dir=project_fixture["documents"],
        outbox_path=project_fixture["secure_outbox"],
    )
    gateway = SecureToolGateway(tools=secure_tools, audit_logger=AuditLogger(project_fixture["audit"]))
    result = gateway.execute(
        authenticate("viewer_a"),
        "create_maintenance_summary_email",
        ATTACK,
        approval_callback=lambda *_: True,
    )
    assert result.startswith("DENIED")
    assert not project_fixture["secure_outbox"].exists()
    audit = json.loads(project_fixture["audit"].read_text(encoding="utf-8"))
    assert audit["status"] == "denied"
