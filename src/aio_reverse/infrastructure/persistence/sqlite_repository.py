"""SQLite implementation of IPersistencePort."""

import json
from pathlib import Path
from aio_reverse.application.ports.persistence_port import IPersistencePort
from aio_reverse.domain.entities.artifact import Artifact, ArtifactKind
from aio_reverse.domain.entities.endpoint import ApiEndpoint, HttpMethod
from aio_reverse.domain.entities.evidence import EvidenceRecord, ProvenanceKind
from aio_reverse.infrastructure.persistence.database import DatabaseManager


class SqliteRepository(IPersistencePort):
    """Concrete repository implementing IPersistencePort over SQLite."""

    def __init__(self, db_manager: DatabaseManager):
        self._db = db_manager

    def save_artifact(self, artifact: Artifact) -> None:
        sql = """
        INSERT INTO artifacts (sha256, path, kind, size_bytes, package_name)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(sha256) DO UPDATE SET
            path = excluded.path,
            size_bytes = excluded.size_bytes,
            package_name = excluded.package_name;
        """
        with self._db.get_connection() as conn:
            conn.execute(
                sql,
                (
                    artifact.sha256,
                    str(artifact.path),
                    artifact.kind.value,
                    artifact.size_bytes,
                    artifact.package_name,
                ),
            )

    def get_artifact(self, sha256: str) -> Artifact | None:
        sql = "SELECT sha256, path, kind, size_bytes, package_name FROM artifacts WHERE sha256 = ?;"
        with self._db.get_connection() as conn:
            row = conn.execute(sql, (sha256,)).fetchone()
            if row is None:
                return None
            return Artifact(
                path=Path(row["path"]),
                kind=ArtifactKind(row["kind"]),
                sha256=row["sha256"],
                size_bytes=row["size_bytes"],
                package_name=row["package_name"],
            )

    def save_endpoints(self, artifact_sha256: str, endpoints: list[ApiEndpoint]) -> None:
        sql = """
        INSERT INTO endpoints (
            artifact_sha256, url, method, headers_json, query_params_json,
            signature_headers_json, is_authenticated
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        with self._db.get_connection() as conn:
            for ep in endpoints:
                conn.execute(
                    sql,
                    (
                        artifact_sha256,
                        ep.url,
                        ep.method.value,
                        json.dumps(ep.headers),
                        json.dumps(ep.query_params),
                        json.dumps(ep.signature_headers),
                        1 if ep.is_authenticated else 0,
                    ),
                )

    def get_endpoints(self, artifact_sha256: str) -> list[ApiEndpoint]:
        sql = "SELECT url, method, headers_json, query_params_json, signature_headers_json, is_authenticated FROM endpoints WHERE artifact_sha256 = ?;"
        with self._db.get_connection() as conn:
            rows = conn.execute(sql, (artifact_sha256,)).fetchall()
            return [
                ApiEndpoint(
                    url=row["url"],
                    method=HttpMethod(row["method"]),
                    headers=json.loads(row["headers_json"]),
                    query_params=json.loads(row["query_params_json"]),
                    signature_headers=json.loads(row["signature_headers_json"]),
                    is_authenticated=bool(row["is_authenticated"]),
                )
                for row in rows
            ]

    def save_evidence(self, target_sha256: str, evidence: EvidenceRecord) -> None:
        sql = """
        INSERT INTO evidence_records (
            evidence_id, target_sha256, tool_name, provenance, confidence_score, data_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(evidence_id) DO UPDATE SET
            confidence_score = excluded.confidence_score,
            data_json = excluded.data_json;
        """
        with self._db.get_connection() as conn:
            conn.execute(
                sql,
                (
                    evidence.evidence_id,
                    target_sha256,
                    evidence.tool_name,
                    evidence.provenance.value,
                    evidence.confidence_score,
                    json.dumps(evidence.data),
                ),
            )

    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        sql = "SELECT evidence_id, tool_name, provenance, confidence_score, data_json, created_at FROM evidence_records WHERE evidence_id = ?;"
        with self._db.get_connection() as conn:
            row = conn.execute(sql, (evidence_id,)).fetchone()
            if row is None:
                return None
            return EvidenceRecord(
                evidence_id=row["evidence_id"],
                tool_name=row["tool_name"],
                provenance=ProvenanceKind(row["provenance"]),
                confidence_score=row["confidence_score"],
                data=json.loads(row["data_json"]),
            )
