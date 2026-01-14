# 📚 도서 URL 자동완성 웹앱 (완전체 v3)

변경 사항(요청 반영)
1) 교보문고 ISBN/출판사/가격 누락 개선:
   - ISBN 13자리(978/979) 강제 스캔
   - '출판사' 텍스트 기반 스캔
   - 가격 스캔/셀렉터 보강 + Playwright 백업
2) 엑셀 출력:
   - '처리상태' 컬럼 제거
   - '상품 URL' 컬럼을 맨 오른쪽으로 이동
3) 화면:
   - NaN가 'nan'으로 보이는 문제 방지(가격 표시)

Streamlit Cloud:
- Main file path: app.py
- packages.txt / postBuild 포함
