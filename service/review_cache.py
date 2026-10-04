"""Accept one immutable model result for each logical review input.

The caller supplies a short SQLite write transaction. Concurrent inferences may
both finish, but their consumers must use the same accepted payload and owner.
"""
from __future__ import annotations
import hashlib
import json
import threading

from .store import dumps, utcnow


_KEYS = {
    "temporal_review_cache": ("cache_key",),
    "fact_definition_cache": ("cache_key",),
    "metric_directory_reviews": ("project_id", "catalog_hash", "prompt_hash", "model"),
}

_INFLIGHT = {}
_INFLIGHT_LOCK = threading.Lock()


def shared_result(store, table, keys, infer, cancelled=lambda: False, validate=lambda value: None):
    """One live inference per immutable cache input in this owning service.

    Waiters only wait on completion, never on the owner's cancellation signal.
    A failed/cancelled owner publishes nothing; the next live waiter obtains
    ownership and invokes its own Pi runtime. No result provenance is rewritten.
    infer returns (payload, actual_request_count).
    """
    fields = _KEYS.get(table)
    if fields is None or set(keys) != set(fields):
        raise ValueError("invalid_review_cache_identity")
    identity = (str(store.path.resolve()), table, tuple(keys[field] for field in fields))
    where = " AND ".join(f"{field}=?" for field in fields)

    def read():
        with store.connect() as db:
            row = db.execute(f"SELECT result_json FROM {table} WHERE {where}",
                             [keys[field] for field in fields]).fetchone()
        if row is None:
            return None
        result = json.loads(row[0])
        validate(result)
        return result

    while True:
        if cancelled():
            raise InterruptedError("cancelled")
        cached = read()
        if cached is not None:
            return cached, True, 0
        with _INFLIGHT_LOCK:
            entry = _INFLIGHT.get(identity)
            owner = entry is None or entry[1]()
            if owner:
                if entry is not None:
                    entry[0].set()
                entry = _INFLIGHT[identity] = (threading.Event(), cancelled)
            done = entry[0]
        if not owner:
            done.wait(0.05)
            continue
        try:
            # A previous owner may have published between our read and claim.
            cached = read()
            if cached is not None:
                return cached, True, 0
            if cancelled():
                raise InterruptedError("cancelled")
            proposed, requests = infer()
            validate(proposed)
            if cancelled():
                raise InterruptedError("cancelled")
            with store.connect(write=True) as db:
                accepted, inserted = accept_result(db, table, keys, proposed)
            validate(accepted)
            return accepted, not inserted, requests
        finally:
            with _INFLIGHT_LOCK:
                if _INFLIGHT.get(identity) is entry:
                    del _INFLIGHT[identity]
                done.set()


def result_hash(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def accept_result(db, table, keys, payload):
    """Insert once, then return the stored winner rather than the proposed value."""
    fields = _KEYS.get(table)
    if fields is None or set(keys) != set(fields):
        raise ValueError("invalid_review_cache_identity")
    values = [keys[field] for field in fields]
    columns = ",".join((*fields, "result_json", "created_at"))
    placeholders = ",".join("?" for _ in range(len(fields) + 2))
    inserted = db.execute(f"INSERT OR IGNORE INTO {table} ({columns}) VALUES({placeholders})",
                          [*values, dumps(payload), utcnow()]).rowcount == 1
    where = " AND ".join(f"{field}=?" for field in fields)
    row = db.execute(f"SELECT result_json FROM {table} WHERE {where}", values).fetchone()
    if row is None:
        raise RuntimeError("review_cache_acceptance_missing")
    return json.loads(row[0]), inserted
