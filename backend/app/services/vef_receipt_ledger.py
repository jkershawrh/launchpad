"""Local durable, append-only ledger for sanitized VEF aggregate receipts."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.services.vef_telemetry_aggregation import aggregate_vef_receipts


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


class VEFReceiptLedger:
    """Persist complete sanitized batches; this is not the production HA store."""

    def __init__(self, path: Path, *, integrity_key: bytes) -> None:
        if not isinstance(integrity_key, bytes) or len(integrity_key) < 16:
            raise ValueError("an external integrity key of at least 16 bytes is required")
        self.path = path
        self._key = integrity_key
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS vef_receipts (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id TEXT NOT NULL UNIQUE,
                pilot_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_chain_hash TEXT NOT NULL,
                chain_hash TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _chain(self, previous: str, payload_sha256: str) -> str:
        return hmac.new(
            self._key, f"{previous}:{payload_sha256}".encode(), hashlib.sha256
        ).hexdigest()

    def _verify_rows(self, rows: list[tuple]) -> list[dict[str, Any]]:
        previous = "0" * 64
        receipts: list[dict[str, Any]] = []
        for (
            _sequence,
            receipt_id,
            _pilot_id,
            raw,
            stored_digest,
            stored_previous,
            stored_chain,
        ) in rows:
            digest = hashlib.sha256(raw.encode()).hexdigest()
            chain = self._chain(previous, digest)
            if stored_digest != digest or stored_previous != previous or stored_chain != chain:
                raise ValueError("ledger integrity verification failed")
            payload = json.loads(raw)
            if payload.get("receipt_id") != receipt_id:
                raise ValueError("ledger integrity verification failed")
            receipts.append(payload)
            previous = chain
        return receipts

    def append_batch(self, receipts: list[dict[str, Any]]) -> dict[str, Any]:
        summary = aggregate_vef_receipts(receipts)
        inserted = replayed = 0
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT sequence, receipt_id, pilot_id, payload_json, payload_sha256, previous_chain_hash, chain_hash FROM vef_receipts ORDER BY sequence"
            ).fetchall()
            self._verify_rows(rows)
            previous = rows[-1][6] if rows else "0" * 64
            existing = {row[1]: row[3] for row in rows}
            for receipt in receipts:
                raw = _canonical(receipt).decode()
                receipt_id = receipt["receipt_id"]
                if receipt_id in existing:
                    if existing[receipt_id] != raw:
                        raise ValueError("conflicting receipt replay")
                    replayed += 1
                    continue
                digest = hashlib.sha256(raw.encode()).hexdigest()
                chain = self._chain(previous, digest)
                connection.execute(
                    "INSERT INTO vef_receipts (receipt_id, pilot_id, payload_json, payload_sha256, previous_chain_hash, chain_hash) VALUES (?, ?, ?, ?, ?, ?)",
                    (receipt_id, summary["pilot_id"], raw, digest, previous, chain),
                )
                previous = chain
                inserted += 1
        return {"inserted": inserted, "replayed": replayed, "pilot_id": summary["pilot_id"]}

    def load_pilot(self, pilot_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT sequence, receipt_id, pilot_id, payload_json, payload_sha256, previous_chain_hash, chain_hash FROM vef_receipts ORDER BY sequence"
            ).fetchall()
        receipts = self._verify_rows(rows)
        return [receipt for receipt in receipts if receipt["pilot_id"] == pilot_id]
