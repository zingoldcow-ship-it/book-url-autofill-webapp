import re
import urllib.parse
import pandas as pd
import streamlit as st

from parsers import parse_any
from utils.excel import to_xlsx_bytes

st.set_page_config(page_title="도서 URL 자동완성", layout="wide")



st.markdown(
    """
<style>
/* ---------- Card UI (absolute bg) ---------- */

/* Make horizontal rows vertically centered (fix header + buttons alignment) */
div[data-testid="stHorizontalBlock"]{
    align-items: center;
}

/* Border wrapper: turn off Streamlit's own border/padding so our inner card controls visuals */
div[data-testid="stVerticalBlockBorderWrapper"]{
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div{
    padding: 0 !important;
}

/* Inner card base */
.card-base{
    border-radius: 18px;
    padding: 18px 20px 16px 20px;
    border: 1px solid rgba(0,0,0,0.07);
    box-shadow: 0 1px 8px rgba(0,0,0,0.05);
}

/* Card tones */
.card-blue{ background: #F2F6FF; }
.card-pink{ background: #FFF2F5; }
.card-yellow{ background: #FFF9E8; }

/* Card title */
.card-title{
    font-size: 1.55rem;
    font-weight: 800;
    line-height: 1.15;
    margin: 0 0 10px 0;
    white-space: nowrap;
    word-break: keep-all;
}

/* Prevent odd Korean word breaks globally */
h1,h2,h3,h4,h5,h6 { word-break: keep-all; }



/* ---------- Card UI (absolute bg) ---------- */
div[data-testid="stVerticalBlockBorderWrapper"]{
    position: relative !important;
    overflow: hidden !important;
    border-radius: 18px !important;
    border: 1px solid rgba(0,0,0,0.07) !important;
    box-shadow: 0 1px 8px rgba(0,0,0,0.05) !important;
    background: transparent !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div{
    padding: 18px 20px 16px 20px !important;
    position: relative !important;
    z-index: 1 !important;
}

/* Background layer that fills the whole card */
.card-bg{
    position: absolute;
    inset: 0;
    z-index: 0;
    border-radius: 18px;
}
.card-bg.blue{ background: #F2F6FF; }
.card-bg.pink{ background: #FFF2F5; }
.card-bg.yellow{ background: #FFF9E8; }

.card-title{
    font-size: 1.55rem;
    font-weight: 800;
    line-height: 1.15;
    margin: 0 0 10px 0;
    white-space: nowrap;
    word-break: keep-all;
}
h1,h2,h3,h4,h5,h6 { word-break: keep-all; }

/* Align header row items */
div[data-testid="stHorizontalBlock"]{ align-items: center; }
</style>
""",
    unsafe_allow_html=True,
)

# --- Global CSS: button heights + tighter header row ---
st.markdown(
    """
<style>
/* Make primary/secondary buttons visually consistent */
div[data-testid="stButton"] button,
div[data-testid="stDownloadButton"] button {
    height: 44px;
    padding: 0 16px;
    font-weight: 600;
}

/* Slightly reduce default gap above/below elements */
.block-container { padding-top: 2rem; }

/* --- Card system (uses :has() to color each bordered container) --- */
div[data-testid="stVerticalBlockBorderWrapper"]{
    border-radius: 18px !important;
    border: 1px solid rgba(0,0,0,0.07) !important;
    box-shadow: 0 1px 8px rgba(0,0,0,0.05) !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div{
    padding: 18px 20px 16px 20px !important;
}

/* card background tones */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.card-blue-marker) { background: #F2F6FF !important; }
div[data-testid="stVerticalBlockBorderWrapper"]:has(.card-pink-marker) { background: #FFF2F5 !important; }
div[data-testid="stVerticalBlockBorderWrapper"]:has(.card-yellow-marker){ background: #FFF9E8 !important; }

/* Card title */
.card-title{
    font-size: 1.55rem;
    font-weight: 800;
    line-height: 1.15;
    margin: 0 0 10px 0;
    white-space: nowrap;
    word-break: keep-all;
}

/* Prevent odd Korean word breaks in headings */
h1,h2,h3,h4,h5,h6 { word-break: keep-all; }

/* Remove top extra spacing inside containers created by markdown */
.card-marker{ height:0px; margin:0; padding:0; }

/* Highlight Excel download button */
div:has(.excel-dl-marker) div[data-testid="stDownloadButton"] button{
    background: #EAF2FF !important;
    border: 1px solid rgba(0,0,0,0.10) !important;
}
div:has(.excel-dl-marker) div[data-testid="stDownloadButton"] button:hover{
    filter: brightness(0.98);
}
</style>
""",
    unsafe_allow_html=True,
)
st.title("📚 도서 정보 자동 채움")
st.caption(
    "URL을 입력하고 도서 정보 가져오기 버튼을 클릭하면 ISBN/도서명/저자/출판사/가격이 자동으로 채워집니다. "
    "결과는 누적해 엑셀로 다운로드할 수 있습니다."
)

with st.expander("✅ 지원 서점 / 사용 방법 / 주의", expanded=False):
    st.markdown(
        """
- 지원: **교보문고 / YES24 / 알라딘 / 영풍문고**
- 사용:
  1) 사용할 서점을 토글로 선택  
  2) 상품 URL을 입력(여러 줄 붙여넣기 가능)  
  3) **도서 정보 가져오기** → 테이블 누적  
  4) 누적 결과에서 **엑셀 다운로드**
- 주의:
  - 일부 서점은 **동적 렌더링/봇 차단**으로 일반 요청 파싱이 실패할 수 있습니다.
  - 이 앱은 그런 경우를 대비해 **Playwright(헤드리스 브라우저) 백업 파싱**을 자동으로 사용합니다.
        """
    )

if "rows" not in st.session_state:
    st.session_state.rows = []

# ---------------------------
# URL 입력: 복사/붙여넣기 자동 정리 (1줄 1URL) + 마지막 개행 추가
# ---------------------------
URLS_KEY = "urls_text"

def _normalize_urls_in_textarea() -> None:
    raw = st.session_state.get(URLS_KEY, "") or ""
    # 1) 개행/탭/공백을 모두 줄바꿈 기준으로 정리
    #    (문서/메신저/엑셀 등에서 복붙 시 공백으로 붙는 케이스 대응)
    tokens = re.split(r"[\n\r\t\s]+", raw.strip())
    urls = [t.strip() for t in tokens if t.strip()]
    # 2) http(s)로 시작하는 것만 남김
    urls = [u for u in urls if re.match(r"^https?://", u)]
    # 3) 중복 제거 (순서 유지)
    seen, out = set(), []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)

    # 4) 다시 텍스트로 합치고, 마지막에 개행을 넣어 커서가 다음 줄로 가는 느낌 제공
    if out:
        st.session_state[URLS_KEY] = "\n".join(out) + "\n"
    else:
        st.session_state[URLS_KEY] = raw

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


def url_key(url: str) -> str:
    """중복 판정을 위한 URL 키 (트래킹 파라미터 제거 + 정규화)."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        p = urllib.parse.urlsplit(url)
        # remove common tracking params (utm_*, etc.)
        qs = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
        filtered = []
        for k, v in qs:
            lk = k.lower()
            if lk.startswith("utm_"):
                continue
            if lk in {"ref", "referer", "from", "source", "tracking", "track", "coupon"}:
                continue
            filtered.append((k, v))
        new_query = urllib.parse.urlencode(filtered, doseq=True)
        # normalize: lower netloc, remove trailing slash in path
        path = p.path.rstrip("/")
        return urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), path, new_query, ""))
    except Exception:
        return url


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

# ---------------------------
# Layout: Cards (Left = site toggles, Right = URL input + fetch button)
# ---------------------------
colA, colB = st.columns([1, 2], gap="large")

with colA:
    with st.container(border=True):
        st.markdown('<div class="card-bg blue"></div>', unsafe_allow_html=True)
        st.markdown('<div class="card-title">🛍️ 서점 선택</div>', unsafe_allow_html=True)
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # 기본 OFF
        use_kyobo = st.checkbox("교보문고", value=False)
        use_yes24 = st.checkbox("YES24", value=False)
        use_aladin = st.checkbox("알라딘", value=False)
        use_yp = st.checkbox("영풍문고", value=False)
        enabled_sites = {"KYobo": use_kyobo, "YES24": use_yes24, "ALADIN": use_aladin, "YPBOOKS": use_yp}

with colB:
    with st.container(border=True):
        st.markdown('<div class="card-bg pink"></div>', unsafe_allow_html=True)
        st.markdown('<div class="card-title">🔗 URL 입력</div>', unsafe_allow_html=True)

        st.text_area(
            "한 줄에 하나씩 상품 URL을 붙여넣으세요.",
            key=URLS_KEY,
            height=150,
            placeholder="예)\nhttps://www.yes24.com/Product/Goods/168226997\nhttps://product.kyobobook.co.kr/detail/S000218972540\nhttps://www.aladin.co.kr/shop/wproduct.aspx?ItemId=376765918\nhttps://www.ypbooks.co.kr/books/202512185684862499?idKey=33",
            on_change=_normalize_urls_in_textarea,
        )
        st.caption("TIP: URL을 붙여넣으면 자동으로 한 줄에 하나씩 정리됩니다. (여러 URL 동시 입력 가능)")
        run = st.button("🚀 도서 정보 가져오기", type="primary")
# ---------------------------
# Actions
# ---------------------------
if run:
    urls = normalize_urls(st.session_state.get(URLS_KEY, ""))
    if not urls:
        st.warning("유효한 URL이 없어요. http(s)로 시작하는 상품 URL을 입력해 주세요.")
    else:
        progress = st.progress(0, text="파싱 중...")
        new_rows = []
        for i, url in enumerate(urls, start=1):
            new_rows.append(parse_any(url, enabled_sites=enabled_sites))
            progress.progress(i / len(urls), text=f"파싱 중... ({i}/{len(urls)})")
        progress.empty()

        # --- 1) 기존 누적 결과에서 URL 기준 중복 정리 (마지막 1개만 남김) ---
        cleaned = []
        seen_keys = set()
        # 뒤에서부터 순회해서 마지막 항목을 우선 유지
        for row in reversed(st.session_state.rows):
            k = url_key(row.get("url", ""))
            if not k:
                cleaned.append(row)
                continue
            if k in seen_keys:
                continue
            seen_keys.add(k)
            cleaned.append(row)
        st.session_state.rows = list(reversed(cleaned))

        # 현재 누적된 URL → index 매핑
        url_to_idx = {}
        for idx, row in enumerate(st.session_state.rows):
            k = url_key(row.get("url", ""))
            if k:
                url_to_idx[k] = idx

        # --- 2) 이번에 파싱한 결과를 URL 기준으로 덮어쓰기(업데이트) / 신규는 추가 ---
        updated = 0
        appended = 0
        for r in new_rows:
            k = url_key(r.get("url", ""))
            if k and k in url_to_idx:
                # 기존 행 덮어쓰기
                prev = st.session_state.rows[url_to_idx[k]]
                r.setdefault("note", "")
                if not r["note"]:
                    r["note"] = "🔄 업데이트됨"
                st.session_state.rows[url_to_idx[k]] = r
                updated += 1
            else:
                st.session_state.rows.append(r)
                if k:
                    url_to_idx[k] = len(st.session_state.rows) - 1
                appended += 1

        # --- 3) ISBN 중복은 참고용으로만 표시(같은 URL 업데이트는 제외) ---
        isbn_seen = {}
        for i, row in enumerate(st.session_state.rows):
            isbn = str(row.get("isbn")).strip() if row.get("isbn") else ""
            if not isbn:
                continue
            if isbn in isbn_seen and url_key(st.session_state.rows[isbn_seen[isbn]].get("url","")) != url_key(row.get("url","")):
                # 이미 다른 URL(다른 서점 등)에서 같은 ISBN이 존재
                if not row.get("note"):
                    row["note"] = "⚠ 이미 추가된 도서"
            else:
                isbn_seen[isbn] = i

        st.success(f"{len(new_rows)}개 URL을 처리했어요. (신규 {appended}개 추가 / {updated}개 업데이트)")



# ---------------------------
# Section 3: 누적 결과 (Card)
# ---------------------------
with st.container(border=True):
    st.markdown('<div class="card-bg yellow"></div>', unsafe_allow_html=True)
    # ---------------------------
    # Section 3: Header + Buttons (Reset + Download) in same row, close to title
    # ---------------------------
    # 타이틀과 버튼 간격을 최대한 붙이기 위해, 첫 컬럼 폭을 줄이고 버튼 컬럼을 바로 옆에 배치합니다.
    h_col1, h_col2, h_col3, h_spacer = st.columns([1.05, 1.15, 1.90, 5.90])

    with h_col1:
        st.markdown('<div class="card-title">📊 누적 결과</div>', unsafe_allow_html=True)

    with h_col2:
        st.markdown("<div style='margin-top:-8px'></div>", unsafe_allow_html=True)
        clear = st.button("🧹 누적 초기화", use_container_width=True)

    with h_col3:
        if st.session_state.rows:
            st.markdown("<div style='margin-top:-8px'></div>", unsafe_allow_html=True)
            df_raw_for_excel = pd.DataFrame(st.session_state.rows)
            xbytes = to_xlsx_bytes(df_raw_for_excel)
            st.download_button(
                "📥 결과 엑셀(.xlsx) 다운로드",
                data=xbytes,
                file_name="도서_자동완성_결과.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    if clear:
        st.session_state.rows = []
        st.toast("누적 데이터를 초기화했어요.", icon="🧹")

    # ---------------------------
    # Table
    # ---------------------------
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
