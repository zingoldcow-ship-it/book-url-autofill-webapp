# 📚 도서 URL 자동완성 웹앱 (완전체: Playwright 포함)

서점 상품 URL만 입력하면 `ISBN / 도서명 / 저자 / 출판사 / 정가 / 할인가` 등을 자동 추출해 누적하고, **엑셀(.xlsx)**로 다운로드합니다.

- 지원: **교보문고 / YES24 / 알라딘 / 영풍문고**
- 파싱 모드:
  - `requests` : 일반 HTTP 요청 기반
  - `playwright` : 동적 렌더링/차단 대응(헤드리스 브라우저) 백업

> Streamlit Cloud에서 Playwright(Chromium)가 설치되지 않은 경우가 있어, 이 프로젝트는  
> 1) `postBuild`로 설치를 시도하고,  
> 2) 런타임에서도 필요 시 설치를 한 번 더 시도합니다.

---

## Streamlit Community Cloud 배포 (추천)

1) 이 폴더를 GitHub Repo로 업로드  
2) Streamlit Cloud에서 **New app**  
3) Repo 선택 → Main file path: `app.py` → Deploy

---

## 파일 설명

- `app.py` : Streamlit UI
- `parsers/` : 서점별 파서 (+ Playwright 백업)
- `packages.txt` : Streamlit Cloud(리눅스) apt 패키지
- `postBuild` : Streamlit Cloud 빌드 후 Chromium 설치
- `requirements.txt` : 파이썬 의존성
