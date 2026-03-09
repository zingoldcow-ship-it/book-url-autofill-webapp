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

def extract_labeled_prices_playwright(url: str, timeout_ms: int = 45000) -> Tuple[str, str, Optional[int], Optional[int]]:
    \"\"\"브라우저 렌더링 후, '판매가/정가' 라벨 근처에서 가격을 직접 뽑아온다.
    교보문고의 5,000원 오탐(배송비/혜택)을 피하기 위해 사용.
    반환: (final_url, html, list_price, sale_price)
    \"\"\"
    ensure_playwright_installed()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=DEFAULT_HEADERS.get("User-Agent"), locale="ko-KR")
        page = context.new_page()
        page.set_default_navigation_timeout(timeout_ms)
        page.goto(url, wait_until="networkidle")
        # 가격 영역이 늦게 뜨는 경우가 있어 추가 대기
        page.wait_for_timeout(1400)

        def pick_by_label(label: str) -> Optional[int]:
            # label이 포함된 요소를 찾고, 그 주변(부모/형제)에서 '원' 포함 텍스트를 탐색
            try:
                loc = page.locator(f\"xpath=//*[contains(normalize-space(.), '{label}')]\").first
                if loc.count() == 0:
                    return None
                # 가장 가까운 컨테이너에서 '원'이 있는 텍스트 찾기
                container = loc.locator(\"xpath=ancestor-or-self::*[1]\")
                # parent up to 3 levels to widen scope
                for up in range(0, 4):
                    scope = container if up == 0 else loc.locator(f\"xpath=ancestor::*[{up}]\")

                    # 다음 형제/같은 컨테이너에서 원 텍스트
                    cand = scope.locator(\"xpath=.//*[contains(., '원')]\")
                    n = min(cand.count(), 20)
                    best = None
                    for i in range(n):
                        txt = cand.nth(i).inner_text().strip()
                        val = parse_price(txt)
                        if val is None:
                            continue
                        # 너무 작은 값(<=6000)은 혜택/배송비일 가능성 높음
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
