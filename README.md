# Vendor PO

`Vendor PO`는 주문서를 바탕으로 거래처 발주 파일을 생성하는 서비스입니다.
화면과 문서에서 사용하는 기능명은 **Vendor PO**이며, 파일명이나 신규
식별자가 필요한 경우에는 `vendor-po`를 사용합니다.

## 구조

- `frontend/index.html`: 사용자 화면 원본
- `docs/index.html`: GitHub Pages 배포용 화면
- `backend/`: FastAPI API와 기존 발주 처리 로직

## 운영 원칙

- 화면 표시명은 `Vendor PO`를 사용합니다.
- backend endpoint와 발주 처리 로직은 기존 계약을 유지합니다.
- Render 서비스 URL은 `https://vendor-po-api.onrender.com`입니다.
- GitHub repository 및 remote 식별자는 `vendor-po`를 사용합니다.

## 배포

`frontend/index.html`을 변경한 경우 GitHub Pages에서 사용하는
`docs/index.html`에도 동일한 화면 변경을 반영해야 합니다.
