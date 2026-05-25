# 프로젝트명

Vendor PO (`vendor-po`)

# 프로젝트 목표

기존 index.html 기반 Vendor PO 생성 웹사이트를
frontend + Python FastAPI backend 구조로 분리한다.

# 현재 구조

- `frontend/index.html`: Vendor PO 독립 화면 원본
- `docs/index.html`: GitHub Pages용 독립 화면 사본
- `backend/api.py`: FastAPI 서버 및 HTTP endpoint
- `backend/main.py`: 기존 발주서 생성 처리 진입점
- `backend/`: 기존 Python 주문 처리 로직 보관
- `PROJECT_CONTEXT.md`: Codex 작업 기준 문서

# 중요한 원칙

- 기존 Python 로직을 발주 처리의 원본 로직으로 유지한다.
- 프론트엔드는 파일 업로드, API 호출, 결과 표시만 담당한다.
- 백엔드는 업로드 파일을 받아 Python 로직으로 처리한다.
- backend endpoint 및 발주 처리 계약은 유지한다.
- 운영 통합 화면은 `beclo-portal`을 우선 사용하며, 이 저장소의 독립 프론트는 보조 진입점이다.

# 명칭 변경 기록

- 기존 서비스/저장소 식별자 `beclo-order`는 `Vendor PO` / `vendor-po`로 변경되었다.
- 화면 표시명은 `Vendor PO`를 사용한다.
- 신규 URL, 저장소명, 임시 파일 prefix 등 신규 식별자는 `vendor-po`를 사용한다.

# 배포 구성

- backend Render URL: `https://vendor-po-api.onrender.com`
- Render Root Directory: `backend`
- Render Start Command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
- FastAPI `app`은 `backend/api.py`에 있다. `backend/main.py`를 Render entrypoint로 사용하지 않는다.
- 독립 GitHub Pages의 기존 custom domain `order.beclo.co.kr` 설정은 제거되었다.

# Google Sheets 연동 주의사항

- Google Sheets는 backend의 `/load-sheets` endpoint가 읽는다.
- 로컬 Python/Windows 환경의 HTTPS 인증서 검증 문제를 처리하기 위해 `truststore`와 `certifi` 의존성을 사용한다.
- 인증서 검증을 비활성화하는 방식으로 문제를 우회하지 않는다.