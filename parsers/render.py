import os
import subprocess
from typing import Tuple

from .common import DEFAULT_HEADERS


def ensure_playwright_installed() -> None:
    """
    Streamlit Cloud에서 playwright 브라우저(Chromium)가 설치되지 않은 경우가 있습니다.
    이 함수는 필요 시 런타임에 'playwright install chromium'를 시도합니다.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception as e:
        raise RuntimeError(f"playwright import 실패: {e}")

    # Quick check: playwright driver exists means pip ok; chromium may still be missing.
    # We'll attempt a harmless launch; if it fails, install chromium.
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            browser.close()
        return
    except Exception:
        # Try installing chromium
        subprocess.run(["playwright", "install", "chromium"], check=False)


def fetch_html_playwright(url: str, timeout_ms: int = 30000) -> Tuple[str, str]:
    """
    Fetch rendered HTML with Playwright (Chromium).
    Returns (final_url, html_text).
    """
    ensure_playwright_installed()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent=DEFAULT_HEADERS.get("User-Agent"),
            locale="ko-KR",
        )
        page = context.new_page()
        page.set_default_navigation_timeout(timeout_ms)
        page.goto(url, wait_until="networkidle")
        # some sites need a bit more settling
        page.wait_for_timeout(500)
        html = page.content()
        final_url = page.url
        context.close()
        browser.close()
        return final_url, html
