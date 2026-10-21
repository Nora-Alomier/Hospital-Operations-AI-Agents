from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from shared.config import DOCUMENTS_DIR
from shared.database import initialize_database
from shared.tools import HospitalTools


@pytest.fixture()
def project_fixture(tmp_path: Path):
    db_path = tmp_path / "hospital.db"
    documents_dir = tmp_path / "documents"
    shutil.copytree(DOCUMENTS_DIR, documents_dir)
    initialize_database(db_path, reset=True)
    return {
        "db": db_path,
        "documents": documents_dir,
        "plain_outbox": tmp_path / "plain_outbox.jsonl",
        "secure_outbox": tmp_path / "secure_outbox.jsonl",
        "audit": tmp_path / "audit.jsonl",
    }


@pytest.fixture()
def hospital_tools(project_fixture):
    return HospitalTools(
        db_path=project_fixture["db"],
        documents_dir=project_fixture["documents"],
        outbox_path=project_fixture["plain_outbox"],
    )
