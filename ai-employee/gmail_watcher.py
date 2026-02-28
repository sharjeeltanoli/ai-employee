import imaplib
import email
import time
import logging
from pathlib import Path
from datetime import datetime
import os

from audit_logger import audit_success, audit_failure

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

ACTOR = "gmail_watcher"

VAULT_PATH = Path("/mnt/c/AI_Employee_Vault")
NEEDS_ACTION = VAULT_PATH / "Needs_Action"
GMAIL_USER = "sharjeeel4@gmail.com"
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# Track processed emails in a file so they persist between restarts
PROCESSED_FILE = Path("/mnt/c/AI_Employee_Vault/ai-employee/processed_emails.txt")

def load_processed():
    if PROCESSED_FILE.exists():
        return set(PROCESSED_FILE.read_text().splitlines())
    return set()

def save_processed(processed_ids):
    PROCESSED_FILE.write_text("\n".join(processed_ids))

def create_action_file(sender, subject, body, eid):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = NEEDS_ACTION / f"EMAIL_{timestamp}_{eid.decode()}.md"
    filepath.write_text(f"""---
type: email
from: {sender}
subject: {subject}
received: {datetime.now().isoformat()}
status: pending
---

## Email Received

- **From:** {sender}
- **Subject:** {subject}
- **Preview:** {body[:300]}

## Suggested Actions
- [ ] Read and understand the email
- [ ] Draft a reply if needed
- [ ] Move to /Done when processed
""")
    logger.info(f"Action file created: {filepath.name}")
    audit_success(
        "email_received",
        actor=ACTOR,
        target=filepath.name,
        parameters={
            "from": sender,
            "subject": subject,
            "email_id": eid.decode(),
            "preview_chars": len(body),
        },
    )

def main():
    logger.info("Starting Gmail Watcher...")
    
    if not GMAIL_APP_PASSWORD:
        logger.error("GMAIL_APP_PASSWORD not set!")
        return

    processed_ids = load_processed()
    logger.info(f"Already processed: {len(processed_ids)} emails")

    while True:
        try:
            mail = imaplib.IMAP4_SSL('imap.gmail.com')
            mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            mail.select('inbox')

            _, messages = mail.search(None, 'UNSEEN')
            email_ids = messages[0].split()

            # Only process latest 5 unread emails
            new_emails = [eid for eid in email_ids if eid.decode() not in processed_ids][-5:]

            if new_emails:
                logger.info(f"Processing {len(new_emails)} new emails...")
                for eid in new_emails:
                    _, msg_data = mail.fetch(eid, '(RFC822)')
                    msg = email.message_from_bytes(msg_data[0][1])

                    sender = msg.get('From', 'Unknown')
                    subject = msg.get('Subject', 'No Subject')

                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode(errors='ignore')
                                break
                    else:
                        body = msg.get_payload(decode=True).decode(errors='ignore')

                    create_action_file(sender, subject, body, eid)
                    processed_ids.add(eid.decode())

                save_processed(processed_ids)
            else:
                logger.info("No new emails. Checking again in 2 minutes...")

            mail.logout()
            time.sleep(120)

        except Exception as e:
            logger.error(f"Error: {e}")
            audit_failure(
                "email_poll",
                actor=ACTOR,
                target="imap.gmail.com",
                detail=str(e),
            )
            time.sleep(30)

if __name__ == "__main__":
    main()
