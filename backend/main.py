"""
발주서 자동 생성 메인 스크립트
"""

import pandas as pd
import os
import glob

# 모듈 임포트
import sys
sys.path.insert(0, '/mnt/skills/user/purchase-order')

from helpers import *
from mapping import build_mapping, load_exception_mapping
from process import process_orders
from output import generate_output, validate_quantities

# ── Step 1. 파일 확인 ──────────────────────────────────

uploaded = glob.glob('/mnt/user-data/uploads/*.xlsx') + \
           glob.glob('/mnt/user-data/uploads/*.xls') + \
           glob.glob('/mnt/user-data/uploads/*.csv')

# 매핑 파일 찾기
mapping_file = next(
    (f for f in uploaded if any(k in os.path.basename(f) for k in ['베클로', '거래처', '상품리스트'])),
    None
)

if not mapping_file:
    raise FileNotFoundError(
        "베클로 거래처 상품리스트 파일을 찾을 수 없습니다.\n"
        "'베클로_거래처_상품리스트.xlsx' 파일을 주문서 파일과 함께 업로드해주세요."
    )

print(f"매핑 파일: {os.path.basename(mapping_file)}")

# ── Step 2. 매핑 데이터 로드 ────────────────────────────

mapping_df = pd.read_excel(mapping_file, sheet_name='상품리스트')
exc_df = pd.read_excel(mapping_file, sheet_name='예외매핑')

exception_map = load_exception_mapping(exc_df)
mapping = build_mapping(mapping_df)

print(f"예외매핑: {len(exception_map)}개")
print(f"매핑 데이터: {len(mapping)}개 행")

# ── Step 3. 주문서 처리 ─────────────────────────────────

print("\n주문서 처리 중...")
result, needs_review, no_mapping = process_orders(uploaded, mapping_file, mapping, exception_map)

# ── Step 4. 임시 발주서 생성 (검수용) ───────────────────

output_path_temp = generate_output(result, needs_review, no_mapping, uploaded, mapping_file)

# ── Step 5. 수량 검수 ───────────────────────────────────

validation_summary = validate_quantities(uploaded, mapping_file, output_path_temp, result=result, no_mapping=no_mapping)
validation_summary['거래처_수'] = len(result)

# ── Step 6. 최종 발주서 생성 (검수 결과 포함) ────────────

output_path = generate_output(result, needs_review, no_mapping, uploaded, mapping_file, validation_summary)

# ── Step 7. 결과 출력 ───────────────────────────────────

print(f"\n발주서 생성 완료: {output_path}")
print(f"거래처 수: {len(result)}개")