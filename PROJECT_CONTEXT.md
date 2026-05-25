# 프로젝트명

Vendor PO (`vendor-po`)

# 프로젝트 목표

기존 index.html 기반 Vendor PO 생성 웹사이트를
frontend + Python FastAPI backend 구조로 분리한다.

# 현재 구조

- frontend/index.html: Vendor PO 웹 화면
- backend/: 기존 Python 주문 처리 로직 보관
- backend/api.py: FastAPI 서버
- backend/main.py: 발주서 생성 처리 진입점
- PROJECT_CONTEXT.md: Codex 작업 기준 문서

# 중요한 원칙

- 기존 Python 로직을 원본 로직으로 유지한다.
- JS로 포팅한 주문 처리 로직은 제거한다.
- 프론트엔드는 파일 업로드, API 호출, 결과 표시만 담당한다.
- 백엔드는 업로드 파일을 받아 Python 로직으로 처리한다.

# 목표 배포 구조

- frontend: GitHub Pages
- backend: Render
