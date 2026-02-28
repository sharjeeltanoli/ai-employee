#!/usr/bin/env python3
"""
Twitter/X poster using Playwright.
Supports direct posting and file-watch mode (PollingObserver for WSL compatibility).

Usage:
    python twitter_poster.py --content "Your tweet here"
    python twitter_poster.py --watch
    python twitter_poster.py --content "Tweet" --debug

Watch mode file naming (Drop_Here/):
    twitter_*.txt  → posts tweet text to Twitter/X

Environment variables:
    TWITTER_EMAIL     Login e-mail
    TWITTER_PASSWORD  Password
    TWITTER_USERNAME  Username/handle (used when Twitter asks to confirm identity)

Session file:
    ai-employee/sessions/twitter_session.json
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

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
SESSIONS_PATH = VAULT_PATH / "ai-employee" / "sessions"
WATCH_FOLDER = VAULT_PATH / "Drop_Here"
DONE_FOLDER = VAULT_PATH / "Done"
NEEDS_ACTION_FOLDER = VAULT_PATH / "Needs_Action"

TWITTER_SESSION_FILE = SESSIONS_PATH / "twitter_session.json"
LOGS_PATH = VAULT_PATH / "Logs"

# Firefox is less aggressively fingerprinted by Twitter than headless Chromium.
# Chromium args kept as fallback.
CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-blink-features=AutomationControlled",
]

# Realistic Windows Firefox user-agent
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
    "Gecko/20100101 Firefox/124.0"
)

# Stealth init script — masks common bot-detection properties
_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
window.chrome = {runtime: {}};
"""

# ---------------------------------------------------------------------------
# Browser helpers
# ---------------------------------------------------------------------------


def _launch_browser(playwright):
    """Launch headless Firefox (harder to detect than Chromium) with WSL compatibility."""
    logger.info("Launching Firefox (headless, WSL-compatible)...")
    try:
        return playwright.firefox.launch(headless=True)
    except Exception as exc:
        logger.warning("Firefox launch failed (%s) — falling back to Chromium.", exc)
        return playwright.chromium.launch(headless=True, args=CHROMIUM_ARGS)


def _new_context(browser, session_file: Path):
    """Create a browser context, loading persisted session state if available."""
    kwargs: dict = {
        "user_agent": BROWSER_USER_AGENT,
        "viewport": {"width": 1280, "height": 800},
    }
    if session_file.exists():
        logger.info("Loading saved session from %s", session_file)
        kwargs["storage_state"] = str(session_file)
    else:
        logger.info("No saved session — will authenticate from scratch.")
    context = browser.new_context(**kwargs)
    context.add_init_script(_STEALTH_SCRIPT)
    return context


def _save_screenshot(page, path: Path, label: str):
    """Save a full-page screenshot, creating parent dirs as needed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=True)
        logger.info("Screenshot saved → %s", path)
    except Exception as exc:
        logger.warning("Could not save %s screenshot: %s", label, exc)


def _click_first_visible(page, selectors: list, timeout: int = 8_000) -> bool:
    """Try each selector in order; click the first visible match."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            logger.info("Clicked element via: %s", sel)
            return True
        except PlaywrightTimeoutError:
            logger.debug("Selector timed out: %s", sel)
    return False


# ---------------------------------------------------------------------------
# Twitter login check
# ---------------------------------------------------------------------------


def _tw_is_logged_in(page) -> bool:
    """Return True if the Twitter/X session is authenticated."""
    logger.info("Twitter: checking login status...")
    try:
        page.goto("https://x.com/home", timeout=30_000)
        page.wait_for_load_state("domcontentloaded", timeout=20_000)
        time.sleep(2)

        # Redirected to login page → not authenticated
        if any(k in page.url for k in ("login", "i/flow/login", "signin")):
            logger.info("Twitter: redirected to login — not authenticated.")
            return False

        # Login form present → not authenticated
        if page.query_selector('input[autocomplete="username"]') or \
           page.query_selector('input[name="text"]'):
            logger.info("Twitter: login form detected — not authenticated.")
            return False

        # Authenticated indicators
        for sel in [
            "a[aria-label='Profile']",
            "a[data-testid='AppTabBar_Profile_Link']",
            "div[data-testid='primaryColumn']",
            "a[href='/compose/tweet']",
        ]:
            if page.query_selector(sel):
                logger.info("Twitter: authenticated element found ('%s').", sel)
                return True

        return False

    except Exception as exc:
        logger.warning("Twitter: exception during login check: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Twitter login flow  (email → [username] → password)
# ---------------------------------------------------------------------------


def _tw_login(page, email: str, password: str, username: str) -> bool:
    """
    Log in to Twitter/X.
    Flow: "Phone, email, or username" → Next → (optional username verify) → password → Log in.
    Screenshots are saved at each step to Logs/ for debugging.
    """
    logger.info("Twitter: navigating to login page...")
    page.goto("https://x.com/i/flow/login", timeout=30_000)
    page.wait_for_load_state("domcontentloaded", timeout=20_000)
    time.sleep(3)  # longer initial wait to appear more human

    try:
        # ── Step 1: "Phone, email, or username" field ─────────────────────
        # Twitter renders this as input[autocomplete="username"] or input[name="text"]
        logger.info("Twitter: waiting for email/username field...")
        email_field = None
        for sel in ('input[autocomplete="username"]', 'input[name="text"]'):
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=15_000)
                email_field = loc
                logger.info("Twitter: email field found via '%s'.", sel)
                break
            except PlaywrightTimeoutError:
                pass

        if email_field is None:
            logger.error("Twitter: could not find email/username input field.")
            _save_screenshot(page, LOGS_PATH / "twitter_step1_fail.png", "step1-fail")
            return False

        email_field.click()
        email_field.type(email, delay=50)
        time.sleep(0.5)
        _save_screenshot(page, LOGS_PATH / "twitter_step1_email.png", "step1-email")

        # Click Next using get_by_role for precision
        logger.info("Twitter: clicking Next after email...")
        try:
            next_btn = page.get_by_role("button", name="Next")
            next_btn.wait_for(state="visible", timeout=8_000)
            next_btn.click()
            logger.info("Twitter: Next button clicked.")
        except PlaywrightTimeoutError:
            logger.error("Twitter: Next button not found after email entry.")
            _save_screenshot(page, LOGS_PATH / "twitter_step1_next_fail.png", "step1-next-fail")
            return False
        time.sleep(2)
        _save_screenshot(page, LOGS_PATH / "twitter_step2.png", "step2")

        # Check for Twitter's "Could not log you in" error specifically
        # (not just any toast — normal toasts appear during posting too)
        page_text = page.inner_text("body")
        if "Could not log you in" in page_text or "Try again later" in page_text:
            logger.error(
                "Twitter: 'Could not log you in' error — IP may be rate-limited from "
                "repeated login attempts. Wait 30+ minutes and try again."
            )
            _save_screenshot(page, LOGS_PATH / "twitter_step2_blocked.png", "step2-blocked")
            return False

        # ── Step 2: Optional username/phone verification ──────────────────
        # Twitter shows a dedicated "Enter your phone number or username" screen
        # ONLY when it needs to verify identity. Distinguish it from being sent
        # back to the initial screen (which also has input[name="text"]) by
        # checking for the ocfEnterTextTextInput testid or a heading change.
        pass_visible = False
        try:
            page.locator('input[name="password"]').first.wait_for(state="visible", timeout=3_000)
            pass_visible = True
        except PlaywrightTimeoutError:
            pass

        if not pass_visible:
            logger.info("Twitter: password not yet visible — checking for username prompt...")
            # The genuine username-prompt screen uses data-testid="ocfEnterTextTextInput"
            try:
                loc = page.locator('input[data-testid="ocfEnterTextTextInput"]').first
                loc.wait_for(state="visible", timeout=6_000)
                logger.info("Twitter: username verification prompt detected.")
                loc.click()
                loc.type(username, delay=50)
                time.sleep(0.5)
                _save_screenshot(page, LOGS_PATH / "twitter_step2_username.png", "step2-username")
                try:
                    next_btn2 = page.get_by_role("button", name="Next")
                    next_btn2.wait_for(state="visible", timeout=8_000)
                    next_btn2.click()
                    logger.info("Twitter: Next clicked after username.")
                except PlaywrightTimeoutError:
                    logger.error("Twitter: Next button not found after username entry.")
                    _save_screenshot(page, LOGS_PATH / "twitter_step2_next_fail.png", "step2-next-fail")
                    return False
                time.sleep(2)
            except PlaywrightTimeoutError:
                logger.info("Twitter: no username prompt — proceeding to password step.")

        # ── Step 3: Password ──────────────────────────────────────────────
        logger.info("Twitter: waiting for password field...")
        pass_field = page.locator('input[name="password"]').first
        pass_field.wait_for(state="visible", timeout=15_000)
        pass_field.click()
        pass_field.type(password, delay=50)
        time.sleep(0.5)
        _save_screenshot(page, LOGS_PATH / "twitter_step3_password.png", "step3-password")

        # Click Log in
        logger.info("Twitter: clicking Log in...")
        try:
            login_btn = page.get_by_role("button", name="Log in")
            login_btn.wait_for(state="visible", timeout=8_000)
            login_btn.click()
            logger.info("Twitter: Log in button clicked.")
        except PlaywrightTimeoutError:
            # Fallback to data-testid
            if not _click_first_visible(page, [
                "button[data-testid='LoginForm_Login_Button']",
                "button:has-text('Log in')",
            ]):
                logger.error("Twitter: could not click Log in button.")
                _save_screenshot(page, LOGS_PATH / "twitter_step3_login_fail.png", "step3-login-fail")
                return False

        # Wait for navigation away from login flow
        try:
            page.wait_for_url(lambda url: "login" not in url and "flow" not in url, timeout=20_000)
        except PlaywrightTimeoutError:
            pass
        time.sleep(3)

        _save_screenshot(page, LOGS_PATH / "twitter_step4_postlogin.png", "step4-postlogin")
        logger.info("Twitter: post-login URL: %s", page.url)

        if any(k in page.url for k in ("login", "flow/login")):
            logger.error("Twitter: still on login page — credentials may be wrong.")
            return False

        # Dismiss post-login prompts (notifications, "Turn on alerts", etc.)
        for sel in [
            "button:has-text('Not now')",
            "button:has-text('Skip for now')",
            "div[role='button']:has-text('Not now')",
        ]:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=3_000)
                loc.click()
                logger.info("Twitter: dismissed post-login prompt ('%s').", sel)
                time.sleep(1)
            except PlaywrightTimeoutError:
                pass

        logger.info("Twitter: login successful (URL: %s).", page.url)
        return True

    except PlaywrightTimeoutError as exc:
        logger.error("Twitter: login timed out: %s", exc)
        _save_screenshot(page, LOGS_PATH / "twitter_login_timeout.png", "login-timeout")
        return False


# ---------------------------------------------------------------------------
# Post a tweet
# ---------------------------------------------------------------------------


def _tw_post(page, content: str, debug: bool = False) -> bool:
    """Compose and publish a tweet."""
    logger.info("Twitter: navigating to home...")
    page.goto("https://x.com/home", timeout=30_000)
    page.wait_for_load_state("domcontentloaded", timeout=20_000)
    time.sleep(2)

    try:
        # ── Step 1: Open the compose box ─────────────────────────────────
        logger.info("Twitter: opening tweet composer...")
        opened = _click_first_visible(page, [
            "a[href='/compose/tweet']",
            "a[data-testid='SideNav_NewTweet_Button']",
            "div[aria-label='Tweet'][role='button']",
            "div[aria-label='Post'][role='button']",
        ], timeout=15_000)

        if not opened:
            # The compose box on the home timeline may already be focused
            logger.info("Twitter: trying inline compose box on home feed...")
            opened = _click_first_visible(page, [
                "div[data-testid='tweetTextarea_0']",
                "div[role='textbox'][aria-label='Tweet text']",
                "div[role='textbox'][aria-label='Post text']",
                "div.public-DraftEditor-content",
            ], timeout=10_000)

        if not opened:
            logger.error("Twitter: could not open tweet composer.")
            if debug:
                _save_screenshot(page, LOGS_PATH / "twitter_debug.png", "debug")
            return False

        time.sleep(1)

        # ── Step 2: Find the text editor ─────────────────────────────────
        editor = None
        editor_selectors = [
            "div[data-testid='tweetTextarea_0']",
            "div[role='textbox'][aria-label='Tweet text']",
            "div[role='textbox'][aria-label='Post text']",
            "div[contenteditable='true'][data-testid='tweetTextarea_0']",
            "div[contenteditable='true'][role='textbox']",
        ]

        # Look inside a modal first, then page-wide
        search_contexts = [
            page.locator("div[aria-modal='true']").first,
            page.locator("div[data-testid='modal-container']").first,
            page,
        ]

        for ctx in search_contexts:
            if editor is not None:
                break
            for sel in editor_selectors:
                try:
                    loc = ctx.locator(sel).first
                    loc.wait_for(state="visible", timeout=6_000)
                    editor = loc
                    logger.info("Twitter: editor found via '%s'.", sel)
                    break
                except PlaywrightTimeoutError:
                    pass

        if editor is None:
            logger.error("Twitter: could not locate tweet text editor.")
            if debug:
                _save_screenshot(page, LOGS_PATH / "twitter_debug.png", "debug")
            return False

        editor.click()
        time.sleep(0.5)
        editor.type(content, delay=30)
        logger.info("Twitter: content typed (%d chars).", len(content))
        time.sleep(1)

        # Before-post screenshot
        _save_screenshot(page, LOGS_PATH / "twitter_before_post.png", "before-post")

        # ── Step 3: Click the Post/Tweet button ───────────────────────────
        # Scope to modal if present; button name changed from "Tweet" to "Post" in 2023
        modal = page.locator("div[aria-modal='true']").first
        submitted = False

        for btn_name in ("Post", "Tweet"):
            for ctx in (modal, page):
                try:
                    btn = ctx.get_by_role("button", name=btn_name, exact=True)
                    btn.wait_for(state="visible", timeout=5_000)
                    btn.click()
                    logger.info("Twitter: submit button clicked (name='%s').", btn_name)
                    submitted = True
                    break
                except PlaywrightTimeoutError:
                    pass
            if submitted:
                break

        # Fallback: data-testid
        if not submitted:
            for sel in [
                "button[data-testid='tweetButtonInline']",
                "button[data-testid='tweetButton']",
                "div[data-testid='tweetButtonInline']",
            ]:
                try:
                    loc = page.locator(sel).first
                    loc.wait_for(state="visible", timeout=5_000)
                    loc.click()
                    logger.info("Twitter: submit button clicked via '%s'.", sel)
                    submitted = True
                    break
                except PlaywrightTimeoutError:
                    pass

        if not submitted:
            logger.error("Twitter: could not find Post/Tweet submit button.")
            if debug:
                _save_screenshot(page, LOGS_PATH / "twitter_debug.png", "debug")
            return False

        # ── Step 4: Verify tweet appeared ────────────────────────────────
        time.sleep(5)
        logger.info("Twitter: reloading home to verify tweet...")
        page.goto("https://x.com/home", timeout=30_000)
        page.wait_for_load_state("domcontentloaded", timeout=20_000)
        time.sleep(3)

        _save_screenshot(page, LOGS_PATH / "twitter_after_post.png", "after-post")

        # Check feed for our content
        try:
            page.wait_for_selector(f"text={content[:40]}", timeout=8_000)
            logger.info("Twitter: tweet verified — content found on home timeline.")
        except PlaywrightTimeoutError:
            logger.warning(
                "Twitter: tweet text not found on home timeline — "
                "may still have posted (check twitter_after_post.png)."
            )

        logger.info("Twitter: tweet posted successfully.")
        return True

    except PlaywrightTimeoutError as exc:
        logger.error("Twitter: timeout during posting: %s", exc)
        if debug:
            _save_screenshot(page, LOGS_PATH / "twitter_debug.png", "debug")
        return False
    except Exception as exc:
        logger.error("Twitter: unexpected error during posting: %s", exc)
        if debug:
            _save_screenshot(page, LOGS_PATH / "twitter_debug.png", "debug")
        return False


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def run_twitter_post(content: str, debug: bool = False) -> bool:
    """Authenticate (reusing session if valid) and post a tweet. Returns True on success."""
    email = os.environ.get("TWITTER_EMAIL")
    password = os.environ.get("TWITTER_PASSWORD")
    username = os.environ.get("TWITTER_USERNAME", "")

    if not email or not password:
        logger.error("TWITTER_EMAIL and TWITTER_PASSWORD environment variables must be set.")
        return False

    if len(content) > 280:
        logger.error("Tweet exceeds 280 characters (%d).", len(content))
        return False

    SESSIONS_PATH.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = _launch_browser(p)
        context = _new_context(browser, TWITTER_SESSION_FILE)
        page = context.new_page()
        try:
            if not _tw_is_logged_in(page):
                logger.info("Twitter: session invalid — logging in...")
                if not _tw_login(page, email, password, username):
                    logger.error("Twitter: authentication failed.")
                    if debug:
                        _save_screenshot(page, LOGS_PATH / "twitter_debug.png", "debug")
                    return False
                context.storage_state(path=str(TWITTER_SESSION_FILE))
                logger.info("Twitter: new session saved to %s.", TWITTER_SESSION_FILE)

            success = _tw_post(page, content, debug=debug)

            if success:
                context.storage_state(path=str(TWITTER_SESSION_FILE))
                logger.info("Twitter: session refreshed and saved.")
            return success

        except Exception as exc:
            logger.error("Twitter: unhandled exception: %s", exc)
            return False
        finally:
            context.close()
            browser.close()
            logger.info("Twitter: browser closed.")


# ---------------------------------------------------------------------------
# File-watch mode  (PollingObserver — WSL inotify-safe)
# ---------------------------------------------------------------------------


class TwitterFileHandler(FileSystemEventHandler):
    """
    Watches Drop_Here/ for twitter_*.txt files and posts them as tweets.
    On success: moves file to Done/
    On failure: moves file to Needs_Action/
    """

    def __init__(self, debug: bool = False):
        self.debug = debug

    def on_created(self, event):
        if event.is_directory:
            return
        src = Path(event.src_path)
        if src.suffix.lower() != ".txt" or not src.name.lower().startswith("twitter_"):
            return
        self._handle(src)

    def _handle(self, src: Path):
        logger.info("Watch: Twitter file detected — %s", src.name)
        time.sleep(0.5)  # let the OS finish writing

        try:
            content = src.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.error("Watch: could not read %s: %s", src.name, exc)
            return

        if not content:
            logger.warning("Watch: %s is empty — skipping.", src.name)
            return

        if len(content) > 280:
            logger.error(
                "Watch: %s exceeds 280 characters (%d) — moving to Needs_Action/.",
                src.name, len(content),
            )
            self._move(src, success=False)
            return

        success = run_twitter_post(content, debug=self.debug)
        self._move(src, success)

    def _move(self, src: Path, success: bool):
        dest_folder = DONE_FOLDER if success else NEEDS_ACTION_FOLDER
        dest_folder.mkdir(parents=True, exist_ok=True)
        dest = dest_folder / src.name
        try:
            src.rename(dest)
            logger.info(
                "Watch: %s moved to %s/ (%s).",
                src.name, dest_folder.name, "success" if success else "failed",
            )
        except Exception as exc:
            logger.error("Watch: could not move %s: %s", src.name, exc)


def watch_mode(debug: bool = False):
    """Start PollingObserver watching Drop_Here/ for twitter_*.txt files."""
    WATCH_FOLDER.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Watch mode active. Monitoring: %s\n"
        "  twitter_*.txt  → tweet the file contents (max 280 chars)",
        WATCH_FOLDER,
    )

    handler = TwitterFileHandler(debug=debug)
    observer = PollingObserver()
    observer.schedule(handler, str(WATCH_FOLDER), recursive=False)
    observer.start()
    logger.info("PollingObserver started (WSL-compatible polling mode).")

    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("Watch mode: stopping...")
        observer.stop()
    observer.join()
    logger.info("Watch mode: stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Post tweets to Twitter/X via Playwright.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Post a tweet directly
  python twitter_poster.py --content "Hello, X!"

  # Watch Drop_Here/ and post automatically
  python twitter_poster.py --watch

  # Debug mode (saves screenshots on failure)
  python twitter_poster.py --content "Hello" --debug

Watch mode file naming (drop into Drop_Here/):
  twitter_*.txt   → posted as a tweet (max 280 chars)

Environment variables:
  TWITTER_EMAIL     Login e-mail
  TWITTER_PASSWORD  Password
  TWITTER_USERNAME  Username/handle (needed if Twitter asks to verify identity)

Session file (reused across runs):
  ai-employee/sessions/twitter_session.json
        """,
    )
    parser.add_argument(
        "--content",
        help="Tweet text to post (max 280 characters).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch Drop_Here/ for twitter_*.txt files and post them automatically.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save debug screenshot to Logs/twitter_debug.png on failure.",
    )
    args = parser.parse_args()

    if args.watch:
        watch_mode(debug=args.debug)
    elif args.content:
        ok = run_twitter_post(args.content, debug=args.debug)
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
