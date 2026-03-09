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
            b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            b.close()
        return True
    except Exception:
        subprocess.run(["playwright", "install", "chromium"], check=False)
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                b.close()
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
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        html, final_url = page.content(), page.url
        context.close(); browser.close()
        return final_url, html

def extract_kyobo_prices_playwright(url: str, timeout_ms: int = 45000):
    if not ensure_playwright_installed():
        raise RuntimeError("playwright/chromium 실행 불가")
    from playwright.sync_api import sync_playwright

    def text_of_first(page, selectors):
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    txt = loc.inner_text().strip()
                    if txt:
                        return txt
            except Exception:
                continue
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=DEFAULT_HEADERS.get("User-Agent"), locale="ko-KR")
        page = context.new_page()
        page.set_default_navigation_timeout(timeout_ms)
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2200)

        sale_text = text_of_first(page, [
            "css=.prod_price .price .val",
            "css=.prod_price_box .prod_price .price .val",
            "css=.prod_price_wrap .prod_price .price .val",
            "css=.price_wrap .prod_price .price .val",
            "css=span.price > span.val",
            "xpath=//*[contains(@class,'prod_price')]//*[contains(@class,'price')]//*[contains(@class,'val')]",
        ])
        list_text = text_of_first(page, [
            "css=.prod_price .sale_price .val",
            "css=.prod_price_box .prod_price .sale_price .val",
            "css=.prod_price_wrap .prod_price .sale_price .val",
            "css=.price_wrap .prod_price .sale_price .val",
            "css=span.sale_price > span.val",
            "css=.prod_price .sale_price s",
            "css=.prod_price_box .prod_price .sale_price s",
            "xpath=//*[contains(@class,'prod_price')]//*[contains(@class,'sale_price')]//*[contains(@class,'val')]",
        ])

        sale_price = parse_price(sale_text)
        list_price = parse_price(list_text)

        def pick_following_price(label_text: str) -> Optional[int]:
            try:
                loc = page.locator(f"xpath=//*[normalize-space(text())='{label_text}' or contains(normalize-space(.), '{label_text}')]").first
                if loc.count() == 0:
                    return None
                cand = loc.locator("xpath=following::*[contains(., '원')]")
                vals = []
                for i in range(min(cand.count(), 10)):
                    txt = cand.nth(i).inner_text().strip()
                    v = parse_price(txt)
                    if v and 5000 <= v <= 500000:
                        vals.append(v)
                return vals[0] if vals else None
            except Exception:
                return None

        if sale_price is None:
            sale_price = pick_following_price("최종 판매가") or pick_following_price("판매가") or pick_following_price("할인가")
        if list_price is None:
            list_price = pick_following_price("정가")

        if sale_price is not None and list_price is None:
            list_price = sale_price
        if list_price is not None and sale_price is None:
            sale_price = list_price

        html, final_url = page.content(), page.url
        context.close(); browser.close()
        return final_url, html, list_price, sale_price
