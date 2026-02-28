# AI Employee Vault

An autonomous AI assistant that monitors inboxes, processes tasks, posts to social media, and manages a structured work vault — governed by a human-readable rulebook and a self-looping agent architecture.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INPUTS                                          │
│                                                                         │
│   Gmail (IMAP)          Drop_Here/          Cron (run_claude.sh)       │
│       │                     │                       │                  │
│  gmail_watcher.py    filesystem_watcher.py          │                  │
│       │                     │                       │                  │
└───────┼─────────────────────┼───────────────────────┼──────────────────┘
        │                     │                       │
        └──────────┬──────────┘                       │
                   ▼                                  │
          /Needs_Action/  ◄────────────────────────────┘
          (task .md files)
                   │
                   ▼
     ┌─────────────────────────┐
     │   Claude Code Agent     │
     │   (/process-files)      │◄── Company_Handbook.md (rules)
     │                         │◄── MCP: email-mcp (send replies)
     │   1. Read task          │◄── MCP: odoo-mcp  (CRM/ERP actions)
     │   2. Create Plan.md     │
     │   3. Execute or Escalate│
     └────────────┬────────────┘
                  │
       ┌──────────┼──────────────┐
       ▼          ▼              ▼
  /Done/    /Pending_Approval/  /In_Progress/
  (archive)  (awaits human)     (mid-flight)
                                     │
                   ┌─────────────────┘
                   ▼
          Ralph Wiggum Stop Hook
          (blocks exit if In_Progress/
           is non-empty; re-injects
           /process-files up to 10×)
                   │
                   ▼
            Dashboard.md  ◄── updated after every run
            Briefings/    ◄── /ceo-briefing weekly report

┌─────────────────────────────────────────────────────────────────────────┐
│                     SOCIAL MEDIA OUTPUTS                                │
│                                                                         │
│  linkedin_poster.py    social_poster.py         twitter_poster.py      │
│  (LinkedIn)            (Facebook + Instagram)   (Twitter / X)          │
│       │                       │                       │                │
│       └───────────────────────┴───────────────────────┘                │
│                               │                                         │
│                         Drop_Here/                                      │
│          linkedin_*.txt │ facebook_*.txt │ instagram_*.txt+.jpg         │
│                         │ twitter_*.txt                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Tiers

### Bronze Tier — Foundation
- Gmail IMAP watcher (`gmail_watcher.py`)
- Filesystem watcher for `Drop_Here/` (`filesystem_watcher.py`)
- Vault folder structure (`Needs_Action/`, `Done/`, `Plans/`, etc.)
- `Company_Handbook.md` rulebook
- `Dashboard.md` activity log
- `/process-files` and `/create-plan` agent skills
- `email-mcp` MCP server (send email replies via nodemailer)
- `run_claude.sh` cron wrapper

### Silver Tier — Social Media & Automation Loop
- LinkedIn Playwright poster (`linkedin_poster.py`) with session reuse
- Facebook + Instagram Playwright poster (`social_poster.py`)
- Ralph Wiggum stop hook — self-looping agent that re-injects `/process-files` until `In_Progress/` is empty
- `In_Progress/` folder for mid-flight task tracking
- `/ceo-briefing` skill — full Monday morning CEO report

### Gold Tier — CRM Integration & Twitter (in progress)
- Twitter/X Playwright poster (`twitter_poster.py`) with Firefox headless + stealth
- `odoo-mcp` MCP server — Claude can read/write Odoo CRM & ERP via tool calls
- `Business_Goals.md` — KPI targets that feed the CEO briefing
- `Briefings/` folder for generated CEO briefing archives

---

## Folder Structure

```
AI_Employee_Vault/
│
├── ai-employee/                   # Python automation (git repo root)
│   ├── filesystem_watcher.py      # Watches Drop_Here/ (PollingObserver, WSL-safe)
│   ├── gmail_watcher.py           # IMAP poller — writes .md files to /Needs_Action
│   ├── linkedin_poster.py         # Playwright LinkedIn poster with session reuse
│   ├── social_poster.py           # Playwright Facebook + Instagram poster
│   ├── twitter_poster.py          # Playwright Twitter/X poster (Firefox headless)
│   ├── auth_gmail.py              # One-time Gmail OAuth flow
│   ├── run_claude.sh              # Cron wrapper for non-interactive Claude runs
│   ├── pyproject.toml             # uv project — Python 3.11+, playwright, watchdog
│   └── sessions/                  # Saved browser sessions (gitignored)
│       ├── facebook_session.json
│       ├── instagram_session.json
│       └── twitter_session.json
│
├── mcp-servers/
│   ├── email-mcp/                 # Node.js MCP: send email via nodemailer/Gmail
│   │   ├── index.js
│   │   └── package.json
│   └── odoo-mcp/                  # Node.js MCP: Odoo CRM/ERP tool calls
│       ├── index.js
│       └── package.json
│
├── .claude/
│   ├── settings.json              # MCP server registration + hooks config
│   ├── commands/
│   │   ├── process-files.md       # /process-files skill
│   │   ├── create-plan.md         # /create-plan skill
│   │   └── ceo-briefing.md        # /ceo-briefing skill
│   └── hooks/
│       └── stop_hook.py           # Ralph Wiggum: blocks exit if In_Progress/ non-empty
│
├── Company_Handbook.md            # AI rules of engagement (policy document)
├── Business_Goals.md              # KPIs and targets (read by CEO briefing)
├── Dashboard.md                   # Live activity log — updated every run
│
├── Needs_Action/                  # Incoming task files (auto-generated .md)
├── In_Progress/                   # Tasks currently being worked on
├── Pending_Approval/              # Actions awaiting human sign-off
├── Approved/                      # Human-approved, ready to execute
├── Done/                          # Completed tasks archive
├── Drop_Here/                     # Drop any file here to trigger watchers
├── Plans/                         # Auto-generated Plan_*.md files
├── Briefings/                     # CEO briefing reports (YYYY-MM-DD_CEO_Briefing.md)
└── Logs/
    ├── cron.log                   # Output of every run_claude.sh execution
    ├── ralph_wiggum.log           # Stop hook loop log
    ├── facebook_before_post.png   # Pre-submit composer screenshot
    ├── facebook_after_post.png    # Post-submit feed screenshot
    └── twitter_*.png              # Twitter login step screenshots
```

---

## Setup

### Prerequisites

- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Node.js 18+ (for MCP servers)
- [Claude Code](https://claude.ai/code) CLI
- WSL2 (Ubuntu) recommended

### 1. Clone and install

```bash
git clone <repo-url> AI_Employee_Vault
cd AI_Employee_Vault/ai-employee
uv sync
uv run playwright install chromium
uv run playwright install firefox   # required for twitter_poster.py
```

### 2. Install MCP server dependencies

```bash
cd /mnt/c/AI_Employee_Vault/mcp-servers/email-mcp && npm install
cd /mnt/c/AI_Employee_Vault/mcp-servers/odoo-mcp  && npm install
```

### 3. Environment variables

Add to your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
# Gmail watcher + email-mcp
export GMAIL_APP_PASSWORD="your-gmail-app-password"   # 16-char Google App Password

# LinkedIn poster
export LINKEDIN_EMAIL="your@email.com"
export LINKEDIN_PASSWORD="your-linkedin-password"

# Facebook & Instagram (social_poster.py)
export FACEBOOK_EMAIL="your@email.com"
export FACEBOOK_PASSWORD="your-facebook-password"
export INSTAGRAM_EMAIL="your@email.com"
export INSTAGRAM_PASSWORD="your-instagram-password"

# Twitter / X (twitter_poster.py)
export TWITTER_EMAIL="your@email.com"
export TWITTER_PASSWORD="your-twitter-password"
export TWITTER_USERNAME="yourusername"         # handle without @, used for identity verify step

# Odoo MCP (optional — Gold Tier)
export ODOO_URL="https://your-odoo-instance.com"
export ODOO_DB="your-db-name"
export ODOO_USER="admin"
export ODOO_PASSWORD="your-odoo-password"
```

> Never commit a `.env` file. All secrets are read at runtime from environment variables only.

### 4. Gmail OAuth (one-time)

Place your Google Cloud OAuth `credentials.json` in `ai-employee/`, then:

```bash
cd ai-employee
uv run python auth_gmail.py
```

Follow the printed URL, paste the auth code back. A `token.pickle` is saved for future runs.

### 5. Start the watchers

```bash
# Terminal 1 — Gmail IMAP poller (checks every 2 min)
uv run python gmail_watcher.py

# Terminal 2 — Drop_Here folder watcher
uv run python filesystem_watcher.py
```

---

## Scripts

### `filesystem_watcher.py`

Watches `Drop_Here/` using `PollingObserver` (WSL inotify-safe). Any file dropped there is moved to `Needs_Action/` as a structured `.md` task file.

```bash
uv run python filesystem_watcher.py
```

---

### `gmail_watcher.py`

Polls Gmail via IMAP every 2 minutes. Unread emails are converted to `.md` files in `Needs_Action/` with metadata (sender, subject, body, date).

```bash
uv run python gmail_watcher.py
```

Requires: `GMAIL_APP_PASSWORD` env var + completed OAuth (`token.pickle`).

---

### `linkedin_poster.py`

Posts text to LinkedIn using Playwright. Session is persisted in `linkedin_session/session.json` so login only happens once.

```bash
# Direct post
uv run python linkedin_poster.py "Your post text here"

# Watch mode — monitors Drop_Here/ for linkedin_*.txt files
uv run python linkedin_poster.py --watch
```

Watch mode: drop `linkedin_hello.txt` into `Drop_Here/` → posts content → moves to `Done/` or `Needs_Action/`.

Requires: `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD`

---

### `social_poster.py`

Posts to **Facebook** and **Instagram** using Playwright. Sessions saved in `sessions/`.

Facebook uses a two-step composer flow (Next → Post). Before/after screenshots saved to `Logs/`.

```bash
# Facebook direct post
uv run python social_poster.py --platform facebook --content "Hello, Facebook!"

# Instagram post (image required for feed posts)
uv run python social_poster.py --platform instagram --content "Caption" --image /path/to/photo.jpg

# Watch mode — monitors Drop_Here/ for facebook_*.txt and instagram_*.txt
uv run python social_poster.py --watch

# Debug mode — saves screenshots on failure
uv run python social_poster.py --platform facebook --content "Test" --debug
```

Watch mode file naming:
- `facebook_hello.txt` → posts text to Facebook
- `instagram_promo.txt` + `instagram_promo.jpg` → posts to Instagram (text + image pair required)

Requires: `FACEBOOK_EMAIL`, `FACEBOOK_PASSWORD`, `INSTAGRAM_EMAIL`, `INSTAGRAM_PASSWORD`

---

### `twitter_poster.py`

Posts tweets to Twitter/X using Playwright with **Firefox headless** (harder to detect than Chromium). Handles Twitter's 3-step login flow: email → optional username verify → password. Step screenshots saved to `Logs/` for debugging.

```bash
# Direct tweet (max 280 chars)
uv run python twitter_poster.py --content "Hello, X!"

# Watch mode — monitors Drop_Here/ for twitter_*.txt files
uv run python twitter_poster.py --watch

# Debug mode — saves screenshots on failure
uv run python twitter_poster.py --content "Test" --debug
```

Watch mode: drop `twitter_hello.txt` into `Drop_Here/` → tweets the content → moves to `Done/` or `Needs_Action/`. Files exceeding 280 characters are rejected to `Needs_Action/` without posting.

Requires: `TWITTER_EMAIL`, `TWITTER_PASSWORD`, `TWITTER_USERNAME`

> **Note:** Twitter aggressively rate-limits automated login attempts. If you see "Could not log you in now", wait 60+ minutes before retrying.

---

### `run_claude.sh`

Cron-friendly wrapper that runs `/process-files` non-interactively. Logs all output to `Logs/cron.log` with timestamps.

```bash
# Manual run
bash ai-employee/run_claude.sh

# Cron example (every 5 minutes)
*/5 * * * * GMAIL_APP_PASSWORD=your-pass bash /mnt/c/AI_Employee_Vault/ai-employee/run_claude.sh
```

---

## MCP Servers

### `email-mcp`

Node.js MCP server registered in `.claude/settings.json`. Gives Claude a `send_email` tool that sends replies via Gmail/nodemailer without exposing SMTP credentials directly.

**Tools exposed to Claude:**
- `send_email` — send an email (to, subject, body)

**Config in `.claude/settings.json`:**
```json
{
  "mcpServers": {
    "email-mcp": {
      "command": "node",
      "args": ["/mnt/c/AI_Employee_Vault/mcp-servers/email-mcp/index.js"],
      "env": {
        "GMAIL_USER": "your@gmail.com",
        "GMAIL_APP_PASSWORD": "${GMAIL_APP_PASSWORD}"
      }
    }
  }
}
```

---

### `odoo-mcp`

Node.js MCP server that exposes Odoo CRM/ERP operations as Claude tools. Allows the agent to create leads, log calls, update contacts, and query records without writing Odoo API code manually.

**Tools exposed to Claude:**
- `create_lead` — create a CRM lead/opportunity
- `get_leads` — query leads with filters
- `update_lead` — update lead fields
- `create_contact` — create a new res.partner record
- `get_contacts` — query contacts

Requires: `ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_PASSWORD`

---

## Agent Skills (Slash Commands)

### `/process-files`

The core task-processing loop. Claude reads every file in `Needs_Action/`, checks `Company_Handbook.md` for applicable rules, creates a `Plan.md`, then either:
- **Executes automatically** — if the action is safe (under $500, non-sensitive)
- **Escalates** — moves item to `Pending_Approval/` with a reason

Updates `Dashboard.md` and moves processed files to `Done/`.

```bash
# Interactive
claude "/process-files"

# Non-interactive (cron)
bash ai-employee/run_claude.sh
```

---

### `/create-plan`

Creates a structured `Plan_*.md` file in `Plans/` for a given task. Used by `/process-files` before any action is taken. The plan includes objective, steps, and whether human approval is required.

Plan format:
```markdown
---
created: 2026-02-28T14:00:00
task: Reply to invoice query from Ahmed
status: pending
requires_approval: no
---

## Objective
Reply to Ahmed's email about INV-001...

## Steps
- [ ] Draft professional reply
- [ ] Send via email-mcp
- [ ] Move EMAIL_ file to Done/

## Approval Required?
No — standard email reply, no financial action.
```

---

### `/ceo-briefing`

Generates a full Monday morning CEO briefing. Audits all vault folders, reads `Business_Goals.md` KPIs, calculates weekly stats, identifies bottlenecks, and writes a dated report to `Briefings/YYYY-MM-DD_CEO_Briefing.md`.

```bash
claude "/ceo-briefing"
```

**Report sections:**
- Executive Summary (2–4 sentences, top priority item)
- Weekly Activity Stats (table: emails, files, tasks, pending, backlog)
- Completed This Week (one bullet per item)
- Pending Items — Action Required (with overdue flags)
- Bottlenecks (stalled items, missed runs, backlog pile-ups)
- Proactive Suggestions (3–5 specific, file-referenced recommendations)
- System Health (last run timestamp, last email check, goals on file)

---

## Ralph Wiggum — The Self-Looping Agent

Ralph Wiggum is the Claude Code **Stop hook** defined in `.claude/hooks/stop_hook.py`. Named after the Simpsons character who enthusiastically keeps helping even when things go wrong.

**How it works:**

1. Every time Claude tries to exit, the Stop hook fires.
2. The hook checks `In_Progress/` for any task files.
3. If files exist, it **blocks the exit** and re-injects the `/process-files` prompt with a message listing the pending tasks.
4. Claude resumes, processes the tasks, and tries to exit again.
5. This continues until `In_Progress/` is empty — or until the safety ceiling of **10 iterations** is reached.

```
Claude finishes a task
        │
        ▼
  Stop Hook fires
        │
   In_Progress/ empty? ──YES──► Claude exits cleanly
        │
        NO
        │
   Iteration < 10? ──NO──► Claude exits (safety ceiling)
        │
       YES
        │
   Block exit + re-inject /process-files
        │
   Claude continues working
        │
        └──► (loop)
```

**Log:** Every block decision is written to `Logs/ralph_wiggum.log` with session ID, iteration count, and which task files were found.

**To place a task mid-flight:** Move the task `.md` file from `Needs_Action/` to `In_Progress/` before Claude finishes — Ralph will ensure it gets processed before Claude exits.

---

## Rules of Engagement

Defined in `Company_Handbook.md`:

| Category | Rule |
|----------|------|
| Communication | Always polite and professional; reply within 24 hours |
| Financial | Auto-execute under $500; flag anything over $500 for human approval |
| Planning | Always create a `Plan.md` in `/Plans/` before taking any action |
| Sensitive actions | Route to `Pending_Approval/` — never execute without human sign-off |
| Social media | Only post content explicitly provided; no generated opinions |

---

## Security Notes

- `credentials.json` and `token.pickle` (Gmail OAuth) are in `.gitignore` — never committed
- Browser session files (`sessions/*.json`, `linkedin_session/`) are gitignored — contain auth cookies
- All credentials are environment variables only — no hardcoded secrets anywhere in the codebase
- The `Company_Handbook.md` $500 threshold is the primary financial safety gate
- Ralph Wiggum has a hard ceiling of 10 iterations to prevent infinite loops
- The `--dangerously-skip-permissions` flag in `run_claude.sh` is intentional for non-interactive cron use — mitigated by the Handbook rules and the human approval gate in `Pending_Approval/`
- Twitter login uses Firefox headless + `navigator.webdriver` masking; session is persisted so login only runs once
