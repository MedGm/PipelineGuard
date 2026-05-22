import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    contract_id   TEXT NOT NULL,
    version       TEXT NOT NULL,
    owner         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    yaml_content  TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    PRIMARY KEY (contract_id, version)
);
"""

def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn
