"""SQLite checkpoint storage for resumable account-level processing."""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


SCHEMA_VERSION = "3"


def file_sha256(path: str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_job_signature(
    input_file: str,
    mode: str,
    status: str,
    since: str,
    until: str,
    api_version: str,
    output_format: str,
) -> Dict[str, Any]:
    absolute_input = os.path.abspath(input_file)
    stat = os.stat(absolute_input)
    return {
        "schema_version": SCHEMA_VERSION,
        "input_file": absolute_input,
        "input_size": stat.st_size,
        "input_mtime_ns": stat.st_mtime_ns,
        "input_sha256": file_sha256(absolute_input),
        "mode": mode,
        "status": status,
        "since": since,
        "until": until,
        "api_version": api_version,
        "output_format": output_format,
    }


class CheckpointMismatchError(RuntimeError):
    pass


class CheckpointStore:
    def __init__(
        self,
        path: str,
        signature: Dict[str, Any],
        resume: bool,
    ) -> None:
        self.path = os.path.abspath(path)
        self.signature = signature
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        existed = os.path.exists(self.path)
        if resume and not existed:
            raise RuntimeError(
                "Checkpoint untuk --resume tidak ditemukan: {}".format(self.path)
            )
        if not resume and existed:
            os.remove(self.path)

        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        try:
            self._create_schema()

            if resume:
                self._validate_signature()
            else:
                self._write_meta("signature", signature)
                self._write_meta("created_at", datetime.now(timezone.utc).isoformat())
        except Exception:
            self.connection.close()
            raise

    def _create_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    cabang TEXT NOT NULL,
                    bisnis TEXT NOT NULL,
                    status TEXT NOT NULL,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS report_rows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_report_rows_account
                    ON report_rows(account_id);

                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_errors_account
                    ON errors(account_id);
                """
            )

    def _write_meta(self, key: str, value: Any) -> None:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                (key, encoded),
            )

    def _read_meta(self, key: str) -> Optional[Any]:
        row = self.connection.execute(
            "SELECT value FROM meta WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["value"])

    def _validate_signature(self) -> None:
        saved = self._read_meta("signature")
        if saved is None:
            raise CheckpointMismatchError(
                "Checkpoint tidak memiliki metadata signature."
            )
        if saved != self.signature:
            differing = []
            keys = sorted(set(saved.keys()) | set(self.signature.keys()))
            for key in keys:
                if saved.get(key) != self.signature.get(key):
                    differing.append(
                        "{}: checkpoint={!r}, saat_ini={!r}".format(
                            key,
                            saved.get(key),
                            self.signature.get(key),
                        )
                    )
            raise CheckpointMismatchError(
                "Checkpoint tidak cocok dengan parameter/file saat ini. {}".format(
                    "; ".join(differing)
                )
            )

    def completed_accounts(self) -> Set[str]:
        rows = self.connection.execute(
            "SELECT account_id FROM accounts WHERE status = 'completed'"
        ).fetchall()
        return {str(row["account_id"]) for row in rows}

    def save_account_result(
        self,
        account_id: str,
        cabang: str,
        bisnis: str,
        rows: List[Dict[str, Any]],
        errors: List[Dict[str, Any]],
        status: str,
    ) -> None:
        if status not in ("completed", "failed"):
            raise ValueError("Status checkpoint tidak valid: {}".format(status))

        now = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                "DELETE FROM report_rows WHERE account_id = ?",
                (account_id,),
            )
            self.connection.execute(
                "DELETE FROM errors WHERE account_id = ?",
                (account_id,),
            )
            if rows:
                self.connection.executemany(
                    "INSERT INTO report_rows(account_id, payload) VALUES (?, ?)",
                    [
                        (
                            account_id,
                            json.dumps(row, ensure_ascii=False, default=str),
                        )
                        for row in rows
                    ],
                )
            if errors:
                self.connection.executemany(
                    "INSERT INTO errors(account_id, payload) VALUES (?, ?)",
                    [
                        (
                            account_id,
                            json.dumps(item, ensure_ascii=False, default=str),
                        )
                        for item in errors
                    ],
                )
            self.connection.execute(
                """
                INSERT OR REPLACE INTO accounts(
                    account_id, cabang, bisnis, status, row_count, error_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    cabang,
                    bisnis,
                    status,
                    len(rows),
                    len(errors),
                    now,
                ),
            )

    def load_rows(self) -> List[Dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT payload FROM report_rows ORDER BY id"
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def load_errors(self) -> List[Dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT payload FROM errors ORDER BY id"
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def account_summary(self) -> List[Dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT account_id, cabang, bisnis, status, row_count, error_count, updated_at
            FROM accounts
            ORDER BY updated_at, account_id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.connection.close()

    def delete_file(self) -> None:
        self.close()
        for suffix in ("", "-wal", "-shm"):
            candidate = self.path + suffix
            if os.path.exists(candidate):
                os.remove(candidate)

    def __enter__(self) -> "CheckpointStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()
