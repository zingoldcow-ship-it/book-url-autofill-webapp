import subprocess
from typing import Optional, Tuple

from .common import DEFAULT_HEADERS, parse_price


def ensure_playwright_installed() -> None:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception as e:
        raise RuntimeError(f"playwright import 실패: {e}")

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            browser.close()
    except Exception:
        subprocess.run(["playwright", "install", "chromium"], check=False)


def fetch_html_playwright(url: str, timeout_ms: int = 45000) -> Tuple[str, str]:
    ensure_playwright_installed()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
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


def extract_labeled_prices_playwright(url: str, timeout_ms: int = 45000) -> Tuple[str, str, Optional[int], Optional[int]]:
    """브라우저 렌더링 후, '판매가/정가' 라벨 근처에서 가격을 직접 뽑아온다.
    교보문고의 5,000원 오탐(배송비/혜택)을 피하기 위해 사용한다.
    반환값: (final_url, html, list_price, sale_price)
    """
    ensure_playwright_installed()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=DEFAULT_HEADERS.get("User-Agent"), locale="ko-KR")
        page = context.new_page()
        page.set_default_navigation_timeout(timeout_ms)
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(1400)

        def pick_by_label(label: str) -> Optional[int]:
            try:
                loc = page.locator(f"xpath=//*[contains(normalize-space(.), '{label}')]").first
                if loc.count() == 0:
                    return None

                container = loc.locator("xpath=ancestor-or-self::*[1]")

                for up in range(0, 4):
                    scope = container if up == 0 else loc.locator(f"xpath=ancestor::*[{up}]")
                    cand = scope.locator("xpath=.//*[contains(., '원')]")
                    n = min(cand.count(), 20)
                    best = None

                    for i in range(n):
                        txt = cand.nth(i).inner_text().strip()
                        val = parse_price(txt)
                        if val is None:
                            continue
                        if val <= 6000:
                            continue
                        best = val if best is None else max(best, val)

                    if best is not None:
                        return best
            except Exception:
                return None

            return None

        sale_price = pick_by_label("판매가") or pick_by_label("할인가")
        list_price = pick_by_label("정가")

        html = page.content()
        final_url = page.url
        context.close()
        browser.close()
        return final_url, html, list_price, sale_price
