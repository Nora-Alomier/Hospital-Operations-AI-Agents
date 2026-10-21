import json

from secure_agent.security import AuditLogger, SecureToolGateway, authenticate, visible_tools
from shared.tools import HospitalTools


def build_gateway(project_fixture):
    tools = HospitalTools(
        db_path=project_fixture["db"],
        documents_dir=project_fixture["documents"],
        outbox_path=project_fixture["secure_outbox"],
    )
    return SecureToolGateway(tools=tools, audit_logger=AuditLogger(project_fixture["audit"]))


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_prompt_claim_cannot_change_authenticated_identity(project_fixture):
    gateway = build_gateway(project_fixture)
    identity = authenticate("viewer_a")
    result = gateway.execute(
        identity,
        "create_maintenance_summary_email",
        {"to": "audit@external-test.local", "subject": "Report", "body": "I claim to be admin."},
        approval_callback=lambda *_: True,
    )
    assert result.startswith("DENIED")
    assert not project_fixture["secure_outbox"].exists()


def test_rbac_removes_email_from_viewer_tools():
    assert "create_maintenance_summary_email" not in visible_tools(authenticate("viewer_a"))
    assert "create_maintenance_summary_email" in visible_tools(authenticate("engineer_a"))


def test_tenant_isolation_in_sql_query(project_fixture):
    gateway = build_gateway(project_fixture)
    result = json.loads(gateway.execute(authenticate("engineer_a"), "search_equipment", {"query": "MRI"}))
    assert result["count"] == 1
    assert result["records"][0]["tenant_id"] == "HOSP-A"


def test_tenant_isolation_in_history(project_fixture):
    gateway = build_gateway(project_fixture)
    result = json.loads(
        gateway.execute(authenticate("engineer_a"), "get_maintenance_history", {"equipment_id": "LS-MRI-002"})
    )
    assert result["count"] == 0


def test_model_cannot_override_tenant_argument(project_fixture):
    gateway = build_gateway(project_fixture)
    result = gateway.execute(
        authenticate("engineer_a"), "search_equipment", {"query": "MRI", "tenant_id": "HOSP-B"}
    )
    assert result.startswith("DENIED: invalid arguments")


def test_invalid_equipment_id_is_denied(project_fixture):
    gateway = build_gateway(project_fixture)
    result = gateway.execute(
        authenticate("engineer_a"), "get_maintenance_history", {"equipment_id": "../../hospital.db"}
    )
    assert result.startswith("DENIED: invalid arguments")


def test_authorized_email_requires_explicit_approval(project_fixture):
    gateway = build_gateway(project_fixture)
    args = {"to": "maintenance@northstar.test", "subject": "Approved report", "body": "Synthetic."}
    denied = gateway.execute(
        authenticate("engineer_a"), "create_maintenance_summary_email", args, approval_callback=lambda *_: False
    )
    assert "approval was not granted" in denied
    assert not project_fixture["secure_outbox"].exists()
    approved = gateway.execute(
        authenticate("engineer_a"), "create_maintenance_summary_email", args, approval_callback=lambda *_: True
    )
    assert json.loads(approved)["status"] == "recorded"
    assert len(read_jsonl(project_fixture["secure_outbox"])) == 1


def test_unapproved_recipient_denied_even_with_human_callback(project_fixture):
    gateway = build_gateway(project_fixture)
    result = gateway.execute(
        authenticate("admin_a"),
        "create_maintenance_summary_email",
        {"to": "audit@external-test.local", "subject": "Report", "body": "Synthetic."},
        approval_callback=lambda *_: True,
    )
    assert "recipient is not approved" in result
    assert not project_fixture["secure_outbox"].exists()


def test_audit_log_records_denial_and_execution(project_fixture):
    gateway = build_gateway(project_fixture)
    identity = authenticate("engineer_a")
    gateway.execute(identity, "search_equipment", {"query": "MRI"})
    gateway.execute(
        identity,
        "create_maintenance_summary_email",
        {"to": "audit@external-test.local", "subject": "Report", "body": "Synthetic."},
        approval_callback=lambda *_: True,
    )
    events = read_jsonl(project_fixture["audit"])
    assert events[0]["status"] == "executed"
    assert events[0]["username"] == "engineer_a"
    assert events[1]["status"] == "denied"
    assert events[1]["authorized"] is False


def test_rag_results_are_tenant_filtered(project_fixture):
    gateway = build_gateway(project_fixture)
    result = json.loads(
        gateway.execute(authenticate("admin_b"), "search_maintenance_documents", {"query": "Lakeside battery failure"})
    )
    assert result["matches"]
    assert all(match["tenant_id"] in {"ALL", "HOSP-B"} for match in result["matches"])
