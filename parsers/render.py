import subprocess
from typing import Tuple
from .common import DEFAULT_HEADERS

def ensure_playwright_installed() -> None:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception as e:
        raise RuntimeError(f"playwright import 실패: {e}")
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
            b.close()
        return
    except Exception:
        subprocess.run(["playwright","install","chromium"], check=False)

def fetch_html_playwright(url: str, timeout_ms: int = 45000) -> Tuple[str, str]:
    ensure_playwright_installed()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=DEFAULT_HEADERS.get("User-Agent"), locale="ko-KR")
        page = context.new_page()
        page.set_default_navigation_timeout(timeout_ms)
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(900)
        html = page.content()
        final_url = page.url
        context.close()
        browser.close()
        return final_url, html
