# CEO Briefing Skill

You are the AI Employee generating a Monday Morning CEO Briefing. This is a
concise, honest, data-driven report that gives the CEO a full picture of the
week in under 3 minutes of reading.

---

## Step 1 — Establish the reporting period

Get today's date. The reporting period is the 7 calendar days ending today
(i.e. last Monday 00:00 through today 23:59). You will use this window to
filter activity in every step below.

---

## Step 2 — Read business targets

Read `/mnt/c/AI_Employee_Vault/Business_Goals.md` for current targets, KPIs,
and priorities.

- If the file does not exist, note "Business_Goals.md not yet defined" in the
  Executive Summary and continue — do not abort.

---

## Step 3 — Audit the /Done folder

List every file in `/mnt/c/AI_Employee_Vault/Done/` and classify each one:

- **Email** — filename starts with `EMAIL_`
- **File task** — filename starts with `FILE_`
- **Named task** — filename starts with `TASK_`
- **Other** — anything else

To determine whether a file falls in this week's reporting period:
1. Extract the 8-digit date from the filename if present (e.g. `EMAIL_20260224_...` → `20260224`).
2. If no date is in the filename, use the file's last-modified date.

Count totals for each category for (a) this week and (b) all time.

For each item completed **this week**, read the file and extract a one-line
summary: what it was and what was done.

---

## Step 4 — Audit the /Logs folder

Read every file in `/mnt/c/AI_Employee_Vault/Logs/`:

- `cron.log` — count successful Claude runs, failed runs, and last run timestamp.
- `ralph_wiggum.log` — count how many times the stop hook blocked an exit (shows
  how many in-progress loops ran to completion).
- Any other log files — summarise notable events.

Extract the most recent entry from each log as "last activity".

---

## Step 5 — Audit /Pending_Approval

List every file in `/mnt/c/AI_Employee_Vault/Pending_Approval/`. For each file:
- Read its contents
- Note: what action is pending, who it involves, what the value/risk is, and
  how long it has been waiting (use the date in the filename or frontmatter
  `created:` field)

Flag any item waiting more than 48 hours as **overdue**.

---

## Step 6 — Audit /Needs_Action

List every file in `/mnt/c/AI_Employee_Vault/Needs_Action/`. Count them and
note the oldest item (by filename date or modified date). This represents
the current backlog.

---

## Step 7 — Audit /In_Progress

List every visible (non-dot) file in `/mnt/c/AI_Employee_Vault/In_Progress/`.
Any task sitting here represents work that was started but not finished.

---

## Step 8 — Read Dashboard.md

Read `/mnt/c/AI_Employee_Vault/Dashboard.md` for any manually recorded context,
flagged items, or notes that do not appear in the folder audit.

---

## Step 9 — Calculate stats

Compute the following figures for the briefing:

| Metric | How to calculate |
|--------|-----------------|
| Emails processed this week | Count of `EMAIL_` files in /Done with a date in this week |
| Files handled this week | Count of `FILE_` files in /Done with a date in this week |
| Named tasks completed this week | Count of `TASK_` files in /Done with a date in this week |
| Total items completed this week | Sum of the three above |
| Items pending approval | Count of files in /Pending_Approval |
| Overdue approvals (>48 h) | Count of those waiting > 48 hours |
| Current backlog | Count of files in /Needs_Action |
| In-progress (stalled) | Count of visible files in /In_Progress |
| Automation runs this week | From cron.log |
| Stop-hook loops this week | From ralph_wiggum.log |

---

## Step 10 — Identify bottlenecks

A bottleneck exists when any of the following is true:

- An item in /Pending_Approval is more than 48 hours old
- /Needs_Action has more than 10 unprocessed items
- /In_Progress has any stalled task files
- cron.log shows a failed run in the last 48 hours
- The same sender or topic appears in multiple /Needs_Action items (pile-up)

List each bottleneck clearly with its age and recommended resolution.

---

## Step 11 — Generate proactive suggestions

Based on everything you have read, produce 3–5 actionable suggestions the CEO
should consider this week. Examples of good suggestions:

- "The follow-up email to Ahmed (INV-001, $500) has been pending approval since
  [date]. Approve or reject it to unblock the pipeline."
- "Business_Goals.md is missing — defining targets will allow the briefing to
  track progress against goals."
- "Ralph Wiggum fired N times this week, meaning N tasks required multiple
  iterations. Review those task files for complexity patterns."

Be specific — reference real file names, dates, amounts, and names from the
audit. Do not give generic advice.

---

## Step 12 — Write the briefing file

Determine today's date in YYYY-MM-DD format.
Create `/mnt/c/AI_Employee_Vault/Briefings/YYYY-MM-DD_CEO_Briefing.md` using
this exact template (replace all `[...]` placeholders):

```markdown
---
generated: [ISO datetime]
reporting_period: [Monday date] to [today's date]
generated_by: AI Employee (Claude)
---

# CEO Briefing — [Day, Month DD YYYY]

## Executive Summary

[2–4 sentences. State the overall health of the operation this week.
Call out the single most important thing needing the CEO's attention.
Be direct — no fluff.]

---

## Weekly Activity Stats

| Metric | This Week | All Time |
|--------|-----------|----------|
| Emails processed | [n] | [n] |
| Files handled | [n] | [n] |
| Named tasks completed | [n] | [n] |
| **Total items completed** | **[n]** | **[n]** |
| Items pending approval | [n] | — |
| Overdue approvals (>48 h) | [n] | — |
| Current backlog (/Needs_Action) | [n] | — |
| Stalled tasks (/In_Progress) | [n] | — |
| Automation runs | [n] | — |
| Stop-hook loops fired | [n] | — |

---

## Completed This Week

[For each item completed this week, one bullet:
- **[TYPE]** `[filename]` — [one-line description of what was done]]

If nothing was completed this week, write: _No items completed in this period._

---

## Pending Items — Action Required

[For each file in /Pending_Approval:
- **[age]** `[filename]` — [what it is, what decision is needed, value/risk]
  ⚠️ OVERDUE if waiting > 48 h]

If nothing is pending, write: _No items pending approval._

---

## Bottlenecks

[For each bottleneck identified in Step 10:
- **[Bottleneck type]** — [description, age, recommended action]]

If no bottlenecks, write: _No bottlenecks detected._

---

## Proactive Suggestions

[Numbered list of 3–5 specific, actionable suggestions from Step 11]

---

## System Health

- **Last automation run:** [timestamp from cron.log, or "no runs recorded"]
- **Last email check:** [infer from most recent EMAIL_ file in /Done or /Needs_Action]
- **Business goals on file:** [Yes — link to Business_Goals.md / No — not yet defined]
- **Briefing generated:** [ISO datetime]
```

---

## Step 13 — Update Dashboard.md

Open `/mnt/c/AI_Employee_Vault/Dashboard.md` and:

1. Update `Last Updated:` to today's date.
2. Update `Active Tasks:` to the current /Needs_Action count.
3. Update `Pending Approvals:` to the current /Pending_Approval count.
4. Add a new line at the top of `## Recent Activity`:
   `- **[today's date]** | CEO Briefing generated → [Briefings/YYYY-MM-DD_CEO_Briefing.md]`

---

## Step 14 — Report to the user

After writing the file and updating the dashboard, output:

1. The full path of the generated briefing file.
2. A 3-bullet summary of the top findings (most important things from the briefing).
3. Confirm Dashboard.md was updated.
