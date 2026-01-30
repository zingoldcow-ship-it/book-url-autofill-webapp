import re
import pandas as pd
import streamlit as st

from parsers import parse_any
from utils.excel import to_xlsx_bytes

st.set_page_config(page_title="도서 URL 자동완성", layout="wide")

st.markdown(
    """
<style>
/* 버튼 크기/높이 통일: '누적 초기화' & '엑셀 다운로드'를 제목 높이와 맞춤 */
div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button {
  height: 44px;
  font-size: 1rem;
  padding: 0.35rem 0.9rem;
}
/* 헤더(3) 제목과 버튼 세로 정렬 보정 */
.v-align-44 { line-height: 44px; margin: 0; padding: 0; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("📚 도서 정보 자동 채움")
st.caption("URL을 입력하고 도서 정보 가져오기 버튼을 클릭하면 ISBN/도서명/저자/출판사/가격이 자동으로 채워집니다. 결과는 누적해 엑셀로 다운로드할 수 있습니다.")

with st.expander("✅ 지원 서점 / 사용 방법 / 주의", expanded=False):
    st.markdown(
        """
- 지원: **교보문고 / YES24 / 알라딘 / 영풍문고**
- 사용:
  1) 사용할 서점을 토글로 선택  
  2) 상품 URL을 한 줄에 하나씩 입력(여러 줄 붙여넣기 가능)  
  3) **도서 정보 가져오기** → 테이블 누적  
  4) **엑셀 다운로드**  
- 주의:
  - 일부 서점은 **동적 렌더링/봇 차단**으로 일반 요청 파싱이 실패할 수 있습니다.
  - 이 앱은 그런 경우를 대비해 **Playwright(헤드리스 브라우저) 백업 파싱**을 자동으로 사용합니다.
        """
    )

if "rows" not in st.session_state:
    st.session_state.rows = []

if "urls_input" not in st.session_state:
    st.session_state.urls_input = ""

colA, colB = st.columns([1, 2])

with colA:
    st.subheader("1) 서점 선택")
    use_kyobo = st.toggle("교보문고", value=False)
    use_yes24 = st.toggle("YES24", value=False)
    use_aladin = st.toggle("알라딘", value=False)
    use_yp = st.toggle("영풍문고", value=False)
    enabled_sites = {"KYobo": use_kyobo, "YES24": use_yes24, "ALADIN": use_aladin, "YPBOOKS": use_yp}

with colB:
    st.subheader("2) URL 입력")
    urls_text = st.text_area(
        "한 줄에 하나씩 상품 URL을 붙여넣으세요.",
        key="urls_input",
        height=140,
        placeholder="""예)
https://www.yes24.com/Product/Goods/168226997
https://product.kyobobook.co.kr/detail/S000218972540
https://www.aladin.co.kr/shop/wproduct.aspx?ItemId=376765918
https://www.ypbooks.co.kr/books/202512185684862499?idKey=33""",
        on_change=_normalize_urls_input,
    )

    st.caption("TIP: URL을 붙여넣으면 자동으로 한 줄에 하나씩 정리됩니다. (여러 URL 동시 입력 가능)")
    run = st.button("🚀 도서 정보 가져오기", type="primary")


def _normalize_urls_input():
    text = st.session_state.get("urls_input", "") or ""
    # 붙여넣기 시 공백/탭으로 들어온 URL도 자동으로 한 줄에 하나씩 정리 + 마지막에 개행 추가
    candidates = re.findall(r"https?://[^\s]+", text)
    cleaned = []
    for u in candidates:
        u = u.strip().strip('"').strip("'")
        u = u.rstrip(").,;")
        cleaned.append(u)
    out, seen = [], set()
    for u in cleaned:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    new_text = "\n".join(out)
    if new_text and not new_text.endswith("\n"):
        new_text += "\n"
    st.session_state["urls_input"] = new_text


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
PARSEMODE_KO = {"requests": "자동", "playwright": "브라우저", "skipped": "제외", "unknown": "알수없음", "exception": "오류"}
COLUMN_KO = {
    "site": "서점", "url": "상품 URL", "status": "처리상태", "isbn": "ISBN", "title": "도서명",
    "author": "저자", "publisher": "출판사", "list_price": "정가", "sale_price": "판매가",
    "product_id": "상품ID", "parse_mode": "처리방식", "error": "오류", "note": "비고",
}
SITE_KO = {"KYobo": "교보문고", "YES24": "YES24", "ALADIN": "알라딘", "YPBOOKS": "영풍문고"}

if run:
    urls = normalize_urls(urls_text)
    if not urls:
        st.warning("유효한 URL이 없어요. http(s)로 시작하는 상품 URL을 입력해 주세요.")
    else:
        progress = st.progress(0, text="파싱 중...")
        new_rows = []
        for i, url in enumerate(urls, start=1):
            new_rows.append(parse_any(url, enabled_sites=enabled_sites))
            progress.progress(i / len(urls), text=f"파싱 중... ({i}/{len(urls)})")
        progress.empty()

        existing = {str(r.get("isbn")).strip() for r in st.session_state.rows if r.get("isbn")}
        for r in new_rows:
            isbn = str(r.get("isbn")).strip() if r.get("isbn") else ""
            if isbn and isbn in existing:
                r["note"] = "⚠ 이미 추가된 도서"
            elif isbn:
                existing.add(isbn)

        st.session_state.rows.extend(new_rows)
        st.success(f"{len(new_rows)}개 URL을 처리했어요. 아래 테이블에 누적되었습니다.")

# 3) 누적 결과 (제목 옆에 '누적 초기화' + 처리 완료 시 '엑셀 다운로드' 버튼 표시)
h1, h2, h3 = st.columns([1, 0.18, 0.32], gap="small")
with h1:
    st.markdown('<h3 class="v-align-44">3) 누적 결과</h3>', unsafe_allow_html=True)

with h2:
    clear2 = st.button("🧹 누적 초기화", key="clear_accum")

# 다운로드 버튼은 누적 데이터가 있을 때만 노출 (4) 섹션 문구는 제거)
with h3:
    download_clicked = False  # placeholder

if clear2:
    st.session_state.rows = []
    st.toast("누적 데이터를 초기화했어요.", icon="🧹")
    st.rerun()

if st.session_state.rows:
    df_raw = pd.DataFrame(st.session_state.rows)

    # 엑셀 다운로드 버튼 (누적 초기화 옆)
    xbytes = to_xlsx_bytes(df_raw)
    with h3:
        st.download_button(
            "⬇️ 결과 엑셀(.xlsx) 다운로드",
            data=xbytes,
            file_name="도서_자동완성_결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="secondary",
            key="download_xlsx",
        )

    df_view = df_raw.copy()
    if "site" in df_view.columns:
        df_view["site"] = df_view["site"].map(SITE_KO).fillna(df_view["site"])
    if "status" in df_view.columns:
        df_view["status"] = df_view["status"].map(STATUS_KO).fillna(df_view["status"])
    if "parse_mode" in df_view.columns:
        df_view["parse_mode"] = df_view["parse_mode"].map(PARSEMODE_KO).fillna(df_view["parse_mode"])

    for c in ["list_price", "sale_price"]:
        if c in df_view.columns:
            df_view[c] = df_view[c].apply(fmt_won)

    df_view = df_view.rename(columns=COLUMN_KO)

    preferred_cols = ["서점","상품 URL","처리상태","ISBN","도서명","저자","출판사","정가","판매가","비고","상품ID","처리방식","오류"]
    cols = [c for c in preferred_cols if c in df_view.columns] + [c for c in df_view.columns if c not in preferred_cols]
    st.dataframe(df_view[cols], use_container_width=True, hide_index=True)

    ok = df_raw[df_raw["status"] == "success"] if "status" in df_raw.columns else df_raw
    st.caption(f"성공: {len(ok)} / 전체: {len(df_raw)}")
else:
    st.info("아직 누적된 데이터가 없어요. URL을 입력하고 **도서 정보 가져오기**를 눌러보세요.")
