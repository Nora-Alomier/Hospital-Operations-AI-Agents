import json

from shared.database import maintenance_history, search_equipment
from shared.rag import load_documents, search_documents


def test_normal_equipment_query(project_fixture):
    records = search_equipment("MRI", db_path=project_fixture["db"])
    assert {record["tenant_id"] for record in records} == {"HOSP-A", "HOSP-B"}
    assert {record["equipment_id"] for record in records} == {"NS-MRI-001", "LS-MRI-002"}


def test_normal_maintenance_history(project_fixture):
    records = maintenance_history("NS-MRI-001", tenant_id="HOSP-A", db_path=project_fixture["db"])
    assert len(records) == 2
    assert all(record["tenant_id"] == "HOSP-A" for record in records)


def test_rag_loads_chunks_and_returns_citations(project_fixture):
    chunks = load_documents(project_fixture["documents"])
    assert len(chunks) >= 9
    results = search_documents(
        "ventilator failed battery self-test",
        tenant_id="HOSP-A",
        documents_dir=project_fixture["documents"],
    )
    assert results
    assert all(result["citation"].endswith(tuple(f"#chunk-{n}" for n in range(1, 20))) for result in results)
    assert any(result["source"] == "ventilator_maintenance.txt" for result in results)


def test_rag_tenant_filter_hides_other_hospital_addendum(project_fixture):
    results = search_documents(
        "Lakeside humidity movement test",
        tenant_id="HOSP-A",
        documents_dir=project_fixture["documents"],
        top_k=10,
    )
    assert all(result["tenant_id"] in {"ALL", "HOSP-A"} for result in results)
    assert not any("Lakeside Hospital addendum" in result["text"] for result in results)


def test_tool_results_are_json(hospital_tools):
    payload = json.loads(hospital_tools.search_equipment("ventilator"))
    assert payload["count"] == 2
