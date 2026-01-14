import json
import re
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_html(url: str, timeout: int = 20) -> Tuple[str, str]:
    """Fetch HTML via requests. Returns (final_url, html_text)."""
    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.url, resp.text


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def first_text(el) -> Optional[str]:
    if not el:
        return None
    t = el.get_text(" ", strip=True)
    return t if t else None


def parse_price(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def extract_jsonld(s: BeautifulSoup) -> list[dict]:
    blocks = []
    for tag in s.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        raw = raw.strip()
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                blocks.append(obj)
            elif isinstance(obj, list):
                blocks.extend([x for x in obj if isinstance(x, dict)])
        except Exception:
            continue
    return blocks


def pick_booklike(jsonlds: list[dict]) -> Optional[dict]:
    for obj in jsonlds:
        t = obj.get("@type")
        if isinstance(t, list):
            t = " ".join(map(str, t))
        if t and any(k in str(t).lower() for k in ["book", "product"]):
            return obj

    for obj in jsonlds:
        graph = obj.get("@graph")
        if isinstance(graph, list):
            for node in graph:
                if isinstance(node, dict):
                    t = node.get("@type")
                    if t and any(k in str(t).lower() for k in ["book", "product"]):
                        return node
    return None
