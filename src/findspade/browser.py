"""The real browser: Chromium driven by Playwright, with a persistent profile so the eBay
login and delivery location survive between runs.

The profile directory holds the eBay login cookies, so keep it out of git.
"""

import time
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

SIGN_IN_URL = "https://signin.ebay.com/"


@dataclass
class PageLoad:
    """What happened on the last page load, for --verbose diagnostics."""

    status: int | None  # HTTP status of the main response
    final_url: str  # after any redirects
    seconds: float  # from starting the load until the HTML was read


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

    def get(self, url: str) -> str:
        start = time.monotonic()
        response = self.page.goto(url, wait_until="load")
        html = self.page.content()
        status = response.status if response else None
        self.last_load = PageLoad(status, self.page.url, round(time.monotonic() - start, 1))
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
