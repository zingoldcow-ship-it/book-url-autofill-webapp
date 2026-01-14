import json, re
from typing import Optional, Tuple
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
    # ISBN 키워드가 없어도 978/979로 시작하는 13자리 숫자를 찾음
    t = re.sub(r"\s+", " ", text)
    m = re.search(r"(97[89]\d{10})", t)
    return m.group(1) if m else None

def scan_publisher(text: str) -> Optional[str]:
    # '출판사' 뒤에 오는 값을 최대 20자 정도 잡기(너무 길면 자름)
    t = re.sub(r"\s+", " ", text)
    m = re.search(r"출판사\s*[:\-]?\s*([가-힣A-Za-z0-9·&()\- ]{2,30})", t)
    if not m:
        return None
    v = m.group(1).strip()
    # 자주 따라오는 라벨 제거
    v = re.split(r"(발행일|쪽수|정가|판매가|ISBN|저자)", v)[0].strip()
    return v[:30] if v else None

def scan_prices_from_text(text: str) -> tuple[Optional[int], Optional[int]]:
    t = re.sub(r"\s+", " ", text)

    def pick_after(keyword: str) -> Optional[int]:
        m = re.search(keyword + r".{0,40}?(\d[\d,]*)\s*원", t)
        return parse_price(m.group(1)) if m else None

    list_price = pick_after("정가")
    sale_price = pick_after("판매가") or pick_after("할인가") or pick_after("할인") or pick_after("판매 가격")

    if sale_price is None:
        m = re.search(r"(\d[\d,]{2,})\s*원", t)
        sale_price = parse_price(m.group(1)) if m else None

    return list_price, sale_price
