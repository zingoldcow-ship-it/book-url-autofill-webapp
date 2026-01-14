import re
from .common import fetch_html, soup, extract_jsonld, pick_booklike, parse_price, scan_prices_from_text, scan_isbn
from .render import fetch_html_playwright

def _parse_from_html(final_url: str, html: str, product_id: str | None) -> dict:
    s = soup(html)
    book = pick_booklike(extract_jsonld(s)) or {}
    title = book.get("name") or None
    author=None; publisher=None; isbn=None
    list_price=None; sale_price=None

    a = book.get("author")
    if isinstance(a, dict): author=a.get("name")
    elif isinstance(a, list):
        names=[]
        for it in a:
            if isinstance(it, dict) and it.get("name"): names.append(it.get("name"))
            elif isinstance(it, str): names.append(it)
        author=", ".join(names) if names else None
    elif isinstance(a, str): author=a

    p = book.get("publisher")
    if isinstance(p, dict): publisher=p.get("name")
    elif isinstance(p, str): publisher=p

    identifiers = book.get("isbn") or book.get("ISBN") or None
    if isinstance(identifiers, str): isbn=identifiers

    offers = book.get("offers")
    if isinstance(offers, dict):
        list_price=parse_price(str(offers.get("price")) if offers.get("price") is not None else None)
        sale_price=list_price

    if not title:
        og=s.find("meta", property="og:title")
        title=og.get("content").strip() if og and og.get("content") else None

    text=s.get_text(" ", strip=True)

    if not isbn:
        isbn = scan_isbn(text)

    if list_price is None or sale_price is None:
        lp, sp = scan_prices_from_text(text)
        list_price = list_price or lp
        sale_price = sale_price or sp

    status="success" if (title or isbn) and (sale_price is not None or list_price is not None) else "failed"
    err=None if status=="success" else "필수 정보를 찾지 못했습니다(페이지 구조/차단 가능)."

    return {"site":"YES24","url":final_url,"status":status,"product_id":product_id,
            "isbn":isbn,"title":title,"author":author,"publisher":publisher,
            "list_price":list_price,"sale_price":sale_price,"error":err}

def parse_yes24(url: str) -> dict:
    m=re.search(r"/Goods/(\d+)", url)
    product_id=m.group(1) if m else None
    final_url, html = fetch_html(url)
    row=_parse_from_html(final_url, html, product_id)
    row["parse_mode"]="requests"
    if row["status"]=="success": return row
    final_url2, html2 = fetch_html_playwright(url)
    row2=_parse_from_html(final_url2, html2, product_id)
    row2["parse_mode"]="playwright"
    return row2
