#!/usr/bin/env python3
"""
Ralph Wiggum Stop Hook
"I'm helping!" — keeps Claude working until In_Progress/ is empty.

Blocks Claude Code from exiting if /mnt/c/AI_Employee_Vault/In_Progress/
contains any task files. Re-injects the /process-files prompt so Claude
continues working. Releases after MAX_ITERATIONS to prevent infinite loops.

Protocol:
  - Reads JSON from stdin (Claude Code hook payload)
  - Writes JSON to stdout: {"decision": "block", "reason": "..."} to block
  - Exit 0 in all cases (decision field controls behaviour, not exit code)
  - Logs every iteration to Logs/ralph_wiggum.log
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
VAULT        = Path("/mnt/c/AI_Employee_Vault")
IN_PROGRESS  = VAULT / "In_Progress"
LOG_FILE     = VAULT / "Logs" / "ralph_wiggum.log"
COUNTER_FILE = Path("/tmp/ralph_wiggum_iterations.json")
MAX_ITERATIONS = 10

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_counters() -> dict:
    if COUNTER_FILE.exists():
        try:
            return json.loads(COUNTER_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_counters(counters: dict) -> None:
    COUNTER_FILE.write_text(json.dumps(counters))


def get_task_files() -> list:
    """Return names of visible task files currently sitting in In_Progress/."""
    if not IN_PROGRESS.exists():
        return []
    return [
        f.name for f in sorted(IN_PROGRESS.iterdir())
        if f.is_file() and not f.name.startswith(".")
    ]


def allow_stop(session_id: str, counters: dict, reason: str) -> None:
    """Clean up counter and exit without blocking."""
    counters.pop(session_id, None)
    save_counters(counters)
    logger.info("Allowing Claude to exit — %s", reason)
    sys.exit(0)


def block_stop(session_id: str, iteration: int, counters: dict, tasks: list) -> None:
    """Increment counter, write block decision to stdout, and exit."""
    counters[session_id] = iteration
    save_counters(counters)

    task_list = "\n".join(f"  • {t}" for t in tasks)
    reason = (
        f"[Ralph Wiggum Hook — iteration {iteration}/{MAX_ITERATIONS}]\n"
        f"There are {len(tasks)} task(s) still waiting in /In_Progress/:\n"
        f"{task_list}\n\n"
        f"Please run /process-files to process these tasks. "
        f"Move each file out of /In_Progress/ when done. "
        f"When /In_Progress/ is empty you may stop."
    )

    logger.info(
        "Blocking exit — re-injecting /process-files prompt "
        "(iteration %d/%d, tasks: %s)",
        iteration, MAX_ITERATIONS, tasks,
    )

    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Read hook payload from stdin
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        logger.warning("Could not parse hook input JSON — allowing stop.")
        sys.exit(0)

    session_id        = hook_input.get("session_id", "unknown")
    stop_hook_active  = hook_input.get("stop_hook_active", False)

    # Load per-session iteration counter
    counters  = load_counters()
    iteration = counters.get(session_id, 0)

    # Check what's in In_Progress/
    tasks = get_task_files()

    logger.info(
        "Session=%s | iteration=%d | stop_hook_active=%s | in_progress=%d %s",
        session_id, iteration, stop_hook_active, len(tasks), tasks,
    )

    # ── No tasks in flight → let Claude exit cleanly ──────────────────────────
    if not tasks:
        allow_stop(session_id, counters, "In_Progress/ is empty")

    # ── Safety ceiling → release after MAX_ITERATIONS ─────────────────────────
    if iteration >= MAX_ITERATIONS:
        logger.warning(
            "MAX_ITERATIONS (%d) reached for session %s — releasing Claude. "
            "Tasks still present: %s",
            MAX_ITERATIONS, session_id, tasks,
        )
        allow_stop(session_id, counters, f"max iterations ({MAX_ITERATIONS}) reached")

    # ── Tasks still present → block and re-inject ─────────────────────────────
    block_stop(session_id, iteration + 1, counters, tasks)


if __name__ == "__main__":
    main()
