#!/usr/bin/env python3
"""
LinkedIn automation script using Playwright.
Posts text updates to LinkedIn with session persistence.
Supports direct CLI posting and file-watch mode (PollingObserver for WSL compatibility).

Usage:
    python linkedin_poster.py "Your post content here"
    python linkedin_poster.py --watch   # watches Drop_Here for .txt files to post
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
VAULT_PATH = Path("/mnt/c/AI_Employee_Vault")
SESSION_PATH = VAULT_PATH / "ai-employee" / "linkedin_session"
SESSION_FILE = SESSION_PATH / "session.json"
WATCH_FOLDER = VAULT_PATH / "Drop_Here"
DONE_FOLDER = VAULT_PATH / "Done"


# ---------------------------------------------------------------------------
# LinkedIn helpers
# ---------------------------------------------------------------------------

def _is_logged_in(page) -> bool:
    """Return True if the current browser context is authenticated."""
    logger.info("Checking login status...")
    try:
        page.goto("https://www.linkedin.com/feed/", timeout=30_000)
        page.wait_for_load_state("domcontentloaded", timeout=20_000)

        if "/login" in page.url or "/checkpoint" in page.url:
            logger.info("Not logged in — redirect detected: %s", page.url)
            return False

        # Primary: look for well-known nav / identity elements
        if page.query_selector(
            "div.feed-identity-module, "
            "[data-control-name='nav.settings'], "
            ".global-nav__me, "
            ".global-nav__primary-link, "
            "nav.global-nav"
        ):
            logger.info("Session is valid — nav element found.")
            return True

        # Fallback: if we landed on /feed/ without a redirect, trust the URL.
        # LinkedIn sometimes lazy-loads nav elements; an absent selector does
        # not mean we are logged out.
        if "linkedin.com/feed" in page.url:
            logger.info("Session appears valid — on feed URL with no login redirect.")
            return True

        logger.info("Could not confirm login state; will re-authenticate.")
        return False

    except Exception as exc:
        logger.warning("Exception while checking login: %s", exc)
        return False


def _login(page, email: str, password: str) -> bool:
    """Log in to LinkedIn with provided credentials."""
    logger.info("Navigating to LinkedIn login page...")
    page.goto("https://www.linkedin.com/login", timeout=30_000)
    page.wait_for_load_state("domcontentloaded", timeout=20_000)

    try:
        logger.info("Entering email...")
        page.fill("#username", email)

        logger.info("Entering password...")
        page.fill("#password", password)

        logger.info("Submitting login form...")
        page.click("button[type='submit']")

        # LinkedIn may redirect to feed or a verification checkpoint
        page.wait_for_url("**linkedin.com/**", timeout=30_000)
        time.sleep(2)  # Let the page settle

        if "/login" in page.url:
            logger.error("Still on login page — credentials may be wrong.")
            return False

        if "/checkpoint" in page.url or "/challenge" in page.url:
            logger.warning(
                "LinkedIn requires additional verification (2FA / CAPTCHA). "
                "Complete it manually then re-run this script — session will be saved."
            )
            # Give manual intervention time
            time.sleep(60)

        page.wait_for_url("**/feed/**", timeout=60_000)
        logger.info("Login successful.")
        return True

    except PlaywrightTimeoutError as exc:
        logger.error("Login timed out: %s", exc)
        return False


def _click_first_visible(page, selectors: list[str], timeout: int = 30_000) -> bool:
    """
    Try each selector in order; click the first one that becomes visible.
    Returns True if a match was clicked, False if all selectors timed out.
    """
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            logger.info("Clicked element via selector: %s", sel)
            return True
        except PlaywrightTimeoutError:
            logger.debug("Selector timed out, trying next: %s", sel)
    return False


def _post(page, content: str) -> bool:
    """Submit a text post on LinkedIn."""
    logger.info("Navigating to feed for posting...")
    page.goto("https://www.linkedin.com/feed/", timeout=30_000)
    # "networkidle" never fires on LinkedIn (continuous background polling);
    # "domcontentloaded" is sufficient to have the share box rendered.
    page.wait_for_load_state("domcontentloaded", timeout=30_000)

    try:
        # ---- Open the share dialog ----
        # LinkedIn periodically renames these selectors; try all known variants.
        logger.info("Looking for 'Start a post' trigger...")
        start_selectors = [
            "button.share-box-feed-entry__trigger",
            "[data-control-name='share.sharebox_create_post_button']",
            "button:has-text('Start a post')",
            ".share-creation-state__button",
            # Newer LinkedIn UI selectors
            "div.share-box-feed-entry__top-bar",
            "div[data-placeholder='Start a post']",
            ".feed-shared-update-v2",
        ]
        if not _click_first_visible(page, start_selectors, timeout=30_000):
            # Last-resort: find any visible element with "Start a post" text
            logger.warning(
                "Named selectors failed — trying text-based fallback for share trigger."
            )
            triggered = False
            for candidate in page.get_by_text("Start a post").all():
                try:
                    if candidate.is_visible():
                        candidate.click()
                        triggered = True
                        logger.info("Clicked 'Start a post' via text fallback.")
                        break
                except Exception:
                    continue
            if not triggered:
                logger.error("Could not find 'Start a post' trigger with any selector.")
                return False
        logger.info("Share dialog opened.")

        # ---- Wait for the editor ----
        editor_selectors = [
            "div.ql-editor[contenteditable='true']",
            "div[data-placeholder='What do you want to talk about?']",
            "div[aria-placeholder*='talk about']",
            "div[aria-label*='Text editor']",
            # Newer LinkedIn editor selectors
            "div[contenteditable='true'][data-placeholder]",
            ".share-creation-state__editor div[contenteditable='true']",
            "div[contenteditable='true']",
        ]
        editor = None
        for sel in editor_selectors:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=30_000)
                editor = loc
                logger.info("Found editor via selector: %s", sel)
                break
            except PlaywrightTimeoutError:
                logger.debug("Editor selector timed out, trying next: %s", sel)

        if editor is None:
            logger.error("Could not find post editor with any known selector.")
            return False

        editor.click()
        logger.info("Typing post content...")
        editor.type(content, delay=30)  # slight delay mimics human typing

        # ---- Click Post ----
        logger.info("Looking for Post submit button...")
        post_btn_selectors = [
            "button.share-actions__primary-action",
            "button[data-control-name='share.post']",
            "button:has-text('Post')",
            ".share-box_actions button[type='submit']",
            "button[aria-label='Post']",
        ]
        if not _click_first_visible(page, post_btn_selectors, timeout=30_000):
            logger.error("Could not find Post submit button with any known selector.")
            return False
        logger.info("Post button clicked.")

        # Wait for dialog to dismiss / confirmation
        time.sleep(4)
        logger.info("Post submitted successfully.")
        return True

    except PlaywrightTimeoutError as exc:
        logger.error("Timeout while posting: %s", exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error while posting: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Core posting flow
# ---------------------------------------------------------------------------

def run_post(content: str) -> bool:
    """
    Authenticate (reusing saved session if available) and publish *content*.
    Returns True on success.
    """
    email = os.environ.get("LINKEDIN_EMAIL")
    password = os.environ.get("LINKEDIN_PASSWORD")

    if not email or not password:
        logger.error(
            "LINKEDIN_EMAIL and LINKEDIN_PASSWORD environment variables must be set."
        )
        return False

    SESSION_PATH.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        logger.info("Launching Chromium (headless, WSL-compatible)...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
            ],
        )

        # Load saved session if it exists
        context_kwargs: dict = {}
        if SESSION_FILE.exists():
            logger.info("Loading saved session from %s", SESSION_FILE)
            context_kwargs["storage_state"] = str(SESSION_FILE)
        else:
            logger.info("No saved session found — will authenticate from scratch.")

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        try:
            if not _is_logged_in(page):
                logger.info("Session invalid or absent — logging in...")
                if not _login(page, email, password):
                    logger.error("Authentication failed. Aborting.")
                    return False

                logger.info("Saving fresh session to %s", SESSION_FILE)
                context.storage_state(path=str(SESSION_FILE))

            success = _post(page, content)

            if success:
                # Refresh stored cookies after a successful post
                context.storage_state(path=str(SESSION_FILE))
                logger.info("Session refreshed and saved.")

            return success

        except Exception as exc:
            logger.error("Unhandled exception in run_post: %s", exc)
            return False

        finally:
            context.close()
            browser.close()
            logger.info("Browser closed.")


# ---------------------------------------------------------------------------
# File-watch mode  (PollingObserver for WSL compatibility)
# ---------------------------------------------------------------------------

class LinkedInPostFileHandler(FileSystemEventHandler):
    """
    Watches Drop_Here for *.txt files whose names start with 'linkedin_'.
    Each file's contents are posted to LinkedIn, then the file is moved to Done/.
    Uses PollingObserver so the watcher works reliably under WSL.
    """

    def on_created(self, event):
        if event.is_directory:
            return

        src = Path(event.src_path)
        if not src.name.lower().startswith("linkedin_") or src.suffix.lower() != ".txt":
            return

        logger.info("LinkedIn post file detected: %s", src.name)
        time.sleep(0.5)  # Let the OS finish writing the file

        try:
            content = src.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.error("Could not read %s: %s", src.name, exc)
            return

        if not content:
            logger.warning("File %s is empty — skipping.", src.name)
            return

        logger.info("Posting content from %s...", src.name)
        success = run_post(content)

        dest_folder = DONE_FOLDER if success else VAULT_PATH / "Needs_Action"
        dest_folder.mkdir(exist_ok=True)
        dest = dest_folder / src.name
        src.rename(dest)
        logger.info(
            "File moved to %s (%s).",
            dest_folder.name,
            "success" if success else "failed",
        )


def watch_mode():
    """Start the PollingObserver to watch Drop_Here for LinkedIn post files."""
    WATCH_FOLDER.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Watch mode active. Drop a file named 'linkedin_*.txt' into %s to post.",
        WATCH_FOLDER,
    )

    handler = LinkedInPostFileHandler()
    observer = PollingObserver()
    observer.schedule(handler, str(WATCH_FOLDER), recursive=False)
    observer.start()
    logger.info("PollingObserver started (WSL-compatible polling mode).")

    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("Stopping watcher...")
        observer.stop()
    observer.join()
    logger.info("Watcher stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Post a text update to LinkedIn via Playwright.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python linkedin_poster.py "Hello LinkedIn world!"
  python linkedin_poster.py --watch

Environment variables required (unless --watch is also used implicitly):
  LINKEDIN_EMAIL      Your LinkedIn login e-mail
  LINKEDIN_PASSWORD   Your LinkedIn password

Session storage:
  %(session)s
        """ % {"session": SESSION_FILE},
    )
    parser.add_argument(
        "content",
        nargs="?",
        help="Text content to post. Required unless --watch is given.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help=(
            "Watch Drop_Here/ for files named linkedin_*.txt and post their "
            "contents automatically (PollingObserver — WSL-compatible)."
        ),
    )
    args = parser.parse_args()

    if args.watch:
        watch_mode()
    elif args.content:
        ok = run_post(args.content)
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
