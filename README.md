# AI Employee

An autonomous AI assistant that monitors inboxes, processes incoming tasks, posts to LinkedIn, and manages a structured work vault — all governed by a human-readable rulebook.

---

## How it works

```
Inbox / Drop_Here
       │
       ▼
  gmail_watcher.py          ← polls Gmail every 2 min via IMAP
  filesystem_watcher.py     ← watches Drop_Here/ for dropped files
       │
       ▼
  /Needs_Action/            ← each item becomes a .md task file
       │
       ▼
  Claude Code (/process-files)
    • reads Company_Handbook.md rules
    • creates a Plan.md in /Plans/
    • auto-executes safe actions (< $500, non-sensitive)
    • routes sensitive actions → /Pending_Approval/
       │
       ▼
  /Done/ or /Pending_Approval/
       │
       ▼
  Dashboard.md              ← running activity log
```

---

## Repository layout

```
AI_Employee_Vault/
├── ai-employee/            # Python automation code (own git repo)
│   ├── gmail_watcher.py    # IMAP poller — writes .md files to /Needs_Action
│   ├── filesystem_watcher.py  # Drop_Here watcher (PollingObserver, WSL-safe)
│   ├── linkedin_poster.py  # Playwright-based LinkedIn posting with session reuse
│   ├── auth_gmail.py       # One-time OAuth flow for Gmail API credentials
│   ├── run_claude.sh       # Cron-friendly wrapper that runs /process-files
│   └── pyproject.toml      # uv project — Python 3.11+
│
├── mcp-servers/
│   └── email-mcp/          # Node.js MCP server (nodemailer + MCP SDK)
│
├── .claude/
│   └── commands/
│       ├── process-files.md  # /process-files skill definition
│       └── create-plan.md    # /create-plan skill definition
│
├── Company_Handbook.md     # Rules of engagement (the AI's policy document)
├── Dashboard.md            # Live activity log updated after every run
│
├── Needs_Action/           # Incoming task files (auto-generated .md)
├── Pending_Approval/       # Actions awaiting human sign-off
├── Approved/               # Human-approved items ready to execute
├── Done/                   # Completed tasks archive
├── Drop_Here/              # Drop any file here to trigger the watcher
├── Plans/                  # Auto-generated Plan.md files
└── Logs/                   # Cron run logs
```

---

## Setup

### Prerequisites

- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Node.js 18+ (for the email MCP server)
- [Claude Code](https://claude.ai/code) CLI
- Playwright Chromium (`uv run playwright install chromium`)

### 1. Clone and install

```bash
git clone <repo-url>
cd AI_Employee_Vault/ai-employee
uv sync
uv run playwright install chromium
```

### 2. Set environment variables

```bash
export GMAIL_APP_PASSWORD="your-gmail-app-password"
export LINKEDIN_EMAIL="your@email.com"
export LINKEDIN_PASSWORD="your-linkedin-password"
```

> Add these to your shell profile or a `.env` file (never commit the `.env` file).

### 3. Gmail credentials (one-time OAuth)

Place your Google Cloud OAuth `credentials.json` in `ai-employee/`, then run:

```bash
cd ai-employee
uv run python auth_gmail.py
```

Follow the printed URL to authorise, paste the code back. A `token.pickle` is saved for future runs.

### 4. Start the watchers

```bash
# Terminal 1 — watch Gmail
uv run python gmail_watcher.py

# Terminal 2 — watch Drop_Here folder
uv run python filesystem_watcher.py
```

### 5. Run Claude to process tasks

```bash
# Interactive
claude "/process-files"

# Non-interactive (cron)
bash ai-employee/run_claude.sh
```

### 6. Post to LinkedIn

```bash
# One-off post
uv run python linkedin_poster.py "Your post text here"

# Watch Drop_Here for linkedin_*.txt files
uv run python linkedin_poster.py --watch
```

---

## Rules of engagement

Defined in [`Company_Handbook.md`](Company_Handbook.md):

| Rule | Detail |
|------|--------|
| Communication | Always polite and professional; reply within 24 h |
| Financial | Flag any payment over $500 for human approval |
| Actions | Always create a Plan.md before acting |
| Sensitive actions | Require human approval via /Pending_Approval |

---

## Vault workflow

1. **Incoming** — emails land in `/Needs_Action/` as structured `.md` files
2. **Plan** — Claude creates a `Plan.md` in `/Plans/` before touching anything
3. **Execute or escalate** — safe actions run automatically; anything sensitive waits in `/Pending_Approval/`
4. **Archive** — completed items move to `/Done/`; the `Dashboard.md` is updated

---

## Security notes

- `credentials.json` and `token.pickle` are excluded from git (see `.gitignore`)
- LinkedIn session cookies are stored locally in `linkedin_session/` and excluded from git
- Never commit `.env` files or any file containing passwords or API keys
- The `Company_Handbook.md` payment threshold ($500) is the primary financial safety gate
