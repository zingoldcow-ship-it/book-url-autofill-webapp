import re
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
                    return re.sub(r"\s*\|\s*교보문고\s*$", "", v).strip()
        except Exception:
            pass
    m = re.search(r"^\s*([^|\n]{2,120})\s*[|｜]\s*교보문고", text)
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

def _extract_prices_by_dom(s: BeautifulSoup):
    def first_price(selectors):
        for sel in selectors:
            try:
                tag = s.select_one(sel)
                if tag:
                    v = parse_price(tag.get_text(" ", strip=True))
                    if v and 5000 <= v <= 500000:
                        return v
            except Exception:
                continue
        return None

    sale_price = first_price([
        ".prod_price .price .val",
        ".prod_price_box .prod_price .price .val",
        ".prod_price_wrap .prod_price .price .val",
        ".price_wrap .prod_price .price .val",
        "span.price > span.val",
    ])
    list_price = first_price([
        ".prod_price .sale_price .val",
        ".prod_price_box .prod_price .sale_price .val",
        ".prod_price_wrap .prod_price .sale_price .val",
        ".price_wrap .prod_price .sale_price .val",
        "span.sale_price > span.val",
        ".prod_price .sale_price s",
        ".prod_price_box .prod_price .sale_price s",
    ])
    return list_price, sale_price

def _extract_prices_by_labels(text: str):
    t = re.sub(r"\s+", " ", text)
    list_price = None
    sale_price = None
    for pat, kind in [
        (r"정가\s*([0-9][0-9,]{2,})\s*원", "list"),
        (r"판매가\s*([0-9][0-9,]{2,})\s*원", "sale"),
        (r"할인가\s*([0-9][0-9,]{2,})\s*원", "sale"),
        (r"최종\s*판매가\s*([0-9][0-9,]{2,})\s*원", "sale"),
    ]:
        m = re.search(pat, t)
        if m:
            v = parse_price(m.group(1))
            if v:
                if kind == "list" and list_price is None:
                    list_price = v
                if kind == "sale" and sale_price is None:
                    sale_price = v
    nums = [parse_price(x) for x in re.findall(r"([0-9][0-9,]{2,})\s*원", t)]
    nums = [n for n in nums if n and 5000 <= n <= 500000]
    if nums:
        if sale_price is None:
            sale_price = min(nums)
        if list_price is None:
            list_price = max(nums)
    return list_price, sale_price

def _is_out_of_stock(text: str, list_price=None, sale_price=None) -> bool:
    if list_price is not None or sale_price is not None:
        return False
    t = re.sub(r"\s+", " ", text)
    strong = [
        "구매가 불가능한 도서입니다",
        "현재 판매하지 않는 상품입니다",
        "일시 품절",
        "품절되었습니다",
        "판매가 중지되었습니다",
    ]
    return any(k in t for k in strong)

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
        offer_price = parse_price(str(offers.get("price")) if offers.get("price") is not None else None)
        if offer_price:
            list_price = offer_price
            sale_price = offer_price

    title = title or _extract_title(s, text)
    isbn = isbn or scan_isbn(text)
    author = author or _extract_author(text)
    publisher = publisher or _extract_publisher(text) or scan_publisher(text)

    nd_list, nd_sale = extract_next_data_prices(html)
    if nd_list is not None:
        list_price = nd_list
    if nd_sale is not None:
        sale_price = nd_sale

    dom_list, dom_sale = _extract_prices_by_dom(s)
    if list_price is None and dom_list is not None:
        list_price = dom_list
    if sale_price is None and dom_sale is not None:
        sale_price = dom_sale

    if list_price is None and sale_price is None:
        meta_list, meta_sale = _extract_prices_from_meta(s)
        list_price = list_price or meta_list
        sale_price = sale_price or meta_sale

    label_list, label_sale = _extract_prices_by_labels(text)
    if list_price is None and label_list is not None:
        list_price = label_list
    if sale_price is None and label_sale is not None:
        sale_price = label_sale

    if list_price is None or sale_price is None:
        txt_list, txt_sale = scan_prices_from_text(text)
        list_price = list_price or txt_list
        sale_price = sale_price or txt_sale

    if sale_price is not None and list_price is None:
        list_price = sale_price
    if list_price is not None and sale_price is None:
        sale_price = list_price

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

    if _is_out_of_stock(text, list_price, sale_price):
        row["status"] = "failed"
        row["sale_price"] = None
        row["list_price"] = None
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

def parse_kyobo(url: str) -> dict:
    m = re.search(r"/detail/([A-Z0-9]+)", url)
    product_id = m.group(1) if m else None

    final_url, html = fetch_html(url)
    row = _parse_from_html(final_url, html, product_id)
    price = row.get("sale_price") or row.get("list_price")
    if _score(row) >= 4 and not _suspicious_price(price):
        return row

    if extract_kyobo_prices_playwright is not None:
        try:
            final_url2, html2, list2, sale2 = extract_kyobo_prices_playwright(url)
            row2 = _parse_from_html(final_url2, html2, product_id)
            if list2 is not None:
                row2["list_price"] = list2
            if sale2 is not None:
                row2["sale_price"] = sale2
            row2["parse_mode"] = "playwright"
            if row2.get("sale_price") and not row2.get("list_price"):
                row2["list_price"] = row2["sale_price"]
            if row2.get("list_price") and not row2.get("sale_price"):
                row2["sale_price"] = row2["list_price"]

            p1 = row.get("sale_price") or row.get("list_price")
            p2 = row2.get("sale_price") or row2.get("list_price")
            if _score(row2) > _score(row):
                return row2
            if _score(row2) == _score(row) and p2 is not None and (_suspicious_price(p1) or p1 is None):
                return row2
        except Exception:
            pass

    if _score(row) >= 3:
        row["status"] = "success"
        if row.get("error") in {"교보문고 페이지에서 필수 정보를 찾지 못했습니다.", "품절 도서"}:
            row["error"] = None
    return row
