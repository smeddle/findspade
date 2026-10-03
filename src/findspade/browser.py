"""The real browser: Chromium driven by Playwright, with a persistent profile so the eBay
login and delivery location survive between runs.

The profile directory holds the eBay login cookies, so keep it out of git.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

SIGN_IN_URL = "https://signin.ebay.com/"


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
        return self

    def __exit__(self, *exc_info) -> None:
        self._context.close()
        self._playwright.stop()

    def get(self, url: str) -> str:
        self.page.goto(url, wait_until="load")
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
