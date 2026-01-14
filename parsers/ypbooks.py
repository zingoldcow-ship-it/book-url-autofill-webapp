import re
from .common import fetch_html, soup, extract_jsonld, pick_booklike, parse_price
from .render import fetch_html_playwright


def _parse_from_html(site: str, final_url: str, html: str, product_id: str | None) -> dict:
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

    status = "success" if (title or isbn or sale_price) else "failed"
    err = None if status == "success" else "필수 정보를 찾지 못했습니다(차단/동적 렌더링 가능)."

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


def parse_ypbooks(url: str) -> dict:
    m = re.search(r"/books/(\d+)", url)
    product_id = m.group(1) if m else None

    final_url, html = fetch_html(url)
    row = _parse_from_html("YPBOOKS", final_url, html, product_id)
    row["parse_mode"] = "requests"
    if row["status"] == "success":
        return row

    final_url2, html2 = fetch_html_playwright(url)
    row2 = _parse_from_html("YPBOOKS", final_url2, html2, product_id)
    row2["parse_mode"] = "playwright"
    return row2
