"""The real browser: Chromium driven by Playwright, with a persistent profile so the eBay
login and delivery location survive between runs.

The profile directory holds the eBay login cookies, so keep it out of git.
"""

import time
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

SIGN_IN_URL = "https://signin.ebay.com/"
READY_TIMEOUT_SECONDS = 20  # how long to wait for the content, e.g. while a bot check runs


@dataclass
class PageLoad:
    """What happened on the last page load, for --verbose diagnostics."""

    status: int | None  # HTTP status of the main response
    loaded_url: str  # when the page first finished loading, e.g. eBay's bot check
    final_url: str  # when the HTML was read
    seconds: float  # from starting the load until the HTML was read
    ready: bool | None  # whether the awaited content appeared (None if nothing awaited)


class PlaywrightBrowser:
    """Use as a context manager: `with PlaywrightBrowser(profile_dir) as browser: ...`"""

    def __init__(self, profile_dir: Path, headless: bool = False):
        self.profile_dir = profile_dir
        self.headless = headless

    def __enter__(self) -> "PlaywrightBrowser":
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            self.profile_dir, headless=self.headless
        )
        self.page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self.last_load: PageLoad | None = None
        return self

    def __exit__(self, *exc_info) -> None:
        self._context.close()
        self._playwright.stop()

    def get(self, url: str, wait_for: str | None = None) -> str:
        """Load the URL and return its HTML.

        With wait_for (a CSS selector), first wait until it matches, up to a time limit: eBay
        may show a bot check that redirects to the content after a few seconds, or add
        content with scripts after the page has loaded.
        """
        start = time.monotonic()
        response = self.page.goto(url, wait_until="load")
        loaded_url = self.page.url
        ready = None
        if wait_for:
            try:
                self.page.wait_for_selector(wait_for, timeout=READY_TIMEOUT_SECONDS * 1000)
                ready = True
            except PlaywrightTimeout:
                ready = False  # the parser will report what the page is instead
        html = self.page.content()
        status = response.status if response else None
        seconds = round(time.monotonic() - start, 1)
        self.last_load = PageLoad(status, loaded_url, self.page.url, seconds, ready)
        return html

    def html_now(self) -> str:
        """The current page's HTML as it is now, without reloading."""
        return self.page.content()


def login(profile_dir: Path) -> None:
    """Open eBay's sign-in page and wait until the user closes the browser window."""
    with PlaywrightBrowser(profile_dir) as browser:
        browser.page.goto(SIGN_IN_URL)
        print(
            "In the browser window: sign in to eBay. If item pages later show delivery to a "
            "non-US address, also set 'Shipping to' a US ZIP code on any search page.\n"
            "Close the window when done."
        )
        browser.page.wait_for_event("close", timeout=0)
