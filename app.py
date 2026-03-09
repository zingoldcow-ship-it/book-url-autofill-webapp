import re
import pandas as pd
import streamlit as st

from parsers import parse_any
from utils.excel import to_xlsx_bytes

st.set_page_config(page_title="도서 URL 자동완성", layout="wide")

st.title("📚 도서 URL 자동완성 웹앱 (완전체 v5)")
st.caption("서점 상품 URL만 붙여넣으면 ISBN/도서명/저자/출판사/가격 정보가 자동으로 채워지고, 누적 후 엑셀로 내려받을 수 있어요.")

with st.expander("✅ 지원 서점 / 사용 방법 / 주의", expanded=False):
    st.markdown(
        """
- 지원: **교보문고 / YES24 / 알라딘 / 영풍문고**
- 사용:
  1) 사용할 서점을 토글로 선택  
  2) 상품 URL을 한 줄에 하나씩 입력(여러 줄 붙여넣기 가능)  
  3) **파싱 실행** → 테이블 누적  
  4) **엑셀 다운로드**  
- 주의:
  - 일부 서점은 **동적 렌더링/봇 차단**으로 일반 요청 파싱이 실패할 수 있습니다.
  - 이 앱은 기본적으로 **requests 기반 파싱**을 사용하며, 배포 안정화를 위해 브라우저 의존성은 제거했습니다.
        """
    )

if "rows" not in st.session_state:
    st.session_state.rows = []

colA, colB = st.columns([1, 2])

with colA:
    st.subheader("1) 서점 선택")
    use_kyobo = st.toggle("교보문고", value=True)
    use_yes24 = st.toggle("YES24", value=True)
    use_aladin = st.toggle("알라딘", value=True)
    use_yp = st.toggle("영풍문고", value=True)
    enabled_sites = {"KYobo": use_kyobo, "YES24": use_yes24, "ALADIN": use_aladin, "YPBOOKS": use_yp}

with colB:
    st.subheader("2) URL 입력")
    urls_text = st.text_area(
        "한 줄에 하나씩 상품 URL을 붙여넣으세요.",
        height=140,
        placeholder="예)\nhttps://www.yes24.com/Product/Goods/168226997\nhttps://product.kyobobook.co.kr/detail/S000218972540\nhttps://www.aladin.co.kr/shop/wproduct.aspx?ItemId=376765918\nhttps://www.ypbooks.co.kr/books/202512185684862499?idKey=33",
    )

btn1, btn2, btn3 = st.columns([1, 1, 2])
with btn1:
    run = st.button("🚀 파싱 실행", type="primary")
with btn2:
    clear = st.button("🧹 누적 초기화")
with btn3:
    st.caption("TIP: URL을 여러 줄 붙여넣고 한 번에 실행하면 편해요.")

if clear:
    st.session_state.rows = []
    st.toast("누적 데이터를 초기화했어요.", icon="🧹")

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
PARSEMODE_KO = {"requests": "자동", "playwright": "브라우저", "fallback": "자동(안정화)", "skipped": "제외", "unknown": "알수없음", "exception": "오류"}
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

st.subheader("3) 누적 결과")
if st.session_state.rows:
    df_raw = pd.DataFrame(st.session_state.rows)

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

    st.subheader("4) 엑셀 다운로드")
    xbytes = to_xlsx_bytes(df_raw)
    st.download_button(
        "⬇️ 결과 엑셀(.xlsx) 다운로드",
        data=xbytes,
        file_name="도서_자동완성_결과.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="secondary",
    )
else:
    st.info("아직 누적된 데이터가 없어요. URL을 입력하고 **파싱 실행**을 눌러보세요.")
