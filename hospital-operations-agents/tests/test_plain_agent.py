import json

from plain_agent.agent import PlainHospitalAgent


def test_simulated_email_tool_writes_local_record(hospital_tools, project_fixture):
    result = hospital_tools.create_maintenance_summary_email(
        "training@example.test", "Synthetic test", "No real delivery."
    )
    assert json.loads(result)["status"] == "recorded"
    record = json.loads(project_fixture["plain_outbox"].read_text(encoding="utf-8"))
    assert record["delivery"] == "SIMULATED_LOCAL_RECORD_ONLY"


def test_plain_agent_allows_unauthorized_external_email(hospital_tools, project_fixture):
    agent = PlainHospitalAgent(tools=hospital_tools)
    result = agent.dispatch_tool(
        "create_maintenance_summary_email",
        {
            "to": "audit@external-test.local",
            "subject": "Equipment maintenance report",
            "body": "Synthetic report.",
        },
    )
    assert json.loads(result)["status"] == "recorded"
    record = json.loads(project_fixture["plain_outbox"].read_text(encoding="utf-8"))
    assert record["to"] == "audit@external-test.local"
