
import streamlit as st
import pandas as pd
import base64

st.set_page_config(layout="wide")

if "results" not in st.session_state:
    st.session_state.results = []

st.markdown("""
<style>
.section-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 0.25rem;
}
.section-header h3 {
    margin: 0;
}
.header-buttons {
    display: flex;
    align-items: center;
    gap: 10px;
}
.header-buttons button {
    height: 42px;
    font-size: 15px;
}
</style>
""", unsafe_allow_html=True)

st.title("📚 도서 정보 자동 채움")

cols = st.columns([2.2, 6])
with cols[0]:
    st.markdown("""<div class="section-header"><h3>3) 누적 결과</h3></div>""", unsafe_allow_html=True)

with cols[1]:
    bcols = st.columns([1.2, 2.2])
    with bcols[0]:
        if st.button("🧹 누적 초기화"):
            st.session_state.results = []

    with bcols[1]:
        if st.session_state.results:
            with open("download_icon.png", "rb") as f:
                icon = base64.b64encode(f.read()).decode()

            csv = pd.DataFrame(st.session_state.results).to_csv(index=False).encode("utf-8-sig")
            b64 = base64.b64encode(csv).decode()

            st.markdown(f"""
            <a download="results.xlsx" href="data:text/csv;base64,{b64}" style="text-decoration:none">
                <button>
                    <img src="data:image/png;base64,{icon}" style="height:18px;vertical-align:middle;margin-right:6px"/>
                    결과 엑셀(.xlsx) 다운로드
                </button>
            </a>
            """, unsafe_allow_html=True)

st.divider()

if st.session_state.results:
    st.dataframe(pd.DataFrame(st.session_state.results), use_container_width=True)
else:
    st.info("아직 누적된 데이터가 없습니다.")
