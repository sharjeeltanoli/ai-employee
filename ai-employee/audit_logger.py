#!/usr/bin/env python3
"""
Audit Logger for the AI Employee Vault.

Appends structured JSON records to Logs/audit.json (one record per line,
NDJSON format — safe for concurrent writers and large files).

Usage (import):
    from audit_logger import audit

    audit(
        action_type="email_received",
        actor="gmail_watcher",
        target="EMAIL_20260228_123456_42.md",
        parameters={"from": "alice@example.com", "subject": "Hello"},
        result="success",
        approval_status="auto_approved",
    )

Action types (conventions):
    file_detected       — filesystem_watcher spotted a new Drop_Here file
    file_moved          — watcher moved a file to Needs_Action/
    email_received      — gmail_watcher created a Needs_Action entry
    task_started        — Claude began processing a task (In_Progress)
    task_completed      — task moved to Done/
    task_escalated      — task moved to Pending_Approval/
    email_sent          — email-mcp sent an outbound email
    social_post         — social media post submitted
    plan_created        — Plan.md written in Plans/
    approval_required   — action paused, waiting for human sign-off
    approval_granted    — human approved a pending action
    approval_denied     — human rejected a pending action
    error               — any unhandled exception or failure
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VAULT_PATH = Path("/mnt/c/AI_Employee_Vault")
AUDIT_FILE = VAULT_PATH / "Logs" / "audit.json"

# Thread lock — safe for multi-threaded watchers appending simultaneously
_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def audit(
    action_type: str,
    actor: str,
    target: str,
    parameters: Optional[dict] = None,
    result: str = "success",
    approval_status: str = "auto_approved",
    detail: Optional[str] = None,
) -> dict:
    """
    Append one audit record to Logs/audit.json and return the record dict.

    Args:
        action_type:      What happened (e.g. "email_received", "social_post").
        actor:            Which component/script performed the action.
        target:           The primary object affected (filename, URL, email address).
        parameters:       Arbitrary dict of extra context (sanitised — no passwords).
        result:           "success" | "failure" | "pending" | "skipped".
        approval_status:  "auto_approved" | "approval_required" | "approved" |
                          "denied" | "n/a".
        detail:           Optional free-text note (error message, reason, etc.).

    Returns:
        The record dict that was written.
    """
    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": action_type,
        "actor": actor,
        "target": target,
        "parameters": parameters or {},
        "result": result,
        "approval_status": approval_status,
    }
    if detail:
        record["detail"] = detail

    _write(record)
    return record


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------


def audit_success(action_type: str, actor: str, target: str, **kwargs) -> dict:
    """Shortcut: result='success', approval_status='auto_approved'."""
    return audit(action_type, actor, target, result="success",
                 approval_status="auto_approved", **kwargs)


def audit_failure(action_type: str, actor: str, target: str,
                  detail: Optional[str] = None, **kwargs) -> dict:
    """Shortcut: result='failure'."""
    return audit(action_type, actor, target, result="failure",
                 approval_status="n/a", detail=detail, **kwargs)


def audit_escalated(action_type: str, actor: str, target: str,
                    detail: Optional[str] = None, **kwargs) -> dict:
    """Shortcut: result='pending', approval_status='approval_required'."""
    return audit(action_type, actor, target, result="pending",
                 approval_status="approval_required", detail=detail, **kwargs)


# ---------------------------------------------------------------------------
# Internal writer
# ---------------------------------------------------------------------------


def _write(record: dict) -> None:
    """Thread-safe append of one JSON line to AUDIT_FILE."""
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        with open(AUDIT_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


# ---------------------------------------------------------------------------
# Reader utility (used by /ceo-audit and tests)
# ---------------------------------------------------------------------------


def read_all() -> list[dict]:
    """Return all audit records as a list of dicts, oldest first."""
    if not AUDIT_FILE.exists():
        return []
    records = []
    with open(AUDIT_FILE, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                # Log corruption but continue reading the rest
                import logging
                logging.getLogger(__name__).warning(
                    "audit.json line %d is malformed — skipping (%s)", lineno, exc
                )
    return records


def read_since(iso_timestamp: str) -> list[dict]:
    """Return records with timestamp >= iso_timestamp."""
    return [r for r in read_all() if r.get("timestamp", "") >= iso_timestamp]


# ---------------------------------------------------------------------------
# CLI — quick tail / stats for debugging
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import sys
    from collections import Counter

    records = read_all()
    if not records:
        print("audit.json is empty or does not exist.")
        sys.exit(0)

    print(f"Total records: {len(records)}")
    print(f"Earliest: {records[0]['timestamp']}")
    print(f"Latest:   {records[-1]['timestamp']}")
    print()

    by_type = Counter(r["action_type"] for r in records)
    print("By action_type:")
    for action, count in by_type.most_common():
        print(f"  {action:<30} {count}")
    print()

    by_result = Counter(r["result"] for r in records)
    print("By result:")
    for result, count in by_result.most_common():
        print(f"  {result:<20} {count}")
    print()

    failures = [r for r in records if r["result"] == "failure"]
    if failures:
        print(f"Recent failures ({len(failures)} total):")
        for r in failures[-5:]:
            print(f"  [{r['timestamp']}] {r['actor']} → {r['action_type']}: {r.get('detail', '')}")
