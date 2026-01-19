import re
from .common import (
    fetch_html, soup, extract_jsonld, pick_booklike, parse_price,
    scan_prices_from_text, scan_isbn, scan_publisher, extract_next_data_prices
)
from .render import fetch_html_playwright, extract_kyobo_prices_playwright


def _is_out_of_stock(html: str) -> bool:
    """교보문고 품절/판매중지/재고없음 감지.

    raw HTML에는 스크립트/혜택/템플릿 문자열이 섞여 오탐이 날 수 있어
    가능한 한 BeautifulSoup의 가시 텍스트(get_text)에서만 판정한다.
    """
    try:
        text = soup(html).get_text(" ", strip=True)
    except Exception:
        text = html or ""

    # 흔한 패턴(페이지 어딘가에 존재할 수 있는 일반 문구)은 제외하고,
    # 실제 '품절/절판/판매중지/구매불가'를 의미하는 표현 위주로만 감지한다.
    patterns = [
        r"재고\s*사정.*품절",
        r"일시\s*품절",
        r"현재\s*품절",
        r"품절\s*도서",
        r"절판",
        r"판매\s*중지",
        r"구매\s*불가",
    ]
    return any(re.search(p, text) for p in patterns)


def _parse_from_html(final_url: str, html: str, product_id: str | None) -> dict:
    s = soup(html)
    book = pick_booklike(extract_jsonld(s)) or {}

    title = book.get("name") or None
    isbn = book.get("isbn") or book.get("ISBN") or None
    author = None
    publisher = None
    list_price = None
    sale_price = None

    a = book.get("author")
    if isinstance(a, dict):
        author = a.get("name")
    elif isinstance(a, list):
        names = []
        for it in a:
            if isinstance(it, dict) and it.get("name"):
                names.append(it.get("name"))
            elif isinstance(it, str):
                names.append(it)
        author = ", ".join(names) if names else None
    elif isinstance(a, str):
        author = a

    p = book.get("publisher")
    if isinstance(p, dict):
        publisher = p.get("name")
    elif isinstance(p, str):
        publisher = p

    offers = book.get("offers")
    if isinstance(offers, dict):
        list_price = parse_price(str(offers.get("price")) if offers.get("price") is not None else None)
        sale_price = list_price

    if not title:
        og = s.find("meta", property="og:title")
        title = og.get("content").strip() if og and og.get("content") else None

    text = s.get_text(" ", strip=True)

    # 공통 Next.js 추출 (가끔 5,000 오탐이 섞일 수 있음 → 최종은 playwright 전용으로 교정)
    nd_list, nd_sale = extract_next_data_prices(html)
    if nd_list is not None:
        list_price = nd_list
    if nd_sale is not None:
        sale_price = nd_sale

    if not isbn:
        isbn = scan_isbn(text)
    if not publisher:
        publisher = scan_publisher(text)

    if list_price is None or sale_price is None:
        lp, sp = scan_prices_from_text(text)
        list_price = list_price or lp
        sale_price = sale_price or sp

    return {
        "site": "KYobo",
        "url": final_url,
        "status": "success" if (title or isbn) else "failed",
        "product_id": product_id,
        "isbn": isbn,
        "title": title,
        "author": author,
        "publisher": publisher,
        "list_price": list_price,
        "sale_price": sale_price,
        "error": None,
    }

def _is_suspicious(v):
    if v is None:
        return True
    if not isinstance(v, int):
        return False
    return v <= 6000

def parse_kyobo(url: str) -> dict:
    m = re.search(r"/detail/([A-Z0-9]+)", url)
    product_id = m.group(1) if m else None

    # 1) requests로 기본 정보(ISBN/출판사/제목/저자) 우선 확보
    final_url, html = fetch_html(url)
    row = _parse_from_html(final_url, html, product_id)
    row["parse_mode"] = "requests"

    # 2) 가격은 교보에서 오탐이 잦으므로 '의심'이면 곧바로 playwright kyobo 전용 가격 추출로 교정
    
    # 품절/재고없음이면 '가격만' 0 처리(요청사항)
    # - 나머지(제목/ISBN/저자/출판사)는 기존 로직 그대로 유지
    # - 품절은 정상 구매 불가 상태이므로 status는 failed로 두되, 가격만 0으로 고정
    if _is_out_of_stock(html):
        row["list_price"] = 0
        row["sale_price"] = 0
        row["status"] = "failed"
        row["error"] = "품절/재고없음 도서"
        row["parse_mode"] = "requests"
        return row

    p = row.get("sale_price") or row.get("list_price")

    if _is_suspicious(p):
        final_url2, html2, lp2, sp2 = extract_kyobo_prices_playwright(url)
        # playwright로 얻은 html로 다시 파싱(정보가 더 풍부할 수 있음)
        row2 = _parse_from_html(final_url2, html2, product_id)

        # playwright 렌더링에서만 품절 문구가 노출되는 케이스 처리
        if _is_out_of_stock(html2):
            row2["list_price"] = 0
            row2["sale_price"] = 0
            row2["status"] = "failed"
            row2["error"] = "품절/재고없음 도서"
            row2["parse_mode"] = "playwright"
            return row2
        if lp2 is not None:
            row2["list_price"] = lp2
        if sp2 is not None:
            row2["sale_price"] = sp2

        p2 = row2.get("sale_price") or row2.get("list_price")
        if _is_suspicious(p2):
            row2["status"] = "failed"
            row2["error"] = "교보문고 가격을 찾지 못했습니다(배송비/혜택 오탐 방지로 5,000원은 제외)."
        else:
            row2["status"] = "success" if (row2.get("title") or row2.get("isbn")) else "failed"
            row2["error"] = None if row2["status"] == "success" else "필수 정보를 찾지 못했습니다."
        row2["parse_mode"] = "playwright"
        return row2

    # 가격이 정상처럼 보이면 그대로
    if row["status"] != "success":
        row["error"] = "필수 정보를 찾지 못했습니다(차단/구조 변경 가능)."
    return row
