import json, re
from typing import Optional, Tuple, Any
import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/121.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def fetch_html(url: str, timeout: int = 20) -> Tuple[str, str]:
    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.url, resp.text

def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")

def parse_price(text: Optional[str]) -> Optional[int]:
    if not text: return None
    digits = re.sub(r"[^\d]", "", text)
    if not digits: return None
    try: return int(digits)
    except ValueError: return None

def extract_jsonld(s: BeautifulSoup) -> list[dict]:
    blocks = []
    for tag in s.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = tag.string or tag.get_text()
        if not raw: continue
        raw = raw.strip()
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict): blocks.append(obj)
            elif isinstance(obj, list): blocks.extend([x for x in obj if isinstance(x, dict)])
        except Exception:
            continue
    return blocks

def pick_booklike(jsonlds: list[dict]) -> Optional[dict]:
    for obj in jsonlds:
        t = obj.get("@type")
        if isinstance(t, list): t = " ".join(map(str, t))
        if t and any(k in str(t).lower() for k in ["book","product"]): return obj
    for obj in jsonlds:
        graph = obj.get("@graph")
        if isinstance(graph, list):
            for node in graph:
                if isinstance(node, dict):
                    t = node.get("@type")
                    if t and any(k in str(t).lower() for k in ["book","product"]): return node
    return None

def scan_isbn(text: str) -> Optional[str]:
    t = re.sub(r"\s+", " ", text)
    m = re.search(r"(97[89]\d{10})", t)
    return m.group(1) if m else None

def scan_publisher(text: str) -> Optional[str]:
    t = re.sub(r"\s+", " ", text)
    m = re.search(r"출판사\s*[:\-]?\s*([가-힣A-Za-z0-9·&()\-\s]{2,30})", t)
    if not m:
        return None
    v = m.group(1).strip()
    v = re.split(r"(발행일|쪽수|정가|판매가|ISBN|저자)", v)[0].strip()
    return v[:30] if v else None

def scan_prices_from_text(text: str) -> tuple[Optional[int], Optional[int]]:
    t = re.sub(r"\s+", " ", text)
    banned = ["배송비", "적립", "포인트", "쿠폰", "회원가", "최대", "혜택", "캐시", "마일리지", "적립금", "할인쿠폰"]

    def pick_after(keyword: str) -> Optional[int]:
        m = re.search(keyword + r".{0,60}?(\d[\d,]*)\s*원", t)
        return parse_price(m.group(1)) if m else None

    list_price = pick_after("정가")
    sale_price = pick_after("판매가") or pick_after("할인가") or pick_after("할인") or pick_after("판매 가격")

    if sale_price is None:
        for m in re.finditer(r"(\d[\d,]{2,})\s*원", t):
            start = max(0, m.start() - 25)
            ctx = t[start:m.start()]
            if any(b in ctx for b in banned):
                continue
            sale_price = parse_price(m.group(1))
            if sale_price:
                break

    return list_price, sale_price

def _walk(obj: Any, path: str="") -> list[tuple[str, Any]]:
    items = []
    if isinstance(obj, dict):
        for k,v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            items.append((p,v))
            items.extend(_walk(v, p))
    elif isinstance(obj, list):
        for i,v in enumerate(obj):
            p = f"{path}[{i}]"
            items.append((p,v))
            items.extend(_walk(v, p))
    return items

def extract_next_data_prices(html: str) -> tuple[Optional[int], Optional[int]]:
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

    candidates = []
    keys_priority = [
        "salePrice","sellPrice","discountPrice","discountedPrice","finalPrice","purchasePrice",
        "price","sellingPrice","currentPrice","normalPrice","listPrice","standardPrice","origPrice"
    ]
    for p, v in _walk(data):
        if not isinstance(v, (int, float, str)):
            continue
        lower_p = p.lower()
        if not any(k.lower() in lower_p for k in keys_priority):
            continue
        val = int(v) if isinstance(v, (int, float)) else parse_price(v)
        if val is None:
            continue
        if 500 <= val <= 500000:
            candidates.append((p, val))

    if not candidates:
        return (None, None)

    def score(path: str, val: int) -> int:
        lp = path.lower()
        s = 0
        if "saleprice" in lp or "sellprice" in lp or "discount" in lp or "final" in lp:
            s += 100
        if "listprice" in lp or "standard" in lp or "normal" in lp or "orig" in lp:
            s += 50
        s += min(val // 100, 300)
        return s

    candidates.sort(key=lambda x: score(x[0], x[1]), reverse=True)
    sale_price = candidates[0][1]
    list_price = None
    for p,val in candidates:
        lp = p.lower()
        if any(k in lp for k in ["listprice","standard","normal","orig"]):
            list_price = val
            break
    if list_price is None:
        higher = [v for _,v in candidates if v >= sale_price]
        list_price = max(higher) if higher else sale_price

    return (list_price, sale_price)
