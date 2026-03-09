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
                    return re.sub(r"\s*\|\s*교보문고\s*$", "", v).strip()
        except Exception:
            pass
    m = re.search(r"^\s*([^|\n]{2,120})\s*[|｜]\s*교보문고", text)
    return _clean(m.group(1)) if m else None

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

def _extract_prices_from_any_text(text: str):
    t = re.sub(r"\s+", " ", text)
    nums = [parse_price(x) for x in re.findall(r"([0-9][0-9,]{2,})\s*원", t)]
    nums = [n for n in nums if n and 5000 <= n <= 500000]
    if not nums:
        return None, None
    return max(nums), min(nums)

def _parse_from_html(final_url: str, html: str, product_id: str | None):
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
    return row

def _score(row):
    score = sum(1 for k in ["title", "isbn", "author", "publisher"] if row.get(k))
    if row.get("sale_price") is not None or row.get("list_price") is not None:
        score += 2
    return score

def _suspicious_price(v):
    if v is None:
        return True
    try:
        return int(v) <= 6000
    except Exception:
        return False

def _search_engine_guess(url: str, product_id: str | None):
    import requests
    queries = [
        f'"{url}"',
        f'"{product_id}" 교보문고' if product_id else "",
        f'교보문고 "{product_id}" 가격' if product_id else "",
        f'"{product_id}"' if product_id else "",
    ]
    patterns_title = [r"『([^』]{2,120})』", r"“([^”]{2,120})”", r'"([^"]{2,120})"']
    author_pat = r"([가-힣A-Za-z0-9·&().,\- ]{2,40})\s*(?:저서|저자\(글\)|지음)"
    for q in queries:
        if not q:
            continue
        try:
            search_url = "https://html.duckduckgo.com/html/?q=" + quote_plus(q)
            resp = requests.get(search_url, timeout=20, headers={"User-Agent":"Mozilla/5.0","Accept-Language":"ko-KR,ko;q=0.9,en;q=0.8"})
            if resp.status_code != 200:
                continue
            text = re.sub(r"\s+", " ", BeautifulSoup(resp.text, "lxml").get_text(" ", strip=True))
            title = None
            for pat in patterns_title:
                m = re.search(pat, text)
                if m:
                    cand = _clean(m.group(1))
                    if cand and "교보문고" not in cand and len(cand) >= 2:
                        title = cand
                        break
            author = None
            m = re.search(author_pat, text)
            if m:
                author = _clean(m.group(1))
            list_price, sale_price = _extract_prices_from_any_text(text)
            if title or author or list_price or sale_price:
                return {"title": title, "author": author, "list_price": list_price, "sale_price": sale_price}
        except Exception:
            continue
    return {"title": None, "author": None, "list_price": None, "sale_price": None}

def _search_kyobo_by_keyword(keyword: str, product_id: str | None = None):
    import requests
    if not keyword:
        return {}
    try:
        search_url = "https://search.kyobobook.co.kr/search?keyword=" + quote_plus(keyword)
        resp = requests.get(search_url, timeout=20, headers={"User-Agent":"Mozilla/5.0","Accept-Language":"ko-KR,ko;q=0.9,en;q=0.8"})
        resp.raise_for_status()
        s = BeautifulSoup(resp.text, "lxml")

        target = None
        for a in s.select('a[href*="/detail/"], a[href*="product.kyobobook.co.kr/detail"]'):
            href = a.get("href") or ""
            txt = _clean(a.get_text(" ", strip=True))
            if product_id and product_id in href:
                target = a
                break
            if target is None and txt and len(txt) >= 2 and "/detail/" in href:
                target = a

        block_text = ""
        title = None
        if target is not None:
            title = _clean(target.get_text(" ", strip=True))
            parent = target
            for _ in range(8):
                parent = parent.parent
                if parent is None:
                    break
                block_text = re.sub(r"\s+", " ", parent.get_text(" ", strip=True))
                if product_id and product_id in block_text:
                    break
                if len(block_text) >= 120:
                    break

        text = block_text or re.sub(r"\s+", " ", s.get_text(" ", strip=True))
        author = None
        publisher = None
        m = re.search(r"([가-힣A-Za-z0-9·&().,\- ]{2,40})\s*저자\(글\)", text)
        if m:
            author = _clean(m.group(1))
        m = re.search(r"([가-힣A-Za-z0-9·&().,\- ]{2,40})\s*·\s*\d{4}년\s*\d{1,2}월", text)
        if m:
            publisher = _clean(m.group(1))
        list_price, sale_price = _extract_prices_from_any_text(text)
        return {"title": title, "author": author, "publisher": publisher, "list_price": list_price, "sale_price": sale_price}
    except Exception:
        return {}

def parse_kyobo(url: str):
    m = re.search(r"/detail/([A-Z0-9]+)", url)
    product_id = m.group(1) if m else None

    final_url, html = fetch_html(url)
    row = _parse_from_html(final_url, html, product_id)

    # 검색 fallback으로 가격 먼저 보강
    guess = _search_engine_guess(url, product_id)
    search_row = _search_kyobo_by_keyword(guess.get("title") or product_id or "", product_id=product_id)

    improved = dict(row)
    for key in ["title", "author", "list_price", "sale_price"]:
        if guess.get(key) and not improved.get(key):
            improved[key] = guess.get(key)
    for key in ["title", "author", "publisher", "list_price", "sale_price"]:
        if search_row.get(key) and not improved.get(key):
            improved[key] = search_row.get(key)

    if improved.get("sale_price") and not improved.get("list_price"):
        improved["list_price"] = improved["sale_price"]
    if improved.get("list_price") and not improved.get("sale_price"):
        improved["sale_price"] = improved["list_price"]

    if _score(improved) > _score(row) or ((improved.get("sale_price") or improved.get("list_price")) and _suspicious_price(row.get("sale_price") or row.get("list_price"))):
        improved["status"] = "success"
        improved["parse_mode"] = "search-fallback"
        improved["error"] = None
        row = improved

    # 그래도 가격이 없을 때만 playwright 시도
    if extract_kyobo_prices_playwright is not None and row.get("sale_price") is None and row.get("list_price") is None:
        try:
            final_url2, html2, list2, sale2 = extract_kyobo_prices_playwright(url)
            if list2 is not None:
                row["list_price"] = list2
            if sale2 is not None:
                row["sale_price"] = sale2
            if row.get("sale_price") and not row.get("list_price"):
                row["list_price"] = row["sale_price"]
            if row.get("list_price") and not row.get("sale_price"):
                row["sale_price"] = row["list_price"]
            if row.get("sale_price") or row.get("list_price"):
                row["parse_mode"] = "playwright"
        except Exception:
            pass

    # 품절 오판 제거
    row["status"] = "success"
    row["error"] = None
    return row
