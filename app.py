import re
import pandas as pd
import streamlit as st

from parsers import parse_any
from utils.excel import to_xlsx_bytes

st.set_page_config(page_title="도서 정보 자동 채움 웹앱", layout="wide")

st.markdown(
    """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
h1, h2, h3, h4 {word-break: keep-all;}
div[data-testid="stButton"] button,
div[data-testid="stDownloadButton"] button {
    min-height: 44px;
    font-weight: 600;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("📚 도서 정보 자동 채움 웹앱")
st.caption(
    "URL을 입력하고 도서 정보 가져오기 버튼을 클릭하면 ISBN/도서명/저자/출판사/가격이 자동으로 채워집니다. "
    "결과는 누적해 엑셀로 다운로드할 수 있습니다."
)

with st.expander("✅ 지원서점 / 사용방법 / 참고사항", expanded=True):
    st.markdown(
        """
- **지원서점:** 교보문고 / YES24 / 알라딘 / 영풍문고
- **사용방법**
  1. 구매할 서점을 **체크박스에서 선택**
  2. 도서 상품 URL을 **한 줄에 하나씩 붙여넣기**
  3. **도서 정보 가져오기** 버튼 클릭
  4. 결과를 아래 표에서 확인
  5. **결과 엑셀(.xlsx) 다운로드** 버튼 클릭
- **참고사항**
  - 같은 URL을 다시 조회하면 **기존 행을 교체**합니다.
  - 일부 서점은 동적 렌더링/봇 차단으로 일반 요청 파싱이 실패할 수 있습니다.
  - 교보문고는 requests 기반 수집을 우선 사용하고, 필요할 때만 보조 파싱을 시도합니다.
"""
    )

if "rows" not in st.session_state:
    st.session_state.rows = []

URLS_KEY = "urls_text"

def _normalize_urls_in_textarea() -> None:
    raw = st.session_state.get(URLS_KEY, "") or ""
    tokens = re.split(r"[\n\r\t\s]+", raw.strip())
    urls = [t.strip() for t in tokens if t.strip()]
    urls = [u for u in urls if re.match(r"^https?://", u)]
    seen, out = set(), []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    st.session_state[URLS_KEY] = "\n".join(out)

def normalize_urls(text: str) -> list[str]:
    urls = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if not re.match(r"^https?://", line):
            continue
        urls.append(line)
    seen, out = set(), []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out

def fmt_won(v):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    try:
        return f"{int(v):,}원"
    except Exception:
        return str(v)

STATUS_KO = {"success": "성공", "failed": "실패", "skipped": "제외"}
PARSEMODE_KO = {
    "requests": "자동",
    "playwright": "브라우저",
    "search-fallback": "검색보조",
    "skipped": "제외",
    "unknown": "알수없음",
    "exception": "오류",
}
COLUMN_KO = {
    "site": "서점",
    "url": "상품 URL",
    "status": "처리상태",
    "isbn": "ISBN",
    "title": "도서명",
    "author": "저자",
    "publisher": "출판사",
    "list_price": "정가",
    "sale_price": "판매가",
    "product_id": "상품ID",
    "parse_mode": "처리방식",
    "error": "오류",
    "note": "비고",
}
SITE_KO = {"KYobo": "교보문고", "YES24": "YES24", "ALADIN": "알라딘", "YPBOOKS": "영풍문고"}

def upsert_rows(existing_rows: list[dict], incoming_rows: list[dict]) -> tuple[list[dict], int, int]:
    index_by_url = {}
    for idx, row in enumerate(existing_rows):
        url = str(row.get("url") or "").strip()
        if url:
            index_by_url[url] = idx

    added = 0
    updated = 0
    for row in incoming_rows:
        url = str(row.get("url") or "").strip()
        if url and url in index_by_url:
            existing_rows[index_by_url[url]] = row
            updated += 1
        else:
            existing_rows.append(row)
            if url:
                index_by_url[url] = len(existing_rows) - 1
            added += 1
    return existing_rows, added, updated

left_col, right_col = st.columns([1, 2], gap="large")

with left_col:
    with st.container(border=True):
        st.subheader("🛒 서점 선택")
        use_kyobo = st.checkbox("교보문고", value=False)
        use_yes24 = st.checkbox("YES24", value=False)
        use_aladin = st.checkbox("알라딘", value=False)
        use_yp = st.checkbox("영풍문고", value=False)
        enabled_sites = {
            "KYobo": use_kyobo,
            "YES24": use_yes24,
            "ALADIN": use_aladin,
            "YPBOOKS": use_yp,
        }

with right_col:
    with st.container(border=True):
        st.subheader("🔗 URL 입력")
        st.text_area(
            "한 줄에 하나씩 상품 URL을 붙여넣으세요.",
            key=URLS_KEY,
            height=150,
            placeholder="예)\nhttps://product.kyobobook.co.kr/detail/S000219379560\nhttps://www.yes24.com/Product/Goods/90428162",
            on_change=_normalize_urls_in_textarea,
        )
        st.caption("TIP: 여러 URL을 한 번에 붙여넣어도 자동으로 한 줄에 하나씩 정리됩니다.")
        run = st.button("🚀 도서 정보 가져오기", type="primary")

if run:
    urls = normalize_urls(st.session_state.get(URLS_KEY, ""))
    if not any(enabled_sites.values()):
        st.warning("먼저 구매할 서점을 체크박스에서 1개 이상 선택해 주세요.")
    elif not urls:
        st.warning("유효한 URL이 없어요. http(s)로 시작하는 상품 URL을 입력해 주세요.")
    else:
        progress = st.progress(0, text="도서 정보를 가져오는 중...")
        new_rows = []
        for i, url in enumerate(urls, start=1):
            result = parse_any(url, enabled_sites=enabled_sites)
            new_rows.append(result)
            progress.progress(i / len(urls), text=f"도서 정보를 가져오는 중... ({i}/{len(urls)})")
        progress.empty()

        st.session_state.rows, added_cnt, updated_cnt = upsert_rows(st.session_state.rows, new_rows)

        seen_isbn = set()
        for row in st.session_state.rows:
            isbn = str(row.get("isbn") or "").strip()
            if not isbn:
                continue
            if isbn in seen_isbn:
                row["note"] = "⚠ 동일 ISBN 중복"
            else:
                if row.get("note") == "⚠ 동일 ISBN 중복":
                    row["note"] = None
                seen_isbn.add(isbn)

        st.success(f"{len(new_rows)}개 URL 처리 완료 · 신규 {added_cnt}개 / 업데이트 {updated_cnt}개")

with st.container(border=True):
    title_col, reset_col, download_col = st.columns([3.0, 1.3, 2.2], gap="medium")
    with title_col:
        st.subheader("📊 누적 결과")
    with reset_col:
        if st.button("🧹 누적 초기화", use_container_width=True):
            st.session_state.rows = []
            st.rerun()
    with download_col:
        if st.session_state.rows:
            df_for_excel = pd.DataFrame(st.session_state.rows)
            xbytes = to_xlsx_bytes(df_for_excel)
            st.download_button(
                "📥 결과 엑셀(.xlsx) 다운로드",
                data=xbytes,
                file_name="도서_자동완성_결과.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    if st.session_state.rows:
        df_raw = pd.DataFrame(st.session_state.rows)
        df_view = df_raw.copy()

        if "site" in df_view.columns:
            df_view["site"] = df_view["site"].map(SITE_KO).fillna(df_view["site"])
        if "status" in df_view.columns:
            df_view["status"] = df_view["status"].map(STATUS_KO).fillna(df_view["status"])
        if "parse_mode" in df_view.columns:
            df_view["parse_mode"] = df_view["parse_mode"].map(PARSEMODE_KO).fillna(df_view["parse_mode"])

        for col in ["list_price", "sale_price"]:
            if col in df_view.columns:
                df_view[col] = df_view[col].apply(fmt_won)

        df_view = df_view.rename(columns=COLUMN_KO)
        preferred_cols = ["서점","상품 URL","처리상태","ISBN","도서명","저자","출판사","정가","판매가","비고","상품ID","처리방식","오류"]
        cols = [c for c in preferred_cols if c in df_view.columns] + [c for c in df_view.columns if c not in preferred_cols]
        st.dataframe(df_view[cols], use_container_width=True, hide_index=True)

        ok = df_raw[df_raw["status"] == "success"] if "status" in df_raw.columns else df_raw
        st.caption(f"성공: {len(ok)} / 전체: {len(df_raw)}")
    else:
        st.info("아직 누적된 데이터가 없어요. URL을 입력하고 도서 정보 가져오기를 눌러보세요.")
