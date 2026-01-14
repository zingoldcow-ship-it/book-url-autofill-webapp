import re
import pandas as pd
import streamlit as st

from parsers import parse_any
from utils.excel import to_xlsx_bytes

st.set_page_config(page_title="도서 URL 자동완성", layout="wide")

st.title("📚 도서 URL 자동완성 웹앱 (완전체)")
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
  - 이 앱은 그런 경우를 대비해 **Playwright(헤드리스 브라우저) 백업 파싱**을 자동으로 사용합니다.
  - 첫 실행에서 Playwright 브라우저(Chromium)를 자동 설치할 수 있어요. 설치 중에는 몇 분 정도 더 걸릴 수 있습니다.
        """
    )

if "rows" not in st.session_state:
    st.session_state.rows = []  # list of dicts

colA, colB = st.columns([1, 2])

with colA:
    st.subheader("1) 서점 선택")
    use_kyobo = st.toggle("교보문고", value=True)
    use_yes24 = st.toggle("YES24", value=True)
    use_aladin = st.toggle("알라딘", value=True)
    use_yp = st.toggle("영풍문고", value=True)

    enabled_sites = {
        "KYobo": use_kyobo,
        "YES24": use_yes24,
        "ALADIN": use_aladin,
        "YPBOOKS": use_yp,
    }

with colB:
    st.subheader("2) URL 입력")
    urls_text = st.text_area(
        "한 줄에 하나씩 상품 URL을 붙여넣으세요.",
        height=140,
        placeholder="예)\nhttps://www.yes24.com/Product/Goods/168226997\nhttps://product.kyobobook.co.kr/detail/S000218972540\nhttps://www.aladin.co.kr/shop/wproduct.aspx?ItemId=376765918\nhttps://www.ypbooks.co.kr/books/202512185684862499?idKey=33",
    )

btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
with btn_col1:
    run = st.button("🚀 파싱 실행", type="primary")
with btn_col2:
    clear = st.button("🧹 누적 초기화")
with btn_col3:
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
    # de-duplicate while preserving order
    seen = set()
    out = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out

if run:
    urls = normalize_urls(urls_text)
    if not urls:
        st.warning("유효한 URL이 없어요. http(s)로 시작하는 상품 URL을 입력해 주세요.")
    else:
        progress = st.progress(0, text="파싱 중...")
        new_rows = []
        for i, url in enumerate(urls, start=1):
            row = parse_any(url, enabled_sites=enabled_sites)
            new_rows.append(row)
            progress.progress(i / len(urls), text=f"파싱 중... ({i}/{len(urls)})")
        progress.empty()
        st.session_state.rows.extend(new_rows)
        st.success(f"{len(new_rows)}개 URL을 처리했어요. 아래 테이블에 누적되었습니다.")

st.subheader("3) 누적 결과")
if st.session_state.rows:
    df = pd.DataFrame(st.session_state.rows)

    preferred_cols = [
        "site", "url", "status",
        "isbn", "title", "author", "publisher",
        "list_price", "sale_price",
        "product_id", "parse_mode", "error",
    ]
    cols = [c for c in preferred_cols if c in df.columns] + [c for c in df.columns if c not in preferred_cols]
    df = df[cols]

    st.dataframe(df, use_container_width=True, hide_index=True)

    ok = df[df["status"] == "success"] if "status" in df.columns else df
    st.caption(f"성공: {len(ok)} / 전체: {len(df)}")

    st.subheader("4) 엑셀 다운로드")
    xbytes = to_xlsx_bytes(df)
    st.download_button(
        "⬇️ 결과 엑셀(.xlsx) 다운로드",
        data=xbytes,
        file_name="도서_자동완성_결과.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="secondary",
    )
else:
    st.info("아직 누적된 데이터가 없어요. URL을 입력하고 **파싱 실행**을 눌러보세요.")
