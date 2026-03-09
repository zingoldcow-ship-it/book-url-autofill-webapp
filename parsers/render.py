from typing import Tuple, Optional
from .common import DEFAULT_HEADERS, parse_price, fetch_html

def _try_import_playwright():
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        return sync_playwright
    except Exception:
        return None

def fetch_html_playwright(url: str, timeout_ms: int = 45000) -> Tuple[str, str]:
    """
    Optional Playwright renderer.
    Streamlit Cloud 배포 안정성을 위해 Playwright가 없으면 requests 결과로 안전하게 폴백한다.
    """
    sync_playwright = _try_import_playwright()
    if sync_playwright is None:
        return fetch_html(url, timeout=max(20, timeout_ms // 1000))

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                user_agent=DEFAULT_HEADERS.get("User-Agent"),
                locale="ko-KR",
            )
            page = context.new_page()
            page.set_default_navigation_timeout(timeout_ms)
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(900)
            html = page.content()
            final_url = page.url
            context.close()
            browser.close()
            return final_url, html
    except Exception:
        return fetch_html(url, timeout=max(20, timeout_ms // 1000))

def extract_labeled_prices_playwright(
    url: str, timeout_ms: int = 45000
) -> Tuple[str, str, Optional[int], Optional[int]]:
    """
    브라우저 렌더링 기반 가격 보정.
    Playwright를 사용할 수 없으면 HTML만 가져오고 가격 보정은 생략한다.
    """
    sync_playwright = _try_import_playwright()
    if sync_playwright is None:
        final_url, html = fetch_html(url, timeout=max(20, timeout_ms // 1000))
        return final_url, html, None, None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                user_agent=DEFAULT_HEADERS.get("User-Agent"),
                locale="ko-KR",
            )
            page = context.new_page()
            page.set_default_navigation_timeout(timeout_ms)
            page.goto(url, wait_until="domcontentloaded")
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

            sale = pick_by_label("판매가") or pick_by_label("할인가")
            listp = pick_by_label("정가")

            html = page.content()
            final_url = page.url
            context.close()
            browser.close()
            return final_url, html, listp, sale
    except Exception:
        final_url, html = fetch_html(url, timeout=max(20, timeout_ms // 1000))
        return final_url, html, None, None
