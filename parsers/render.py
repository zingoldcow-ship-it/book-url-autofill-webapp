import subprocess
from typing import Tuple, Optional
from .common import DEFAULT_HEADERS, parse_price

def ensure_playwright_installed() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False

    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            browser.close()
        return True
    except Exception:
        subprocess.run(["playwright", "install", "chromium"], check=False)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                browser.close()
            return True
        except Exception:
            return False

def fetch_html_playwright(url: str, timeout_ms: int = 45000) -> Tuple[str, str]:
    if not ensure_playwright_installed():
        raise RuntimeError("playwright/chromium 실행 불가")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=DEFAULT_HEADERS.get("User-Agent"), locale="ko-KR")
        page = context.new_page()
        page.set_default_navigation_timeout(timeout_ms)
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1200)
        html = page.content()
        final_url = page.url
        context.close()
        browser.close()
        return final_url, html

def extract_kyobo_prices_playwright(url: str, timeout_ms: int = 45000) -> Tuple[str, str, Optional[int], Optional[int]]:
    if not ensure_playwright_installed():
        raise RuntimeError("playwright/chromium 실행 불가")
    from playwright.sync_api import sync_playwright

    def pick_following_price(page, label_text: str) -> Optional[int]:
        try:
            loc = page.locator(
                f"xpath=//*[normalize-space(text())='{label_text}' or contains(normalize-space(.), '{label_text}')]"
            ).first
            if loc.count() == 0:
                return None
            cand = loc.locator("xpath=following::*[contains(., '원')]")
            n = min(cand.count(), 12)
            vals = []
            for i in range(n):
                txt = cand.nth(i).inner_text().strip()
                v = parse_price(txt)
                if v is None or v <= 6000:
                    continue
                vals.append(v)
            return max(vals) if vals else None
        except Exception:
            return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=DEFAULT_HEADERS.get("User-Agent"), locale="ko-KR")
        page = context.new_page()
        page.set_default_navigation_timeout(timeout_ms)
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1600)

        sale = pick_following_price(page, "최종 판매가") or pick_following_price(page, "판매가") or pick_following_price(page, "할인가")
        listp = pick_following_price(page, "정가")

        html = page.content()
        final_url = page.url
        context.close()
        browser.close()
        return final_url, html, listp, sale
