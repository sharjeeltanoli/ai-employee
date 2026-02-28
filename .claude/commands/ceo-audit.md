# CEO Audit Skill

You are the AI Employee generating a Security & Activity Audit Report. Read the
audit log and produce a clear, factual report the CEO can use to verify the system
is behaving correctly and spot any anomalies.

---

## Step 1 — Read the audit log

Read `/mnt/c/AI_Employee_Vault/Logs/audit.json`.

The file is newline-delimited JSON (one record per line). Each record has:

```
timestamp       ISO 8601 UTC datetime
action_type     what happened (e.g. "email_received", "file_moved", "social_post")
actor           which script or component performed the action
target          the primary object affected (filename, URL, email address)
parameters      dict of extra context
result          "success" | "failure" | "pending" | "skipped"
approval_status "auto_approved" | "approval_required" | "approved" | "denied" | "n/a"
detail          (optional) free-text note or error message
```

If the file does not exist or is empty, note "No audit records found" and stop.

---

## Step 2 — Establish reporting window

Get today's date. The default reporting window is the **last 7 days**.
Filter records into:
- **This week** — timestamp within the last 7 days
- **All time** — every record in the file

---

## Step 3 — Calculate summary statistics

For the reporting window compute:

| Metric | How |
|--------|-----|
| Total actions | Count all records |
| Successful actions | result == "success" |
| Failed actions | result == "failure" |
| Pending actions | result == "pending" |
| Auto-approved | approval_status == "auto_approved" |
| Required human approval | approval_status == "approval_required" |
| Approved by human | approval_status == "approved" |
| Denied by human | approval_status == "denied" |
| Unique actors | distinct values of the `actor` field |

---

## Step 4 — Break down by action type

Count records per `action_type` for this week. Sort descending by count.

Also compute a per-actor breakdown: for each actor, count successes and failures.

---

## Step 5 — List all failures

For every record where `result == "failure"`:
- Timestamp
- Actor
- Action type
- Target
- Detail / error message

Flag any actor with more than 3 failures this week as a **repeated failure**.

---

## Step 6 — List approval-required actions

For every record where `approval_status == "approval_required"`:
- Timestamp
- Actor
- Action type
- Target
- Current status (still pending, or subsequently approved/denied?)
- How long it has been waiting (compute from timestamp to now)

Flag any approval waiting more than 48 hours as **overdue**.

---

## Step 7 — Anomaly detection

Flag any of the following as anomalies:

1. **High failure rate** — more than 20% of actions this week failed
2. **Unknown actor** — an actor name not in the expected list:
   `filesystem_watcher`, `gmail_watcher`, `linkedin_poster`,
   `social_poster`, `twitter_poster`, `claude_agent`, `email-mcp`, `odoo-mcp`
3. **After-hours activity** — any action between 00:00–05:00 UTC that is
   not a scheduled watcher poll (`email_poll`, `file_detected`)
4. **Rapid repeated action** — same `action_type` + `actor` + `target`
   combination appearing more than 5 times within any 10-minute window
5. **Sensitive action without approval** — any `action_type` containing
   "email_sent", "social_post", or "payment" where `approval_status` is
   neither "auto_approved" nor "approved"

List each anomaly with: type, description, affected records count, and
recommended action.

---

## Step 8 — Write the audit report

Determine today's date in YYYY-MM-DD format.
Create `/mnt/c/AI_Employee_Vault/Briefings/YYYY-MM-DD_Audit_Report.md`
using this exact template:

```markdown
---
generated: [ISO datetime]
reporting_period: [7-day window start] to [today]
generated_by: AI Employee (Claude) — /ceo-audit skill
---

# Security & Activity Audit Report — [Day, Month DD YYYY]

## Executive Summary

[2–3 sentences. State overall system health. Call out the most important
finding — either reassurance that everything is clean, or the top anomaly
requiring attention.]

---

## Summary Statistics (Last 7 Days)

| Metric | This Week | All Time |
|--------|-----------|----------|
| Total actions | [n] | [n] |
| Successful | [n] | [n] |
| Failed | [n] | [n] |
| Pending | [n] | [n] |
| Auto-approved | [n] | [n] |
| Required human approval | [n] | [n] |
| Approved by human | [n] | [n] |
| Denied by human | [n] | [n] |

---

## Actions by Type (This Week)

| Action Type | Count | Success | Failure |
|-------------|-------|---------|---------|
| [type] | [n] | [n] | [n] |

---

## Actions by Actor (This Week)

| Actor | Total | Success | Failure | Failure Rate |
|-------|-------|---------|---------|--------------|
| [actor] | [n] | [n] | [n] | [x%] |

---

## Failures This Week

[For each failure, one bullet:]
- `[timestamp]` **[actor]** → `[action_type]` on `[target]`
  — [detail/error message]

[If none: _No failures recorded this week._]

[If any actor has >3 failures:]
> ⚠️ **Repeated failure:** [actor] failed [n] times — investigate immediately.

---

## Approval-Required Actions

[For each approval-required record:]
- `[timestamp]` **[actor]** → `[action_type]` on `[target]`
  Status: [pending / approved / denied] | Waiting: [duration]
  [⚠️ OVERDUE if > 48 h]

[If none: _No actions required human approval this week._]

---

## Anomalies Detected

[For each anomaly from Step 7:]
- **[Anomaly type]** — [description]
  Affected: [n] records | Recommended action: [specific action]

[If none: _No anomalies detected._]

---

## Full Action Log (This Week)

[Markdown table of all records this week, newest first:]

| Timestamp | Actor | Action | Target | Result | Approval |
|-----------|-------|--------|--------|--------|----------|
| [ts] | [actor] | [action_type] | [target] | [result] | [approval_status] |

---

## System Health Assessment

- **Audit log file:** `/mnt/c/AI_Employee_Vault/Logs/audit.json`
- **Total records on file:** [n]
- **Oldest record:** [timestamp]
- **Newest record:** [timestamp]
- **Actors seen (all time):** [comma-separated list]
- **Report generated:** [ISO datetime]
```

---

## Step 9 — Update Dashboard.md

Open `/mnt/c/AI_Employee_Vault/Dashboard.md` and add a new line at the
top of `## Recent Activity`:

```
- **[today's date]** | Audit report generated → [Briefings/YYYY-MM-DD_Audit_Report.md] — [n] actions, [n] failures, [n] anomalies
```

---

## Step 10 — Report to the user

After writing the file and updating the dashboard, output:

1. The full path of the generated audit report.
2. A 3-bullet summary:
   - Total actions this week and overall failure rate
   - Any anomalies found (or "no anomalies detected")
   - Most active actor and most common action type
3. Confirm Dashboard.md was updated.
