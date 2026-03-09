import re
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from .common import (
    fetch_html, soup, extract_jsonld, pick_booklike, parse_price,
    scan_prices_from_text, scan_isbn, scan_publisher, extract_next_data_prices
)

try:
    from .render import extract_kyobo_prices_playwright
except Exception:
    extract_kyobo_prices_playwright = None


def _clean(v):
    if v is None:
        return None
    v = re.sub(r"\s+", " ", str(v)).strip()
    return v or None


def _meta_content(s: BeautifulSoup, *, prop=None, name=None):
    if prop:
        tag = s.find("meta", property=prop)
        if tag and tag.get("content"):
            return _clean(tag.get("content"))
    if name:
        tag = s.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return _clean(tag.get("content"))
    return None


def _extract_title(s: BeautifulSoup, text: str):
    title = _meta_content(s, prop="og:title") or _meta_content(s, name="title")
    if title:
        title = re.sub(r"\s*\|\s*교보문고\s*$", "", title).strip()
        title = re.sub(r"\s*-\s*교보문고\s*$", "", title).strip()
        if title and "국내도서 메인" not in title:
            return title

    for sel in ["h1", "title", "meta[property='twitter:title']"]:
        try:
            tag = s.select_one(sel)
            if tag:
                v = _clean(tag.get("content")) if tag.name == "meta" else _clean(tag.get_text(" ", strip=True))
                if v and "국내도서 메인" not in v:
                    v = re.sub(r"\s*\|\s*교보문고\s*$", "", v).strip()
                    return v
        except Exception:
            pass

    for pat in [
        r"도서명\s*[:\-]?\s*([^\n|]{2,120})",
        r"^\s*([^|\n]{2,120})\s*[|｜]\s*교보문고",
    ]:
        m = re.search(pat, text)
        if m:
            return _clean(m.group(1))
    return None


def _extract_author(text: str):
    for pat in [
        r"저자\s*(?:\(글\)|\(원작\)|\(편\))?\s*([가-힣A-Za-z0-9·&().,\- ]{2,80})",
        r"작가정보\s*저자\s*(?:\(글\))?\s*([가-힣A-Za-z0-9·&().,\- ]{2,80})",
    ]:
        m = re.search(pat, text)
        if m:
            return _clean(m.group(1))
    return None


def _extract_publisher(text: str):
    for pat in [
        r"출판사\s*[:\-]?\s*([가-힣A-Za-z0-9·&().,\- ]{2,50})",
        r"([가-힣A-Za-z0-9·&().,\- ]{2,50})\s*·\s*\d{4}년\s*\d{1,2}월",
    ]:
        m = re.search(pat, text)
        if m:
            v = _clean(m.group(1))
            if v and v not in {"저자", "작가정보"}:
                return v
    return None


def _extract_prices_from_meta(s: BeautifulSoup):
    vals = []
    for prop in ["product:price:amount", "og:price:amount"]:
        v = _meta_content(s, prop=prop)
        p = parse_price(v)
        if p:
            vals.append(p)
    if vals:
        p = max(vals)
        return p, p
    return None, None


def _is_out_of_stock(text: str) -> bool:
    return any(k in text for k in ["품절", "일시품절", "재고 없음", "판매 중지", "구매 불가"])


def _score(row: dict) -> int:
    score = 0
    for k in ["title", "isbn", "author", "publisher"]:
        if row.get(k):
            score += 1
    if row.get("sale_price") is not None or row.get("list_price") is not None:
        score += 1
    return score


def _parse_from_html(final_url: str, html: str, product_id: str | None) -> dict:
    s = soup(html)
    text = re.sub(r"\s+", " ", s.get_text(" ", strip=True))
    book = pick_booklike(extract_jsonld(s)) or {}

    title = _clean(book.get("name")) if isinstance(book, dict) else None
    isbn = _clean(book.get("isbn") or book.get("ISBN")) if isinstance(book, dict) else None
    author = None
    publisher = None
    list_price = None
    sale_price = None

    a = book.get("author") if isinstance(book, dict) else None
    if isinstance(a, dict):
        author = _clean(a.get("name"))
    elif isinstance(a, list):
        vals = []
        for item in a:
            if isinstance(item, dict) and item.get("name"):
                vals.append(_clean(item.get("name")))
            elif isinstance(item, str):
                vals.append(_clean(item))
        author = ", ".join([x for x in vals if x]) if vals else None
    elif isinstance(a, str):
        author = _clean(a)

    p = book.get("publisher") if isinstance(book, dict) else None
    if isinstance(p, dict):
        publisher = _clean(p.get("name"))
    elif isinstance(p, str):
        publisher = _clean(p)

    offers = book.get("offers") if isinstance(book, dict) else None
    if isinstance(offers, dict):
        list_price = parse_price(str(offers.get("price")) if offers.get("price") is not None else None)
        sale_price = list_price

    title = title or _extract_title(s, text)
    isbn = isbn or scan_isbn(text)
    author = author or _extract_author(text)
    publisher = publisher or _extract_publisher(text) or scan_publisher(text)

    nd_list, nd_sale = extract_next_data_prices(html)
    if nd_list is not None:
        list_price = nd_list
    if nd_sale is not None:
        sale_price = nd_sale

    if list_price is None and sale_price is None:
        meta_list, meta_sale = _extract_prices_from_meta(s)
        list_price = list_price or meta_list
        sale_price = sale_price or meta_sale

    if list_price is None or sale_price is None:
        txt_list, txt_sale = scan_prices_from_text(text)
        list_price = list_price or txt_list
        sale_price = sale_price or txt_sale

    row = {
        "site": "KYobo",
        "url": final_url,
        "status": "success" if (title or isbn or author or publisher) else "failed",
        "product_id": product_id,
        "isbn": isbn,
        "title": title,
        "author": author,
        "publisher": publisher,
        "list_price": list_price,
        "sale_price": sale_price,
        "error": None,
        "parse_mode": "requests",
    }

    if _is_out_of_stock(text):
        row["status"] = "failed"
        row["sale_price"] = None
        row["error"] = "품절 도서"
    elif row["status"] != "success":
        row["error"] = "교보문고 페이지에서 필수 정보를 찾지 못했습니다."
    return row


def _suspicious_price(v):
    if v is None:
        return True
    try:
        return int(v) <= 6000
    except Exception:
        return False


def _search_engine_guess(url: str, product_id: str | None):
    """외부 검색 결과 스니펫에서 제목/저자 등을 추정."""
    import requests

    queries = [
        f'"{url}"',
        f'"{product_id}" 교보문고' if product_id else "",
        f'"{product_id}"' if product_id else "",
    ]
    patterns_title = [
        r"『([^』]{2,120})』",
        r"“([^”]{2,120})”",
        r'"([^"]{2,120})"',
    ]
    author_pat = r"([가-힣A-Za-z0-9·&().,\- ]{2,40})\s*(?:저서|저자\(글\)|지음)"
    for q in queries:
        if not q:
            continue
        try:
            search_url = "https://html.duckduckgo.com/html/?q=" + quote_plus(q)
            resp = requests.get(search_url, timeout=20, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            })
            if resp.status_code != 200:
                continue
            text = re.sub(r"\s+", " ", BeautifulSoup(resp.text, "lxml").get_text(" ", strip=True))
            title = None
            for pat in patterns_title:
                m = re.search(pat, text)
                if m:
                    candidate = _clean(m.group(1))
                    if candidate and "교보문고" not in candidate and len(candidate) >= 2:
                        title = candidate
                        break
            author = None
            m = re.search(author_pat, text)
            if m:
                author = _clean(m.group(1))
            if title or author:
                return {"title": title, "author": author}
        except Exception:
            continue
    return {"title": None, "author": None}


def _search_kyobo_by_keyword(keyword: str):
    """교보 검색 결과 페이지에서 제목/저자/출판사/가격을 보조 추출."""
    import requests

    if not keyword:
        return {}
    try:
        search_url = "https://search.kyobobook.co.kr/search?keyword=" + quote_plus(keyword)
        resp = requests.get(search_url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        })
        resp.raise_for_status()
        s = BeautifulSoup(resp.text, "lxml")

        # 첫 상세페이지 링크 주변을 우선 사용
        link = None
        for a in s.select('a[href*="/detail/"], a[href*="product.kyobobook.co.kr/detail"]'):
            txt = _clean(a.get_text(" ", strip=True))
            href = a.get("href") or ""
            if txt and len(txt) >= 2 and "/detail/" in href:
                link = a
                break

        block_text = ""
        title = None
        if link is not None:
            title = _clean(link.get_text(" ", strip=True))
            parent = link
            for _ in range(5):
                parent = parent.parent
                if parent is None:
                    break
                block_text = re.sub(r"\s+", " ", parent.get_text(" ", strip=True))
                if len(block_text) >= 80:
                    break

        text = block_text or re.sub(r"\s+", " ", s.get_text(" ", strip=True))
        author = None
        publisher = None
        list_price = None
        sale_price = None

        m = re.search(r"([가-힣A-Za-z0-9·&().,\- ]{2,40})\s*저자\(글\)", text)
        if m:
            author = _clean(m.group(1))
        m = re.search(r"([가-힣A-Za-z0-9·&().,\- ]{2,40})\s*·\s*\d{4}년\s*\d{1,2}월", text)
        if m:
            publisher = _clean(m.group(1))

        prices = [parse_price(x) for x in re.findall(r"(\d[\d,]{2,})\s*원", text)]
        prices = [p for p in prices if p and 5000 <= p <= 500000]
        if prices:
            sale_price = min(prices)
            list_price = max(prices)

        return {
            "title": title,
            "author": author,
            "publisher": publisher,
            "list_price": list_price,
            "sale_price": sale_price,
        }
    except Exception:
        return {}


def parse_kyobo(url: str) -> dict:
    m = re.search(r"/detail/([A-Z0-9]+)", url)
    product_id = m.group(1) if m else None

    final_url, html = fetch_html(url)
    row = _parse_from_html(final_url, html, product_id)

    price = row.get("sale_price") or row.get("list_price")
    if _score(row) >= 3 and not _suspicious_price(price):
        return row

    # 1) 검색엔진 스니펫으로 제목 힌트 추정
    guess = _search_engine_guess(url, product_id)
    guessed_title = guess.get("title")
    guessed_author = guess.get("author")

    # 2) 교보 검색 결과 페이지로 보강
    search_row = _search_kyobo_by_keyword(guessed_title or product_id or "")
    improved = dict(row)
    if guessed_title and not improved.get("title"):
        improved["title"] = guessed_title
    if guessed_author and not improved.get("author"):
        improved["author"] = guessed_author

    for key in ["title", "author", "publisher", "list_price", "sale_price"]:
        if search_row.get(key) and not improved.get(key):
            improved[key] = search_row.get(key)

    # 개선되었으면 search-fallback 결과 채택
    if _score(improved) > _score(row):
        improved["status"] = "success"
        improved["parse_mode"] = "search-fallback"
        improved["error"] = None if _score(improved) >= 3 else improved.get("error")
        row = improved

    # 3) 그래도 부족하면 playwright 보조 파싱 시도. 실패해도 기존 row 유지
    if extract_kyobo_prices_playwright is not None and (_score(row) < 4 or _suspicious_price(row.get("sale_price") or row.get("list_price"))):
        try:
            final_url2, html2, list2, sale2 = extract_kyobo_prices_playwright(url)
            row2 = _parse_from_html(final_url2, html2, product_id)
            if list2 is not None:
                row2["list_price"] = list2
            if sale2 is not None:
                row2["sale_price"] = sale2
            row2["parse_mode"] = "playwright"

            if guessed_title and not row2.get("title"):
                row2["title"] = guessed_title
            if guessed_author and not row2.get("author"):
                row2["author"] = guessed_author

            for key in ["publisher"]:
                if search_row.get(key) and not row2.get(key):
                    row2[key] = search_row.get(key)

            if _score(row2) > _score(row):
                row2["status"] = "success"
                row2["error"] = None
                return row2
            p1 = row.get("sale_price") or row.get("list_price")
            p2 = row2.get("sale_price") or row2.get("list_price")
            if _score(row2) == _score(row) and p2 is not None and (_suspicious_price(p1) or p1 is None):
                row2["status"] = "success"
                row2["error"] = None
                return row2
        except Exception:
            pass

    # 마지막 정리
    if _score(row) >= 3:
        row["status"] = "success"
        if row.get("error") == "교보문고 페이지에서 필수 정보를 찾지 못했습니다.":
            row["error"] = None
    return row
