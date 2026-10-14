"""SQLite DDL Schema definitions and initial migrations."""

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS artifacts (
    sha256 TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    package_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS endpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_sha256 TEXT NOT NULL,
    url TEXT NOT NULL,
    method TEXT NOT NULL,
    headers_json TEXT NOT NULL DEFAULT '{}',
    query_params_json TEXT NOT NULL DEFAULT '{}',
    signature_headers_json TEXT NOT NULL DEFAULT '[]',
    is_authenticated INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (artifact_sha256) REFERENCES artifacts (sha256) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crypto_routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_sha256 TEXT NOT NULL,
    name TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    source_location TEXT NOT NULL,
    key_candidates_json TEXT NOT NULL DEFAULT '[]',
    iv_candidates_json TEXT NOT NULL DEFAULT '[]',
    input_parameters_json TEXT NOT NULL DEFAULT '[]',
    code_snippet TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (artifact_sha256) REFERENCES artifacts (sha256) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id TEXT PRIMARY KEY,
    target_sha256 TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    provenance TEXT NOT NULL,
    confidence_score REAL NOT NULL DEFAULT 1.0,
    data_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (target_sha256) REFERENCES artifacts (sha256) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_endpoints_artifact ON endpoints (artifact_sha256);
CREATE INDEX IF NOT EXISTS idx_crypto_artifact ON crypto_routines (artifact_sha256);
CREATE INDEX IF NOT EXISTS idx_evidence_target ON evidence_records (target_sha256);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Executes initial schema DDL to prepare SQLite tables."""
    conn.executescript(SCHEMA_SQL)
