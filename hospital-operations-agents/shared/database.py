"""SQLite storage for fictional equipment and maintenance records."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from shared.config import DATABASE_PATH


EQUIPMENT = [
    ("NS-MRI-001", "Aurora MRI Scanner", "MRI", "HOSP-A", "Radiology", "Northstar / Level 1", "operational", "2026-11-05"),
    ("NS-VENT-014", "Breeze Ventilator 14", "Ventilator", "HOSP-A", "ICU", "Northstar / ICU Bay 4", "maintenance_due", "2026-10-28"),
    ("NS-XRAY-003", "RaySafe X-Ray 3", "X-Ray", "HOSP-A", "Emergency", "Northstar / Imaging 2", "operational", "2026-12-12"),
    ("LS-MRI-002", "Helios MRI Scanner", "MRI", "HOSP-B", "Radiology", "Lakeside / Lower Ground", "operational", "2026-11-19"),
    ("LS-VENT-008", "Breeze Ventilator 8", "Ventilator", "HOSP-B", "ICU", "Lakeside / ICU Bay 2", "out_of_service", "2026-10-22"),
    ("LS-XRAY-011", "RaySafe Mobile X-Ray 11", "X-Ray", "HOSP-B", "Surgery", "Lakeside / Theatre Store", "operational", "2027-01-08"),
]

HISTORY = [
    ("NS-MRI-001", "HOSP-A", "2026-08-04", "M. Noor", "Quarterly coil inspection completed; no defects found."),
    ("NS-MRI-001", "HOSP-A", "2026-05-03", "A. Hale", "Cryogen level and emergency stop verified."),
    ("NS-VENT-014", "HOSP-A", "2026-07-28", "M. Noor", "Replaced intake filter and passed flow calibration."),
    ("NS-XRAY-003", "HOSP-A", "2026-06-12", "S. Ali", "Detector alignment and warning-light test passed."),
    ("LS-MRI-002", "HOSP-B", "2026-08-19", "J. Reed", "Table movement and intercom check passed."),
    ("LS-VENT-008", "HOSP-B", "2026-10-20", "J. Reed", "Removed from service after battery self-test failure."),
    ("LS-XRAY-011", "HOSP-B", "2026-07-08", "K. Chen", "Cable inspection and exposure indicator test passed."),
]


def connect(db_path: Path | str = DATABASE_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: Path | str = DATABASE_PATH, *, reset: bool = False) -> Path:
    """Create or refresh the deterministic synthetic database."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if reset:
        path.unlink(missing_ok=True)
    with connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS equipment (
                equipment_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                equipment_type TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                department TEXT NOT NULL,
                location TEXT NOT NULL,
                status TEXT NOT NULL,
                maintenance_due_date TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS maintenance_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipment_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                service_date TEXT NOT NULL,
                engineer TEXT NOT NULL,
                summary TEXT NOT NULL,
                FOREIGN KEY (equipment_id) REFERENCES equipment(equipment_id)
            );
            CREATE INDEX IF NOT EXISTS idx_equipment_tenant ON equipment(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_history_tenant_equipment
                ON maintenance_history(tenant_id, equipment_id);
            """
        )
        connection.executemany(
            """INSERT OR REPLACE INTO equipment
            (equipment_id, name, equipment_type, tenant_id, department, location, status, maintenance_due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            EQUIPMENT,
        )
        connection.execute("DELETE FROM maintenance_history")
        connection.executemany(
            """INSERT INTO maintenance_history
            (equipment_id, tenant_id, service_date, engineer, summary)
            VALUES (?, ?, ?, ?, ?)""",
            HISTORY,
        )
    return path


def search_equipment(
    query: str,
    *,
    tenant_id: str | None = None,
    db_path: Path | str = DATABASE_PATH,
) -> list[dict]:
    """Search identifiers and descriptive fields with parameterized SQL."""
    wildcard = f"%{query.strip()}%"
    sql = """
        SELECT equipment_id, name, equipment_type, tenant_id, department,
               location, status, maintenance_due_date
        FROM equipment
        WHERE (equipment_id LIKE ? OR name LIKE ? OR equipment_type LIKE ?
               OR department LIKE ? OR status LIKE ?)
    """
    parameters: list[str] = [wildcard] * 5
    if tenant_id is not None:
        sql += " AND tenant_id = ?"
        parameters.append(tenant_id)
    sql += " ORDER BY equipment_id LIMIT 20"
    with connect(db_path) as connection:
        return [dict(row) for row in connection.execute(sql, parameters).fetchall()]


def maintenance_history(
    equipment_id: str,
    *,
    tenant_id: str | None = None,
    db_path: Path | str = DATABASE_PATH,
) -> list[dict]:
    """Return history, optionally restricted by the authenticated tenant."""
    sql = """
        SELECT h.equipment_id, e.name, h.tenant_id, h.service_date,
               h.engineer, h.summary
        FROM maintenance_history h
        JOIN equipment e ON e.equipment_id = h.equipment_id
        WHERE h.equipment_id = ?
    """
    parameters: list[str] = [equipment_id]
    if tenant_id is not None:
        sql += " AND h.tenant_id = ? AND e.tenant_id = ?"
        parameters.extend([tenant_id, tenant_id])
    sql += " ORDER BY h.service_date DESC"
    with connect(db_path) as connection:
        return [dict(row) for row in connection.execute(sql, parameters).fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the synthetic hospital SQLite database.")
    parser.add_argument("--reset", action="store_true", help="Replace existing synthetic data.")
    args = parser.parse_args()
    path = initialize_database(reset=args.reset)
    print(f"Initialized synthetic database: {path}")


if __name__ == "__main__":
    main()
