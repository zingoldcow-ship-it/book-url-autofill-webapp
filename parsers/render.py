import subprocess
from typing import Tuple, Optional
from .common import DEFAULT_HEADERS, parse_price

def ensure_playwright_installed() -> None:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception as e:
        raise RuntimeError(f"playwright import 실패: {e}")

    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            b.close()
        return
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
        page.wait_for_timeout(1200)
        html = page.content()
        final_url = page.url
        context.close()
        browser.close()
        return final_url, html

def extract_kyobo_prices_playwright(url: str, timeout_ms: int = 45000) -> Tuple[str, str, Optional[int], Optional[int]]:
    """교보문고 상세페이지에서 가격을 확실하게 뽑기 위한 Kyobo 전용 추출.
    사용자 제공 XPath(구조 고정형) + 라벨 기반 fallback을 함께 사용.

    반환: (final_url, html, list_price(정가), sale_price(할인가/판매가))
    """
    ensure_playwright_installed()
    from playwright.sync_api import sync_playwright

    KYOB0_SALE_XPATHS = [
        # 사용자 제공(할인가/판매가)
        "/html/body/div[3]/main/section[2]/div[1]/div/div[2]/div/div[3]/div[1]/div[2]/div/span[2]/span",
    ]
    KYOB0_LIST_XPATHS = [
        # 사용자 제공(정가)
        "/html/body/div[3]/main/section[2]/div[1]/div/div[2]/div/div[3]/div[1]/div[2]/div/span[3]/s",
    ]

    def first_price_by_xpaths(page, xpaths) -> Optional[int]:
        for xp in xpaths:
            try:
                loc = page.locator(f"xpath={xp}")
                if loc.count() == 0:
                    continue
                txt = loc.first.inner_text().strip()
                v = parse_price(txt)
                if v is not None:
                    return v
            except Exception:
                continue
        return None

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
                if v is None:
                    continue
                if v <= 6000:
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

        sale = first_price_by_xpaths(page, KYOB0_SALE_XPATHS)
        listp = first_price_by_xpaths(page, KYOB0_LIST_XPATHS)

        # fallback: 라벨 기반
        if sale is None:
            sale = (
                pick_following_price(page, "최종 판매가")
                or pick_following_price(page, "판매가")
                or pick_following_price(page, "할인가")
            )
        if listp is None:
            listp = pick_following_price(page, "정가")

        html = page.content()
        final_url = page.url
        context.close()
        browser.close()
        return final_url, html, listp, sale
