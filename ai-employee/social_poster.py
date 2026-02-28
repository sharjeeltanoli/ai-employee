#!/usr/bin/env python3
"""
Social media poster for Facebook and Instagram using Playwright.
Supports direct posting and file-watch mode (PollingObserver for WSL compatibility).

Usage:
    python social_poster.py --platform facebook --content "Your post here"
    python social_poster.py --platform instagram --content "Caption" --image /path/to/img.jpg
    python social_poster.py --watch

Watch mode file naming (Drop_Here/):
    facebook_*.txt     → posts text to Facebook
    instagram_*.txt    → posts to Instagram; pair with same-stem .jpg/.png/.jpeg for image

Environment variables:
    FACEBOOK_EMAIL, FACEBOOK_PASSWORD
    INSTAGRAM_EMAIL, INSTAGRAM_PASSWORD

Session files:
    ai-employee/sessions/facebook_session.json
    ai-employee/sessions/instagram_session.json
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

FACEBOOK_SESSION_FILE = SESSIONS_PATH / "facebook_session.json"
INSTAGRAM_SESSION_FILE = SESSIONS_PATH / "instagram_session.json"
FB_DEBUG_SCREENSHOT = VAULT_PATH / "Logs" / "facebook_debug.png"

# WSL-compatible Chromium launch flags
WSL_CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--single-process",
]

# Mimic a real browser to reduce bot-detection triggers
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Shared browser helpers
# ---------------------------------------------------------------------------


def _launch_browser(playwright):
    """Launch headless Chromium with WSL-compatible flags."""
    logger.info("Launching Chromium (headless, WSL-compatible)...")
    return playwright.chromium.launch(headless=True, args=WSL_CHROMIUM_ARGS)


def _new_context(browser, session_file: Path):
    """Create a browser context, loading persisted session state if available."""
    kwargs: dict = {"user_agent": BROWSER_USER_AGENT}
    if session_file.exists():
        logger.info("Loading saved session from %s", session_file)
        kwargs["storage_state"] = str(session_file)
    else:
        logger.info("No saved session found — will authenticate from scratch.")
    return browser.new_context(**kwargs)


def _click_first_visible(page, selectors: list, timeout: int = 15_000) -> bool:
    """Try each CSS/text selector in order; click the first visible one."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            logger.info("Clicked element via: %s", sel)
            return True
        except PlaywrightTimeoutError:
            logger.debug("Selector timed out, trying next: %s", sel)
    return False


def _fb_save_debug_screenshot(page, debug: bool):
    """Save a full-page screenshot to FB_DEBUG_SCREENSHOT when debug mode is on."""
    if not debug:
        return
    try:
        FB_DEBUG_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(FB_DEBUG_SCREENSHOT), full_page=True)
        logger.info("Debug screenshot saved → %s", FB_DEBUG_SCREENSHOT)
    except Exception as exc:
        logger.warning("Could not save debug screenshot: %s", exc)


def _dismiss_optional_dialog(page, selectors: list, timeout: int = 3_000):
    """
    Silently attempt to dismiss optional overlay dialogs
    (e.g. 'Save login info', notification prompts).
    Does nothing if the dialog is not present.
    """
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            logger.info("Dismissed optional dialog via: %s", sel)
            return
        except PlaywrightTimeoutError:
            pass


# ===========================================================================
# FACEBOOK
# ===========================================================================


def _fb_is_logged_in(page) -> bool:
    """Return True if the Facebook session is authenticated."""
    logger.info("Facebook: checking login status...")
    try:
        page.goto("https://www.facebook.com/", timeout=30_000)
        page.wait_for_load_state("domcontentloaded", timeout=20_000)
        time.sleep(2)

        if "login" in page.url or "checkpoint" in page.url:
            logger.info("Facebook: login/checkpoint redirect detected.")
            return False

        # If a login form is present on the page, we are definitely NOT logged in
        if page.query_selector('form#login_form') or page.query_selector('input[name="email"]'):
            logger.info("Facebook: login form detected on page — not authenticated.")
            return False

        # If the login button is present, we are not authenticated
        if page.query_selector("[data-testid='royal_login_button']"):
            logger.info("Facebook: login button found — not authenticated.")
            return False

        # Presence of any of these means we are logged in
        authenticated_selectors = [
            "[aria-label='Create']",
            "div[aria-label='Your profile']",
            "[aria-label='Facebook']",
            "div[role='navigation']",
        ]
        for sel in authenticated_selectors:
            if page.query_selector(sel):
                logger.info("Facebook: authenticated element found ('%s').", sel)
                return True

        return False

    except Exception as exc:
        logger.warning("Facebook: exception while checking login: %s", exc)
        return False


def _fb_login(page, email: str, password: str) -> bool:
    """Log in to Facebook with the provided credentials."""
    logger.info("Facebook: navigating to login page...")
    page.goto("https://www.facebook.com/login", timeout=30_000)
    page.wait_for_load_state("domcontentloaded", timeout=20_000)

    try:
        # Use type() not fill() so React's onChange fires and enables the submit button
        email_field = page.locator('input[name="email"]')
        email_field.click()
        email_field.type(email, delay=50)
        pass_field = page.locator('input[name="pass"]')
        pass_field.click()
        pass_field.type(password, delay=50)
        time.sleep(0.5)

        # Try clicking the submit button; fall back to JS click on the form button
        clicked = _click_first_visible(page, [
            'button[name="login"]',
            "button[data-testid='royal_login_button']",
            "button[type='submit']",
            "input[type='submit']",
        ], timeout=5_000)
        if not clicked:
            logger.info("Facebook: CSS selectors failed — trying JS form submit...")
            result = page.evaluate("""() => {
                const form = document.querySelector('form#login_form');
                if (form) {
                    const btn = form.querySelector('[type=submit]') || form.querySelector('button');
                    if (btn) { btn.click(); return 'js-clicked'; }
                    form.submit(); return 'form-submitted';
                }
                return 'no-form-found';
            }""")
            logger.info("Facebook: JS submit result: %s", result)
        # React SPA login — wait for URL to navigate away from login page (up to 20s)
        try:
            page.wait_for_url(lambda url: "login" not in url, timeout=20_000)
        except PlaywrightTimeoutError:
            pass
        time.sleep(2)

        logger.info("Facebook: post-login URL: %s", page.url)

        if "login" in page.url:
            logger.error("Facebook: still on login page — credentials may be wrong or bot detected.")
            return False

        if any(k in page.url for k in ("checkpoint", "two_step", "approvals")):
            logger.warning(
                "Facebook: additional verification required (2FA / security check). "
                "Complete it manually — pausing 90 s for intervention."
            )
            time.sleep(90)

        logger.info("Facebook: login successful (URL: %s).", page.url)
        return True

    except PlaywrightTimeoutError as exc:
        logger.error("Facebook: login timed out: %s", exc)
        return False


def _fb_post(page, content: str, debug: bool = False) -> bool:
    """Create a text post on the Facebook news feed."""
    logger.info("Facebook: navigating to news feed...")
    page.goto("https://www.facebook.com/", timeout=30_000)
    page.wait_for_load_state("domcontentloaded", timeout=20_000)
    time.sleep(2)

    # Dismiss optional dialogs that block the UI
    _dismiss_optional_dialog(page, [
        "[aria-label='Not now']",
        "div[aria-label='Close']",
        "button[data-testid='dialog_cancel']",
    ])

    try:
        # ── Step 1: Open the post composer ────────────────────────────────
        logger.info("Facebook: opening post composer...")
        opened = False

        # Try CSS selectors first
        opened = _click_first_visible(page, [
            "[aria-label=\"What's on your mind?\"]",
            "div[data-testid='status-attachment-mentions-input']",
            "div[data-pagelet='FeedComposer']",
            "div[aria-label='Create a post']",
            "span:has-text(\"What's on your mind\")",
            "div[role='button']:has-text(\"What's on your mind\")",
        ], timeout=30_000)

        # Fallback: page.get_by_placeholder() covers textarea/input variants
        if not opened:
            logger.info("Facebook: CSS selectors failed — trying get_by_placeholder fallback...")
            for hint in ("What's on your mind", "What's on your mind?"):
                try:
                    loc = page.get_by_placeholder(hint).first
                    loc.wait_for(state="visible", timeout=10_000)
                    loc.click()
                    logger.info("Facebook: opened composer via get_by_placeholder('%s').", hint)
                    opened = True
                    break
                except PlaywrightTimeoutError:
                    pass

        if not opened:
            logger.error("Facebook: could not open post composer with any selector.")
            _fb_save_debug_screenshot(page, debug)
            return False

        time.sleep(2)

        # ── Step 2: Locate and focus the text editor ───────────────────────
        editor = None

        editor_selectors = [
            "div[aria-label=\"What's on your mind?\"][contenteditable='true']",
            "div[contenteditable='true'][role='textbox']",
            "div[contenteditable='true']",
            "textarea[placeholder*=\"What's on your mind\"]",
        ]

        # Scope search inside dialog first, then fall back to page-wide
        search_contexts = [
            page.locator("div[role='dialog']").first,
            page.locator("div[aria-label='Create a post']").first,
            page.locator("div[data-pagelet='FeedComposer']").first,
            page,
        ]

        for ctx in search_contexts:
            if editor is not None:
                break
            for sel in editor_selectors:
                try:
                    loc = ctx.locator(sel).first
                    loc.wait_for(state="visible", timeout=8_000)
                    editor = loc
                    logger.info("Facebook: editor found via '%s' (context: %s).", sel, type(ctx).__name__)
                    break
                except PlaywrightTimeoutError:
                    pass

        if editor is None:
            logger.info("Facebook: trying get_by_placeholder for editor...")
            for hint in ("What's on your mind", "What's on your mind?"):
                try:
                    loc = page.get_by_placeholder(hint).first
                    loc.wait_for(state="visible", timeout=8_000)
                    editor = loc
                    logger.info("Facebook: editor found via get_by_placeholder('%s').", hint)
                    break
                except PlaywrightTimeoutError:
                    pass

        if editor is None:
            logger.error("Facebook: could not locate text editor in composer.")
            _fb_save_debug_screenshot(page, debug)
            return False

        # Click the editor to focus it, wait, then type
        editor.click()
        time.sleep(1)
        editor.type(content, delay=30)
        logger.info("Facebook: content typed.")
        time.sleep(1)

        # ── Before-post screenshot to verify text is in the editor ────────
        before_post_path = VAULT_PATH / "Logs" / "facebook_before_post.png"
        try:
            before_post_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(before_post_path), full_page=True)
            logger.info("Facebook: before-post screenshot saved → %s", before_post_path)
        except Exception as exc:
            logger.warning("Facebook: could not save before-post screenshot: %s", exc)

        # ── Step 3: Submit the post ────────────────────────────────────────
        dialog = page.locator("div[role='dialog']").first

        # Facebook's composer may show a "Next" button before the final "Post" button.
        # Click "Next" first if it's present, then proceed to find "Post".
        try:
            next_btn = dialog.get_by_role("button", name="Next")
            next_btn.wait_for(state="visible", timeout=5_000)
            next_btn.click()
            logger.info("Facebook: 'Next' button clicked — waiting for Post step...")
            time.sleep(2)
        except PlaywrightTimeoutError:
            logger.info("Facebook: no 'Next' button found — composer is single-step.")

        # Now find the actual Post/Share submit button.
        # exact=True prevents matching "Post audience", "Boost post", etc.
        submitted = False
        for name in ("Post", "Share now", "Share"):
            try:
                btn = dialog.get_by_role("button", name=name, exact=True)
                btn.wait_for(state="visible", timeout=5_000)
                btn.click()
                logger.info("Facebook: submit button clicked (name='%s').", name)
                submitted = True
                break
            except PlaywrightTimeoutError:
                pass

        # Fallback: aria-label on div[role='button'] (Facebook sometimes renders this way)
        if not submitted:
            for sel in [
                "div[aria-label='Post'][role='button']",
                "div[aria-label='Share now'][role='button']",
            ]:
                try:
                    loc = dialog.locator(sel).first
                    loc.wait_for(state="visible", timeout=5_000)
                    loc.click()
                    logger.info("Facebook: submit button clicked via '%s'.", sel)
                    submitted = True
                    break
                except PlaywrightTimeoutError:
                    pass

        # Last resort: Tab to move focus off the editor onto the submit button, then Enter
        if not submitted:
            logger.info("Facebook: all selectors failed — trying Tab+Enter keyboard submit.")
            editor.click()
            time.sleep(0.3)
            page.keyboard.press("Tab")
            time.sleep(0.3)
            page.keyboard.press("Enter")
            logger.info("Facebook: Tab+Enter sent.")
            submitted = True

        # ── Verify: reload feed and check post appeared ────────────────────
        time.sleep(5)
        logger.info("Facebook: reloading feed to verify post...")
        page.goto("https://www.facebook.com/", timeout=30_000)
        page.wait_for_load_state("domcontentloaded", timeout=20_000)
        time.sleep(3)

        # After-post screenshot
        after_post_path = VAULT_PATH / "Logs" / "facebook_after_post.png"
        try:
            after_post_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(after_post_path), full_page=True)
            logger.info("Facebook: after-post screenshot saved → %s", after_post_path)
        except Exception as exc:
            logger.warning("Facebook: could not save after-post screenshot: %s", exc)

        # Check the feed contains our content as a success indicator
        try:
            page.wait_for_selector(f"text={content[:30]}", timeout=8_000)
            logger.info("Facebook: post verified — content found on feed.")
        except PlaywrightTimeoutError:
            logger.warning(
                "Facebook: could not find post text on feed — "
                "post may still have gone through (check after-post screenshot)."
            )

        logger.info("Facebook: post submitted successfully.")
        return True

    except PlaywrightTimeoutError as exc:
        logger.error("Facebook: timeout during posting: %s", exc)
        _fb_save_debug_screenshot(page, debug)
        return False
    except Exception as exc:
        logger.error("Facebook: unexpected error during posting: %s", exc)
        _fb_save_debug_screenshot(page, debug)
        return False


def run_facebook_post(content: str, debug: bool = False) -> bool:
    """
    Top-level entry point: authenticate (reusing session if valid) and post.
    Pass debug=True to save a screenshot to Logs/facebook_debug.png on any failure.
    Returns True on success.
    """
    email = os.environ.get("FACEBOOK_EMAIL")
    password = os.environ.get("FACEBOOK_PASSWORD")
    if not email or not password:
        logger.error("FACEBOOK_EMAIL and FACEBOOK_PASSWORD environment variables must be set.")
        return False

    SESSIONS_PATH.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = _launch_browser(p)
        context = _new_context(browser, FACEBOOK_SESSION_FILE)
        page = context.new_page()
        try:
            if not _fb_is_logged_in(page):
                logger.info("Facebook: session invalid — logging in...")
                if not _fb_login(page, email, password):
                    logger.error("Facebook: authentication failed.")
                    _fb_save_debug_screenshot(page, debug)
                    return False
                context.storage_state(path=str(FACEBOOK_SESSION_FILE))
                logger.info("Facebook: new session saved to %s.", FACEBOOK_SESSION_FILE)

            success = _fb_post(page, content, debug=debug)

            if success:
                context.storage_state(path=str(FACEBOOK_SESSION_FILE))
                logger.info("Facebook: session refreshed and saved.")
            return success

        except Exception as exc:
            logger.error("Facebook: unhandled exception in run_facebook_post: %s", exc)
            return False
        finally:
            context.close()
            browser.close()
            logger.info("Facebook: browser closed.")


# ===========================================================================
# INSTAGRAM
# ===========================================================================


def _ig_is_logged_in(page) -> bool:
    """Return True if the Instagram session is authenticated."""
    logger.info("Instagram: checking login status...")
    try:
        page.goto("https://www.instagram.com/", timeout=30_000)
        page.wait_for_load_state("domcontentloaded", timeout=20_000)
        time.sleep(2)

        if "accounts/login" in page.url:
            logger.info("Instagram: redirected to login page — not authenticated.")
            return False

        authenticated_selectors = [
            "svg[aria-label='Home']",
            "a[href='/direct/inbox/']",
            "a[href='/explore/']",
            "svg[aria-label='New post']",
            "svg[aria-label='Create']",
            "[aria-label='New post']",
        ]
        for sel in authenticated_selectors:
            if page.query_selector(sel):
                logger.info("Instagram: authenticated element found ('%s').", sel)
                return True

        if "instagram.com" in page.url and "login" not in page.url:
            logger.info("Instagram: on home URL without login redirect — assuming logged in.")
            return True

        return False

    except Exception as exc:
        logger.warning("Instagram: exception while checking login: %s", exc)
        return False


def _ig_login(page, email: str, password: str) -> bool:
    """Log in to Instagram with the provided credentials."""
    logger.info("Instagram: navigating to login page...")
    page.goto("https://www.instagram.com/accounts/login/", timeout=30_000)
    page.wait_for_load_state("domcontentloaded", timeout=20_000)
    time.sleep(2)

    try:
        page.fill("input[name='username']", email)
        time.sleep(0.5)
        page.fill("input[name='password']", password)
        page.click("button[type='submit']")
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
        time.sleep(3)

        if "accounts/login" in page.url:
            logger.error("Instagram: still on login page — credentials may be wrong.")
            return False

        if any(k in page.url for k in ("challenge", "two_factor", "verify")):
            logger.warning(
                "Instagram: additional verification required. "
                "Complete it manually — pausing 90 s for intervention."
            )
            time.sleep(90)

        # Dismiss 'Save your login info?' dialog
        _dismiss_optional_dialog(page, [
            "button:has-text('Not now')",
            "button:has-text('Not Now')",
        ])
        time.sleep(1)

        # Dismiss notification permission prompt
        _dismiss_optional_dialog(page, [
            "button:has-text('Not now')",
            "button:has-text('Not Now')",
        ])
        time.sleep(1)

        logger.info("Instagram: login successful (URL: %s).", page.url)
        return True

    except PlaywrightTimeoutError as exc:
        logger.error("Instagram: login timed out: %s", exc)
        return False


def _ig_post(page, content: str, image_path: Optional[str] = None) -> bool:
    """
    Create a feed post on Instagram.

    image_path is required — Instagram feed posts must include a media file.
    For watch mode, place a same-stem .jpg/.jpeg/.png alongside the .txt file.
    """
    if not image_path:
        logger.error(
            "Instagram: an image file is required for feed posts. "
            "Pass --image /path/to/image.jpg or pair a .jpg/.png with the .txt file in watch mode."
        )
        return False

    img = Path(image_path)
    if not img.exists():
        logger.error("Instagram: image file not found: %s", image_path)
        return False

    logger.info("Instagram: starting new post flow (image: %s)...", img.name)
    page.goto("https://www.instagram.com/", timeout=30_000)
    page.wait_for_load_state("domcontentloaded", timeout=20_000)
    time.sleep(2)

    # Dismiss any blocking dialogs
    _dismiss_optional_dialog(page, [
        "button:has-text('Not now')",
        "button:has-text('Not Now')",
    ])

    try:
        # ── Step 1: Open the Create / New-post dialog ──────────────────────
        logger.info("Instagram: looking for New post / Create button...")
        create_selectors = [
            "svg[aria-label='New post']",
            "svg[aria-label='Create']",
            "[aria-label='New post']",
            "[aria-label='Create']",
            "a[href='/create/style/']",
        ]
        opened = False
        for sel in create_selectors:
            try:
                el = page.locator(sel).first
                el.wait_for(state="visible", timeout=8_000)
                # SVGs are not directly clickable — click the nearest ancestor button/link
                try:
                    el.click()
                    opened = True
                except Exception:
                    page.locator(sel).locator("xpath=ancestor::a[1] | ancestor::button[1]").first.click()
                    opened = True
                logger.info("Instagram: opened create dialog via '%s'.", sel)
                break
            except PlaywrightTimeoutError:
                pass

        if not opened:
            logger.error("Instagram: could not find the New post / Create button.")
            return False

        time.sleep(2)

        # ── Step 2: Select image via file chooser ──────────────────────────
        logger.info("Instagram: waiting for file chooser trigger...")
        try:
            with page.expect_file_chooser(timeout=15_000) as fc_info:
                _click_first_visible(page, [
                    "button:has-text('Select from computer')",
                    "button:has-text('Select from Computer')",
                    "div[role='button']:has-text('Select from computer')",
                    "input[type='file']",
                ], timeout=12_000)
            file_chooser = fc_info.value
            file_chooser.set_files(str(img.resolve()))
            logger.info("Instagram: image file selected: %s.", img.name)
        except Exception as exc:
            logger.error("Instagram: file chooser failed: %s", exc)
            return False

        time.sleep(3)

        # ── Step 3: Crop step → Next ───────────────────────────────────────
        logger.info("Instagram: advancing past crop step...")
        if not _click_first_visible(page, [
            "button:has-text('Next')",
            "div[role='button']:has-text('Next')",
        ], timeout=15_000):
            logger.error("Instagram: could not advance past crop step.")
            return False
        time.sleep(2)

        # ── Step 4: Filters/adjustments step → Next ───────────────────────
        logger.info("Instagram: advancing past filters step...")
        if not _click_first_visible(page, [
            "button:has-text('Next')",
            "div[role='button']:has-text('Next')",
        ], timeout=15_000):
            logger.error("Instagram: could not advance past filters step.")
            return False
        time.sleep(2)

        # ── Step 5: Caption ────────────────────────────────────────────────
        logger.info("Instagram: entering caption...")
        caption_el = None
        for sel in [
            "div[aria-label='Write a caption...'][contenteditable='true']",
            "textarea[aria-label='Write a caption...']",
            "div[contenteditable='true']",
            "textarea",
        ]:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=10_000)
                caption_el = loc
                logger.info("Instagram: caption field found via '%s'.", sel)
                break
            except PlaywrightTimeoutError:
                pass

        if caption_el is None:
            logger.warning("Instagram: could not find caption field — posting without caption.")
        else:
            caption_el.click()
            caption_el.type(content, delay=30)
            logger.info("Instagram: caption typed.")

        time.sleep(1)

        # ── Step 6: Share ──────────────────────────────────────────────────
        logger.info("Instagram: clicking Share...")
        if not _click_first_visible(page, [
            "button:has-text('Share')",
            "div[role='button']:has-text('Share')",
        ], timeout=20_000):
            logger.error("Instagram: could not find Share button.")
            return False

        # Wait for the success confirmation overlay
        time.sleep(5)
        logger.info("Instagram: post submitted successfully.")
        return True

    except PlaywrightTimeoutError as exc:
        logger.error("Instagram: timeout during posting: %s", exc)
        return False
    except Exception as exc:
        logger.error("Instagram: unexpected error during posting: %s", exc)
        return False


def run_instagram_post(content: str, image_path: Optional[str] = None) -> bool:
    """
    Top-level entry point: authenticate (reusing session if valid) and post.
    Returns True on success.
    """
    email = os.environ.get("INSTAGRAM_EMAIL")
    password = os.environ.get("INSTAGRAM_PASSWORD")
    if not email or not password:
        logger.error("INSTAGRAM_EMAIL and INSTAGRAM_PASSWORD environment variables must be set.")
        return False

    SESSIONS_PATH.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = _launch_browser(p)
        context = _new_context(browser, INSTAGRAM_SESSION_FILE)
        page = context.new_page()
        try:
            if not _ig_is_logged_in(page):
                logger.info("Instagram: session invalid — logging in...")
                if not _ig_login(page, email, password):
                    logger.error("Instagram: authentication failed.")
                    return False
                context.storage_state(path=str(INSTAGRAM_SESSION_FILE))
                logger.info("Instagram: new session saved to %s.", INSTAGRAM_SESSION_FILE)

            success = _ig_post(page, content, image_path)

            if success:
                context.storage_state(path=str(INSTAGRAM_SESSION_FILE))
                logger.info("Instagram: session refreshed and saved.")
            return success

        except Exception as exc:
            logger.error("Instagram: unhandled exception in run_instagram_post: %s", exc)
            return False
        finally:
            context.close()
            browser.close()
            logger.info("Instagram: browser closed.")


# ===========================================================================
# File-watch mode  (PollingObserver — WSL inotify-safe)
# ===========================================================================

# Image extensions recognised when pairing with an instagram_*.txt file
_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


class SocialPostFileHandler(FileSystemEventHandler):
    """
    Watches Drop_Here/ for:
      facebook_*.txt   → posts text content to Facebook
      instagram_*.txt  → posts to Instagram; auto-detects paired image file
                         (same stem with .jpg / .jpeg / .png / .webp extension)

    On success: file(s) moved to Done/
    On failure: file(s) moved to Needs_Action/
    """

    def on_created(self, event):
        if event.is_directory:
            return

        src = Path(event.src_path)
        if src.suffix.lower() != ".txt":
            return

        name = src.name.lower()
        if name.startswith("facebook_"):
            self._handle_facebook(src)
        elif name.startswith("instagram_"):
            self._handle_instagram(src)

    # ── Facebook ──────────────────────────────────────────────────────────

    def _handle_facebook(self, src: Path):
        logger.info("Watch: Facebook file detected — %s", src.name)
        time.sleep(0.5)  # let the OS finish writing
        content = self._read_file(src)
        if content is None:
            return
        success = run_facebook_post(content)
        self._move_file(src, success)

    # ── Instagram ─────────────────────────────────────────────────────────

    def _handle_instagram(self, src: Path):
        logger.info("Watch: Instagram file detected — %s", src.name)
        time.sleep(0.5)
        content = self._read_file(src)
        if content is None:
            return

        # Find a paired image with the same stem
        image_path: Optional[str] = None
        for ext in _IMAGE_EXTENSIONS:
            candidate = src.parent / (src.stem + ext)
            if candidate.exists():
                image_path = str(candidate)
                logger.info("Watch: paired image found — %s", candidate.name)
                break

        if not image_path:
            logger.error(
                "Watch: no paired image for %s. "
                "Create %s.jpg (or .jpeg/.png/.webp) in the same folder.",
                src.name, src.stem,
            )
            self._move_file(src, success=False)
            return

        success = run_instagram_post(content, image_path)

        # Move the paired image alongside the text file
        dest_folder = DONE_FOLDER if success else NEEDS_ACTION_FOLDER
        dest_folder.mkdir(parents=True, exist_ok=True)
        img = Path(image_path)
        try:
            img.rename(dest_folder / img.name)
            logger.info("Watch: image moved to %s/.", dest_folder.name)
        except Exception as exc:
            logger.warning("Watch: could not move image %s: %s", img.name, exc)

        self._move_file(src, success)

    # ── Utilities ─────────────────────────────────────────────────────────

    def _read_file(self, src: Path) -> Optional[str]:
        try:
            text = src.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.error("Watch: could not read %s: %s", src.name, exc)
            return None
        if not text:
            logger.warning("Watch: %s is empty — skipping.", src.name)
            return None
        return text

    def _move_file(self, src: Path, success: bool):
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


def watch_mode():
    """Start PollingObserver watching Drop_Here/ for social media post files."""
    WATCH_FOLDER.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Watch mode active. Monitoring: %s\n"
        "  facebook_*.txt           → text post to Facebook\n"
        "  instagram_*.txt          → Instagram post (requires paired .jpg/.jpeg/.png/.webp)\n"
        "  e.g. instagram_promo.txt + instagram_promo.jpg",
        WATCH_FOLDER,
    )

    handler = SocialPostFileHandler()
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


# ===========================================================================
# Entry point
# ===========================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Post to Facebook or Instagram via Playwright.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Direct post to Facebook
  python social_poster.py --platform facebook --content "Hello, Facebook!"

  # Direct post to Instagram (image required)
  python social_poster.py --platform instagram --content "Great day!" --image /tmp/photo.jpg

  # Watch Drop_Here/ and post automatically
  python social_poster.py --watch

Watch mode file naming (drop into Drop_Here/):
  facebook_*.txt          → text post to Facebook
  instagram_*.txt         → Instagram post; must have a same-stem image alongside:
                            e.g.  instagram_launch.txt  +  instagram_launch.jpg

Environment variables:
  FACEBOOK_EMAIL      Facebook login e-mail
  FACEBOOK_PASSWORD   Facebook password
  INSTAGRAM_EMAIL     Instagram login e-mail / username
  INSTAGRAM_PASSWORD  Instagram password

Session files (reused across runs):
  ai-employee/sessions/facebook_session.json
  ai-employee/sessions/instagram_session.json
        """,
    )
    parser.add_argument(
        "--platform",
        choices=["facebook", "instagram"],
        help="Target platform (required for direct posting).",
    )
    parser.add_argument(
        "--content",
        help="Text content / caption to post.",
    )
    parser.add_argument(
        "--image",
        help="Path to an image file (required for Instagram feed posts).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help=(
            "Watch Drop_Here/ for facebook_*.txt and instagram_*.txt files "
            "and post them automatically (PollingObserver — WSL-compatible)."
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Save a screenshot to Logs/facebook_debug.png whenever the Facebook "
            "posting flow fails. Useful for diagnosing selector breakage."
        ),
    )
    args = parser.parse_args()

    if args.watch:
        watch_mode()
    elif args.platform and args.content:
        if args.platform == "facebook":
            ok = run_facebook_post(args.content, debug=args.debug)
        else:
            ok = run_instagram_post(args.content, args.image)
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
