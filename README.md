# 📚 도서 URL 자동완성 웹앱 (Cloud 안정화판 v8)

이 버전은 Streamlit Community Cloud에서 갑자기 발생한 `Error installing requirements` 문제를 피하도록
배포 구조를 다시 정리한 전체 프로젝트입니다.

## 핵심 변경점
- `runtime.txt` 추가: Python 3.11 고정
- `requirements.txt` 전체 버전 고정
- `packages.txt` 제거: apt 충돌 제거
- `postBuild` 제거: Playwright 브라우저 설치 단계 제거
- 파서 안정화: 브라우저 렌더링 의존성이 없어도 앱이 계속 실행되도록 폴백 처리

## 왜 기존 배포가 깨졌나
기존 `packages.txt`가 Debian bullseye 시절 패키지 이름/의존성을 전제로 작성되어 있었는데,
현재 Streamlit Cloud 빌드 환경(trixie)와 충돌하면서 `libglib2.0-0`, `libffi7`, `libpcre3`, `libcups2`
의존성 해석이 깨졌습니다.

## 실행
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 배포
이 폴더 전체를 GitHub 저장소 루트에 그대로 올리고 Streamlit Cloud에서 Redeploy 하세요.
