import re
from .common import fetch_html, soup, extract_jsonld, pick_booklike, parse_price
from .render import fetch_html_playwright


def _parse_from_html(site: str, final_url: str, html: str, product_id: str | None) -> dict:
    s = soup(html)

    book = pick_booklike(extract_jsonld(s)) or {}
    title = book.get("name") or None
    author = None
    publisher = None
    isbn = None
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

    publisher_obj = book.get("publisher")
    if isinstance(publisher_obj, dict):
        publisher = publisher_obj.get("name")
    elif isinstance(publisher_obj, str):
        publisher = publisher_obj

    identifiers = book.get("isbn") or book.get("ISBN") or None
    if isinstance(identifiers, str):
        isbn = identifiers

    offers = book.get("offers")
    if isinstance(offers, dict):
        list_price = parse_price(str(offers.get("price")) if offers.get("price") is not None else None)
        sale_price = list_price

    if not title:
        og = s.find("meta", property="og:title")
        title = og.get("content").strip() if og and og.get("content") else None

    if not isbn:
        text = s.get_text(" ", strip=True)
        m2 = re.search(r"ISBN\s*[:\-]?\s*(97[89]\d{10})", text)
        if m2:
            isbn = m2.group(1)

    # price fallback: if offers not found, try simple scan
    if sale_price is None:
        for txt in s.stripped_strings:
            if "원" in txt and any(ch.isdigit() for ch in txt):
                sale_price = parse_price(txt)
                if sale_price:
                    break
    if list_price is None:
        list_price = sale_price

    status = "success" if (title or isbn or sale_price) else "failed"
    err = None if status == "success" else "필수 정보를 찾지 못했습니다(페이지 구조/차단 가능)."

    return {
        "site": site,
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


def parse_aladin(url: str) -> dict:
    m = re.search(r"ItemId=(\d+)", url)
    product_id = m.group(1) if m else None

    final_url, html = fetch_html(url)
    row = _parse_from_html("ALADIN", final_url, html, product_id)
    row["parse_mode"] = "requests"
    if row["status"] == "success":
        return row

    final_url2, html2 = fetch_html_playwright(url)
    row2 = _parse_from_html("ALADIN", final_url2, html2, product_id)
    row2["parse_mode"] = "playwright"
    return row2
