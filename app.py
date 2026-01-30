import re
import base64
import pandas as pd
import streamlit as st

from parsers import parse_any
from utils.excel import to_xlsx_bytes

st.set_page_config(page_title="도서 URL 자동완성", layout="wide")

# ---------- 스타일 (섹션 3 헤더 정렬 + 버튼 높이 통일) ----------
st.markdown(
    """
<style>
/* 섹션 헤더(3) 한 줄 정렬 */
.section3-row h3 { margin: 0 !important; padding: 0 !important; line-height: 1.15; }
.section3-row { margin-top: 0.25rem; margin-bottom: 0.25rem; }

/* 버튼 높이 통일 */
.section3-row button, .section3-row a.fake-dl-btn {
  height: 42px !important;
  display: inline-flex !important;
  align-items: center !important;
  gap: 8px !important;
  padding: 0 14px !important;
  border-radius: 10px !important;
  border: 1px solid rgba(49, 51, 63, 0.2) !important;
  background: white !important;
  cursor: pointer !important;
  font-size: 15px !important;
}

/* Streamlit 기본 버튼 약간 위로 끌어올려 제목과 기준선 맞추기 */
.section3-row div[data-testid="stButton"] { margin-top: -10px; }
.section3-row div[data-testid="stMarkdown"] { margin-top: -2px; }

/* 커스텀 다운로드 버튼(링크) 텍스트/밑줄 제거 */
.section3-row a.fake-dl-wrap { text-decoration: none; }

/* 커스텀 다운로드 버튼 hover */
.section3-row a.fake-dl-btn:hover { border-color: rgba(49, 51, 63, 0.35) !important; }

/* URL 입력 팁을 조금 더 붙여보기 */
.url-tip { margin-top: -6px; color: rgba(49, 51, 63, 0.65); font-size: 0.9rem; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------- 타이틀 ----------
st.title("📚 도서 정보 자동 채움")
st.caption(
    "URL을 입력하고 도서 정보 가져오기 버튼을 클릭하면 ISBN/도서명/저자/출판사/가격이 자동으로 채워집니다. 결과는 누적해 엑셀로 다운로드할 수 있습니다."
)

with st.expander("✅ 지원 서점 / 사용 방법 / 주의", expanded=False):
    st.markdown(
        """
- 지원: **교보문고 / YES24 / 알라딘 / 영풍문고**
- 사용:
  1) 사용할 서점을 토글로 선택  
  2) 상품 URL을 붙여넣기 (여러 줄/여러 개 URL 동시 붙여넣기 가능)  
  3) **도서 정보 가져오기** → 테이블 누적  
  4) (누적 결과 옆) **엑셀 다운로드**
- 주의:
  - 일부 서점은 **동적 렌더링/봇 차단**으로 일반 요청 파싱이 실패할 수 있습니다.
  - 이 앱은 그런 경우를 대비해 **Playwright(헤드리스 브라우저) 백업 파싱**을 자동으로 사용합니다.
        """
    )

# ---------- 세션 상태 ----------
if "rows" not in st.session_state:
    st.session_state.rows = []

# URL 입력값 (자동 줄바꿈/정리용)
if "urls_text" not in st.session_state:
    st.session_state.urls_text = ""

def normalize_urls_from_text(text: str) -> list[str]:
    # 공백/탭/줄바꿈 혼합 입력을 URL 단위로 안전하게 정리
    if not text:
        return []
    # 줄바꿈/탭을 공백으로 치환 후, 공백 기준으로 쪼개되 http(s)만 필터
    chunks = re.split(r"[\s]+", text.strip())
    urls = [c.strip() for c in chunks if re.match(r"^https?://", (c or "").strip())]
    # 중복 제거(순서 유지)
    seen, out = set(), []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out

def normalize_text_for_textarea(text: str) -> str:
    urls = normalize_urls_from_text(text)
    if not urls:
        return (text or "")
    # 한 줄에 하나 + 마지막 개행(커서 다음 줄 유도)
    return "\n".join(urls) + "\n"

# 붙여넣기 후 자동 정리 (다음 rerun에서 정리된 형태로 바뀜)
st.session_state.urls_text = normalize_text_for_textarea(st.session_state.urls_text)

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

# ---------- 상단 입력 영역 ----------
colA, colB = st.columns([1, 2], vertical_alignment="top")

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
        key="urls_text",
        height=140,
        placeholder="예)\nhttps://www.yes24.com/Product/Goods/168226997\nhttps://product.kyobobook.co.kr/detail/S000218972540\nhttps://www.aladin.co.kr/shop/wproduct.aspx?ItemId=376765918\nhttps://www.ypbooks.co.kr/books/202512185684862499?idKey=33",
    )
    st.markdown('<div class="url-tip">TIP: URL을 붙여넣으면 자동으로 한 줄에 하나씩 정리됩니다. (여러 URL 동시 입력 가능)</div>', unsafe_allow_html=True)
    run = st.button("🚀 도서 정보 가져오기", type="primary")

# ---------- 실행/누적 ----------
def clear_rows():
    st.session_state.rows = []
    st.toast("누적 데이터를 초기화했어요.", icon="🧹")

if run:
    urls = normalize_urls_from_text(urls_text)
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

# ---------- 섹션 3: 누적 결과 + 버튼(초기화/엑셀) ----------
# 아이콘: 파란 다운로드 느낌(간단 SVG)
DOWNLOAD_SVG = """<svg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none'>
<path d='M12 3v10' stroke='#1E88E5' stroke-width='2' stroke-linecap='round'/>
<path d='M8 11l4 4 4-4' stroke='#1E88E5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/>
<path d='M4 17h16' stroke='#1E88E5' stroke-width='2' stroke-linecap='round'/>
</svg>"""
DOWNLOAD_SVG_B64 = base64.b64encode(DOWNLOAD_SVG.encode("utf-8")).decode("utf-8")

# 헤더 바
left, mid, right = st.columns([2.2, 1.3, 2.5], vertical_alignment="center")
with left:
    st.markdown('<div class="section3-row"><h3>3) 누적 결과</h3></div>', unsafe_allow_html=True)

with mid:
    # 버튼이 제목보다 살짝 아래로 느껴지는 문제를 CSS로 당겨 맞춤
    if st.button("🧹 누적 초기화", key="clear_top"):
        clear_rows()

with right:
    if st.session_state.rows:
        df_raw = pd.DataFrame(st.session_state.rows)
        xbytes = to_xlsx_bytes(df_raw)
        b64 = base64.b64encode(xbytes).decode("utf-8")
        fname = "도서_자동완성_결과.xlsx"
        st.markdown(
            f"""
<div class="section3-row">
  <a class="fake-dl-wrap" download="{fname}" href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}">
    <span class="fake-dl-btn">
      <img alt="download" src="data:image/svg+xml;base64,{DOWNLOAD_SVG_B64}" />
      결과 엑셀(.xlsx) 다운로드
    </span>
  </a>
</div>
""",
            unsafe_allow_html=True,
        )

st.divider()

# ---------- 테이블 ----------
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
else:
    st.info("아직 누적된 데이터가 없어요. URL을 입력하고 **도서 정보 가져오기**를 눌러보세요.")
