import re
import json
from typing import Any, Optional, Tuple

from .common import (
    fetch_html, soup, extract_jsonld, pick_booklike, parse_price,
    scan_prices_from_text, scan_isbn, scan_publisher
)
from .render import fetch_html_playwright, extract_labeled_prices_playwright


KYOB0_MIN_VALID_PRICE = 7000  # 5,000원(배송비/혜택) 오탐을 강하게 배제


def _walk(obj: Any, path: str = "") -> list[tuple[str, Any]]:
    items = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            items.append((p, v))
            items.extend(_walk(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}[{i}]"
            items.append((p, v))
            items.extend(_walk(v, p))
    return items


def extract_kyobo_next_data_prices(html: str) -> Tuple[Optional[int], Optional[int]]:
    """교보문고(Next.js) 페이지의 __NEXT_DATA__에서 가격 후보를 추출.
    5,000원 같은 배송비/혜택 오탐을 피하기 위해:
    - path에 배송/적립/쿠폰/혜택 관련 키워드가 있으면 제외
    - 가격은 최소 KYOB0_MIN_VALID_PRICE 이상만 인정
    """
    s = soup(html)
    tag = s.find("script", id="__NEXT_DATA__")
    if not tag:
        return (None, None)
    raw = tag.string or tag.get_text()
    if not raw:
        return (None, None)
    try:
        data = json.loads(raw)
    except Exception:
        return (None, None)

    include_keys = [
        "salePrice", "sellPrice", "discountPrice", "discountedPrice", "finalPrice",
        "price", "sellingPrice", "currentPrice", "normalPrice", "listPrice", "standardPrice", "origPrice"
    ]
    exclude_tokens = [
        "delivery", "shipping", "ship", "fee", "point", "mileage", "reward", "coupon",
        "benefit", "cash", "save", "saving", "accum", "earn", "member", "welcome", "gift"
    ]

    candidates: list[tuple[str, int]] = []
    for p, v in _walk(data):
        lower_p = p.lower()
        if any(t in lower_p for t in exclude_tokens):
            continue
        if not any(k.lower() in lower_p for k in include_keys):
            continue

        val = None
        if isinstance(v, (int, float)):
            val = int(v)
        elif isinstance(v, str):
            val = parse_price(v)

        if val is None:
            continue
        if val < KYOB0_MIN_VALID_PRICE or val > 500000:
            continue
        candidates.append((p, val))

    if not candidates:
        return (None, None)

    def score(path: str, val: int) -> int:
        lp = path.lower()
        s = 0
        if "saleprice" in lp or "sellprice" in lp or "discount" in lp or "final" in lp or "current" in lp:
            s += 200
        if "listprice" in lp or "standard" in lp or "normal" in lp or "orig" in lp:
            s += 100
        # 값이 큰 쪽을 약간 선호 (단, 극단적으로 큰 값은 이미 필터링)
        s += min(val // 100, 500)
        # 상세 상품 컨텍스트일 가능성 있는 토큰 가산
        if any(t in lp for t in ["goods", "product", "item", "detail", "priceinfo", "sale"]):
            s += 80
        return s

    candidates.sort(key=lambda x: score(x[0], x[1]), reverse=True)

    # sale_price: 가장 점수 높은 값
    sale_price = candidates[0][1]

    # list_price: list/standard/normal/orig 키워드가 있는 후보 중 가장 점수 높은 값
    list_price = None
    for p, v in candidates:
        lp = p.lower()
        if any(k in lp for k in ["listprice", "standard", "normal", "orig"]):
            list_price = v
            break

    if list_price is None:
        list_price = max(v for _, v in candidates)

    # list_price는 sale_price보다 작을 수 없도록 보정
    if list_price < sale_price:
        list_price = max(list_price, sale_price)

    return (list_price, sale_price)


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

    # 0) JSON-LD offers
    offers = book.get("offers")
    if isinstance(offers, dict):
        list_price = parse_price(str(offers.get("price")) if offers.get("price") is not None else None)
        sale_price = list_price

    if not title:
        og = s.find("meta", property="og:title")
        title = og.get("content").strip() if og and og.get("content") else None

    text = s.get_text(" ", strip=True)

    # 1) __NEXT_DATA__ 기반 (강력)
    nd_list, nd_sale = extract_kyobo_next_data_prices(html)
    if nd_list is not None:
        list_price = nd_list
    if nd_sale is not None:
        sale_price = nd_sale

    # 2) ISBN / publisher 스캔
    if not isbn:
        isbn = scan_isbn(text)
    if not publisher:
        publisher = scan_publisher(text)

    # 3) 텍스트 기반 가격 (fallback; 오탐 가능 → min price 체크)
    if list_price is None or sale_price is None:
        lp, sp = scan_prices_from_text(text)
        if lp is not None and lp >= KYOB0_MIN_VALID_PRICE:
            list_price = list_price or lp
        if sp is not None and sp >= KYOB0_MIN_VALID_PRICE:
            sale_price = sale_price or sp

    # 오탐 방지: 7,000원 미만이면 '가격 없음' 취급
    if isinstance(list_price, int) and list_price < KYOB0_MIN_VALID_PRICE:
        list_price = None
    if isinstance(sale_price, int) and sale_price < KYOB0_MIN_VALID_PRICE:
        sale_price = None

    status = "success" if (title or isbn) and (sale_price is not None or list_price is not None) else "failed"
    err = None if status == "success" else "가격/ISBN/출판사 정보를 찾지 못했습니다(오탐 방지로 가격을 제외했을 수 있음)."

    return {
        "site": "KYobo",
        "url": final_url,
        "status": status,
        "product_id": product_id,
        "isbn": isbn,
        "title": title,
        "author": author,
        "publisher": publisher,
        "list_price": list_price,
        "sale_price": sale_price,
        "error": err,
    }


def parse_kyobo(url: str) -> dict:
    m = re.search(r"/detail/([A-Z0-9]+)", url)
    product_id = m.group(1) if m else None

    final_url, html = fetch_html(url)
    row = _parse_from_html(final_url, html, product_id)
    row["parse_mode"] = "requests"

    # requests 결과가 실패이거나 가격이 없으면 playwright로
    price = row.get("sale_price") or row.get("list_price")
    if row["status"] != "success" or price is None:
        # 1) 일반 playwright html
        final_url2, html2 = fetch_html_playwright(url)
        row2 = _parse_from_html(final_url2, html2, product_id)
        row2["parse_mode"] = "playwright"

        # 2) 그래도 가격이 없으면 '라벨 기반'으로 직접 추출하여 주입
        p2 = row2.get("sale_price") or row2.get("list_price")
        if p2 is None:
            final_url3, html3, lp3, sp3 = extract_labeled_prices_playwright(url)
            row3 = _parse_from_html(final_url3, html3, product_id)
            if lp3 is not None and lp3 >= KYOB0_MIN_VALID_PRICE:
                row3["list_price"] = lp3
            if sp3 is not None and sp3 >= KYOB0_MIN_VALID_PRICE:
                row3["sale_price"] = sp3
            p3 = row3.get("sale_price") or row3.get("list_price")
            if p3 is not None:
                row3["status"] = "success"
                row3["error"] = None
            row3["parse_mode"] = "playwright"
            return row3

        return row2

    return row
