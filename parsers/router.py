from typing import Dict

from .yes24 import parse_yes24
from .aladin import parse_aladin
from .kyobo import parse_kyobo
from .ypbooks import parse_ypbooks


def detect_site(url: str) -> str:
    u = url.lower()
    if "yes24.com" in u:
        return "YES24"
    if "aladin.co.kr" in u:
        return "ALADIN"
    if "kyobobook.co.kr" in u:
        return "KYobo"
    if "ypbooks.co.kr" in u:
        return "YPBOOKS"
    return "UNKNOWN"


def parse_any(url: str, enabled_sites: Dict[str, bool]) -> dict:
    site = detect_site(url)

    if site in enabled_sites and not enabled_sites.get(site, True):
        return {
            "site": site,
            "url": url,
            "status": "skipped",
            "error": "해당 서점이 비활성화(토글 OFF) 상태라 건너뛰었습니다.",
            "parse_mode": "skipped",
        }

    try:
        if site == "YES24":
            return parse_yes24(url)
        if site == "ALADIN":
            return parse_aladin(url)
        if site == "KYobo":
            return parse_kyobo(url)
        if site == "YPBOOKS":
            return parse_ypbooks(url)
        return {
            "site": site,
            "url": url,
            "status": "failed",
            "error": "지원하지 않는 URL 도메인입니다.",
            "parse_mode": "unknown",
        }
    except Exception as e:
        return {
            "site": site,
            "url": url,
            "status": "failed",
            "error": f"예외 발생: {type(e).__name__}: {e}",
            "parse_mode": "exception",
        }
