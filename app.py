import re
import pandas as pd
import streamlit as st

from parsers import parse_any
from utils.excel import to_xlsx_bytes

st.set_page_config(page_title="도서 정보 자동 채움 웹앱", layout="wide")

st.title("📚 도서 정보 자동 채움 웹앱")
st.caption("URL을 입력하고 도서 정보 가져오기 버튼을 클릭하면 ISBN/도서명/저자/출판사/가격이 자동으로 채워집니다. 결과는 누적해 엑셀로 다운로드할 수 있습니다.")

with st.expander("✅ 지원서점 / 사용방법 / 참고사항", expanded=True):
    st.markdown(
        """
- **지원서점:** 교보문고 / YES24 / 알라딘 / 영풍문고

- **사용방법:**
  1. 구매할 서점을 체크박스에서 선택
  2. 도서 상품 URL을 **한 줄에 하나씩 붙여넣기**
  3. **도서 정보 가져오기** 버튼 클릭
  4. 도서 정보가 자동으로 처리되면 아래 표로 누적
  5. 교사는 결과를 확인하고, **결과 엑셀(.xlsx) 다운로드** 버튼을 클릭한 뒤, 사용

- **참고사항:**
  - 일부 서점은 동적 렌더링/봇 차단으로 일반 요청 파싱이 실패할 수 있습니다.
  - 이 앱은 그런 경우를 대비해 **Playwright(헤드리스 브라우저)** 백업 파싱을 자동으로 사용합니다.
"""
    )

st.divider()

if "rows" not in st.session_state:
    st.session_state.rows = []

left_col, right_col = st.columns([1, 2], gap="large")

with left_col:
    st.subheader("🔒 서점 선택")
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
    st.subheader("🔗 URL 입력")
    urls_text = st.text_area(
        "한 줄에 하나씩 상품 URL을 붙여넣으세요.",
        height=150,
        placeholder="""예)
https://www.yes24.com/Product/Goods/168226997
https://product.kyobobook.co.kr/detail/S000218975240
https://www.aladin.co.kr/shop/wproduct.aspx?ItemId=37675918
https://www.ypbooks.co.kr/books/202512185684862499?idKey=33""",
        label_visibility="visible",
    )
    st.caption("TIP: URL을 붙여넣으면 자동으로 한 줄에 하나씩 정리됩니다. (여러 URL 동시 입력 가능)")
    run = st.button("📕 도서 정보 가져오기", type="primary")

st.divider()

def normalize_urls(text: str) -> list[str]:
    urls = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if not re.match(r"^https?://", line):
            continue
        urls.append(line)

    seen = set()
    out = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
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


if run:
    urls = normalize_urls(urls_text)

    if not any(enabled_sites.values()):
        st.warning("먼저 구매할 서점을 1개 이상 선택해 주세요.")
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

        existing = {str(r.get("isbn")).strip() for r in st.session_state.rows if r.get("isbn")}
        for row in new_rows:
            isbn = str(row.get("isbn")).strip() if row.get("isbn") else ""
            if isbn and isbn in existing:
                row["note"] = "⚠ 이미 추가된 도서"
            elif isbn:
                existing.add(isbn)

        st.session_state.rows.extend(new_rows)
        st.success(f"{len(new_rows)}개 URL을 처리했어요. (신규 {len(new_rows)}개 / 0개 업데이트)")

st.subheader("📊 누적 결과")

top_btn_col1, top_btn_col2 = st.columns([1, 2])

with top_btn_col1:
    if st.button("🧹 누적 초기화"):
        st.session_state.rows = []
        st.rerun()

with top_btn_col2:
    if st.session_state.rows:
        raw_df_for_download = pd.DataFrame(st.session_state.rows)
        xbytes = to_xlsx_bytes(raw_df_for_download)
        st.download_button(
            "📥 결과 엑셀(.xlsx) 다운로드",
            data=xbytes,
            file_name="도서_자동완성_결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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

    preferred_cols = [
        "서점", "상품 URL", "처리상태", "ISBN", "도서명", "저자", "출판사",
        "정가", "판매가", "상품ID", "처리방식", "오류", "비고"
    ]
    cols = [c for c in preferred_cols if c in df_view.columns] + [c for c in df_view.columns if c not in preferred_cols]
    st.dataframe(df_view[cols], use_container_width=True, hide_index=True)
else:
    st.info("아직 누적된 데이터가 없어요. 구매할 서점을 선택하고 URL을 입력한 뒤, 도서 정보 가져오기를 눌러보세요.")
