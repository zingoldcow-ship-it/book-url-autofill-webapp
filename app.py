
import re
import pandas as pd
import streamlit as st

from parsers import parse_any
from utils.excel import to_xlsx_bytes

st.set_page_config(page_title="도서 정보 자동 채움 웹앱", layout="wide")

st.title("📚 도서 정보 자동 채움 웹앱")

with st.expander("✅ 지원서점 / 사용방법 / 참고사항", expanded=True):
    st.markdown(
    '''
**지원서점:** 교보문고 / YES24 / 알라딘 / 영풍문고  

### 사용방법
1. 구매할 서점을 체크박스에서 선택  
2. 도서 상품 URL을 **한 줄에 하나씩 붙여넣기**  
3. **도서 정보 가져오기** 버튼 클릭  
4. 자동으로 아래 표에 누적 정리  
5. **결과 엑셀(.xlsx) 다운로드 버튼** 클릭하여 사용  

### 참고사항
- 일부 서점은 동적 렌더링/봇 차단으로 일반 요청 파싱이 실패할 수 있습니다.
- 이 앱은 그런 경우를 대비해 **Playwright(헤드리스 브라우저)** 백업 파싱을 자동으로 사용합니다.
'''
    )

st.divider()

if "rows" not in st.session_state:
    st.session_state.rows = []

col1, col2 = st.columns([1,2])

with col1:
    st.subheader("🔒 서점 선택")
    use_kyobo = st.checkbox("교보문고", value=True)
    use_yes24 = st.checkbox("YES24", value=True)
    use_aladin = st.checkbox("알라딘", value=True)
    use_yp = st.checkbox("영풍문고", value=True)

with col2:
    st.subheader("🔗 URL 입력")

    urls_text = st.text_area(
        "한 줄에 하나씩 상품 URL을 붙여넣으세요.",
        height=160,
        placeholder="""예)
https://www.yes24.com/Product/Goods/168226997
https://product.kyobobook.co.kr/detail/S000218975240
https://www.aladin.co.kr/shop/wproduct.aspx?ItemId=37675918
https://www.ypbooks.co.kr/books/2025121856848624991"""
    )

    run = st.button("📕 도서 정보 가져오기", type="primary")

st.divider()

def normalize_urls(text):
    urls = []
    for line in (text or "").splitlines():
        line=line.strip()
        if not line:
            continue
        if not re.match(r"^https?://", line):
            continue
        urls.append(line)
    return urls

if run:
    urls = normalize_urls(urls_text)
    for url in urls:
        try:
            data = parse_any(url)
            st.session_state.rows.append(data)
        except Exception as e:
            st.session_state.rows.append({
                "상품URL": url,
                "처리상태": "실패",
                "오류": str(e)
            })

st.subheader("📊 누적 결과")

colA, colB = st.columns([1,2])

with colA:
    if st.button("🧹 누적 초기화"):
        st.session_state.rows = []

with colB:
    if st.session_state.rows:
        df = pd.DataFrame(st.session_state.rows)
        xlsx = to_xlsx_bytes(df)

        st.download_button(
            "📥 결과 엑셀(.xlsx) 다운로드",
            xlsx,
            file_name="book_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if st.session_state.rows:
    df = pd.DataFrame(st.session_state.rows)
    st.dataframe(df, use_container_width=True)
