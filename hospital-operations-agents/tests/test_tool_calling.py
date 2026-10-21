import json

from langchain_core.messages import AIMessage

from secure_agent.agent import SecureHospitalAgent
from secure_agent.security import AuditLogger, SecureToolGateway
from shared.tool_calling import EMAIL_TOOL, recover_email_intent, recover_text_tool_call
from shared.tools import HospitalTools


class StaticModel:
    """Minimal chat model double for testing the agent orchestration loop."""

    def __init__(self, reply: AIMessage):
        self.reply = reply

    def bind_tools(self, _tools):
        return self

    def invoke(self, _messages):
        return self.reply


def secure_agent_with_reply(project_fixture, reply, *, approved=True):
    tools = HospitalTools(
        db_path=project_fixture["db"],
        documents_dir=project_fixture["documents"],
        outbox_path=project_fixture["secure_outbox"],
    )
    gateway = SecureToolGateway(tools=tools, audit_logger=AuditLogger(project_fixture["audit"]))
    return SecureHospitalAgent(
        username="engineer_a",
        gateway=gateway,
        approval_callback=lambda *_: approved,
        model=StaticModel(reply),
    )


def test_recovers_llama_text_json_and_routes_it_through_secure_gateway(project_fixture):
    reply = AIMessage(
        content=json.dumps(
            {
                "name": "send_email",
                "parameters": {
                    "to": "audit@external-test.local",
                    "subject": "Report",
                    "body": "Synthetic training report.",
                },
            }
        )
    )
    agent = secure_agent_with_reply(project_fixture, reply)
    result = agent.run("Send a simulated report to audit@external-test.local.")
    assert result.startswith("DENIED: recipient is not approved")
    assert "No simulated email record was created" in result
    assert not project_fixture["secure_outbox"].exists()
    audit = json.loads(project_fixture["audit"].read_text(encoding="utf-8"))
    assert audit["tool"] == EMAIL_TOOL
    assert audit["status"] == "denied"


def test_email_intent_fallback_produces_backend_denial_not_model_claim(project_fixture):
    agent = secure_agent_with_reply(project_fixture, AIMessage(content="The email was sent successfully."))
    result = agent.run("Email the maintenance report to audit@external-test.local.")
    assert result.startswith("DENIED: recipient is not approved")
    assert "sent successfully" not in result
    assert not project_fixture["secure_outbox"].exists()
    assert json.loads(project_fixture["audit"].read_text(encoding="utf-8"))["status"] == "denied"


def test_authorized_text_json_still_requires_human_approval(project_fixture):
    reply = AIMessage(
        content='''{"name":"send_email","parameters":{"to":"maintenance@northstar.test","subject":"Report","body":"Synthetic."}}'''
    )
    agent = secure_agent_with_reply(project_fixture, reply, approved=False)
    result = agent.run("Send the maintenance email.")
    assert result.startswith("DENIED: explicit human approval was not granted")
    assert not project_fixture["secure_outbox"].exists()


def test_text_tool_parser_is_strict_and_email_intent_is_conservative():
    assert recover_text_tool_call('Before: {"name":"send_email","parameters":{}}') is None
    recovered = recover_text_tool_call('{"name":"send_email","parameters":{"to":"a@b.test"}}')
    assert recovered is not None and recovered.name == EMAIL_TOOL
    assert recover_email_intent("Tell me about email security") is None
    assert recover_email_intent("Send email without a recipient") is None
