"""
주문서 처리 모듈
주문서 파일을 읽어서 발주 데이터로 변환
"""

import pandas as pd
import os
from collections import defaultdict
from helpers import normalize, normalize_filename, parse_option_items


def _basename(path):
    return normalize_filename(os.path.basename(path))


def _is_hyber_file(path, mapping_file=None):
    name = _basename(path)
    return path != mapping_file and ('배송준비' in name or '하이버' in name)


def _read_order_table(path, header=0, **kwargs):
    suffix = os.path.splitext(str(path))[1].lower()
    with open(path, 'rb') as file:
        signature = file.read(4)
    if suffix == '.csv' and signature.startswith(b'PK'):
        return pd.read_excel(path, header=header, engine='openpyxl', **kwargs)
    if suffix == '.csv':
        for encoding in ('utf-8-sig', 'cp949', 'euc-kr'):
            try:
                return pd.read_csv(path, header=header, encoding=encoding, sep=None, engine='python', **kwargs)
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        return pd.read_csv(path, header=header, sep=None, engine='python', **kwargs)
    return pd.read_excel(path, header=header, **kwargs)


def process_orders(uploaded, mapping_file, mapping, exception_map):
    """
    모든 주문서 파일을 처리하여 발주 데이터 생성
    
    Args:
        uploaded: 업로드된 파일 경로 리스트
        mapping_file: 매핑 파일 경로
        mapping: 매핑 DataFrame
        exception_map: 예외매핑 딕셔너리
    
    Returns:
        tuple: (result, needs_review, no_mapping)
    """
    result = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    needs_review = []
    no_mapping = []
    
    # 파일 분류
    naver_files = [f for f in uploaded if '스마트스토어' in _basename(f) or '네이버' in _basename(f)]
    hyber_files = [f for f in uploaded if _is_hyber_file(f, mapping_file)]
    ably_files = [f for f in uploaded if '에이블리' in _basename(f)]
    print(
        "[process_orders] classified files: "
        f"naver={len(naver_files)} {[_basename(f) for f in naver_files]}, "
        f"hyber={len(hyber_files)} {[_basename(f) for f in hyber_files]}, "
        f"ably={len(ably_files)} {[_basename(f) for f in ably_files]}",
        flush=True,
    )
    
    # 네이버 처리
    for nf in naver_files:
        df = _read_order_table(nf, header=1)
        print(f"[process_orders] read naver {_basename(nf)} rows={len(df)} columns={list(df.columns)}", flush=True)
        _process_platform_orders(df, 'naver', '상품번호', '옵션정보', '수량', 
                                mapping, exception_map, result, needs_review, no_mapping)
    
    # 하이버 처리
    for hf in hyber_files:
        df = _read_order_table(hf, header=0)
        print(f"[process_orders] read hyber {_basename(hf)} rows={len(df)} columns={list(df.columns)}", flush=True)
        _process_platform_orders(df, 'hyber', '상품번호', '옵션정보', '수량',
                                mapping, exception_map, result, needs_review, no_mapping)
    
    # 에이블리 처리
    for af in ably_files:
        xl = pd.ExcelFile(af)
        ably_sheet = next((s for s in xl.sheet_names if '에이블리_발송 관리' in s), None)
        if ably_sheet:
            df = pd.read_excel(af, sheet_name=ably_sheet, header=0)
            print(f"[process_orders] read ably {_basename(af)} sheet={ably_sheet} rows={len(df)} columns={list(df.columns)}", flush=True)
            _process_platform_orders(df, 'ably', '판매자 상품코드', '옵션 정보', '수량',
                                    mapping, exception_map, result, needs_review, no_mapping)
        else:
            print(f"[process_orders] ably sheet not found in {_basename(af)} sheets={xl.sheet_names}", flush=True)
    
    return result, needs_review, no_mapping


def _process_platform_orders(df, 플랫폼, 번호col, 옵션col, 수량col, 
                             mapping, exception_map, result, needs_review, no_mapping):
    """
    단일 플랫폼 주문서 처리
    
    Args:
        df: 주문서 DataFrame
        플랫폼: 'naver', 'hyber', 'ably'
        번호col, 옵션col, 수량col: 컬럼명
        mapping: 매핑 DataFrame
        exception_map: 예외매핑 딕셔너리
        result, needs_review, no_mapping: 출력 딕셔너리들
    """

    valid_order_rows = 0
    total_order_qty = 0
    skipped_number = 0
    skipped_option = 0
    no_mapping_before = len(no_mapping)
    needs_review_before = len(needs_review)

    for _, row in df.iterrows():
        try:
            상품번호_raw = row[번호col]
            상품번호 = str(int(float(상품번호_raw))).strip() if 플랫폼 != 'ably' else str(상품번호_raw).strip()
        except:
            skipped_number += 1
            continue

        옵션str = str(row[옵션col]).strip()
        if not 옵션str or 옵션str == 'nan': 
            skipped_option += 1
            continue

        try: 
            수량 = int(row[수량col])
        except: 
            수량 = 1
        valid_order_rows += 1
        total_order_qty += 수량

        # 예외매핑 확인
        matched_exceptions = []
        for (exc_플랫폼, exc_번호, exc_키워드), exc_상품_리스트 in exception_map.items():
            if exc_플랫폼 == 플랫폼 and exc_번호 == 상품번호:
                # exc_상품_리스트는 [(거래처상품명, 거래처상품번호), ...] 형태
                for exc_거래처상품명, exc_거래처상품번호 in exc_상품_리스트:
                    matched_exceptions.append((exc_거래처상품명, exc_거래처상품번호, exc_키워드))

        # 예외매핑 처리
        if matched_exceptions:
            items = parse_option_items(옵션str)
            is_multi = (len(items) > 1)
            
            for 키워드, 플랫폼컬러, opt_사이즈 in items:
                matched_list = []
                
                # 키워드로 매칭 (완전일치 우선, 부분포함 차선)
                if 키워드:
                    for 상품명, 상품번호, exc_키워드 in matched_exceptions:
                        if normalize(exc_키워드) == normalize(키워드):
                            matched_list.append((상품명, 상품번호))
                    if not matched_list:
                        for 상품명, 상품번호, exc_키워드 in matched_exceptions:
                            if normalize(exc_키워드) in normalize(키워드):
                                matched_list.append((상품명, 상품번호))
                
                # 옵션 전체 문자열에서 찾기 (단일 아이템일 때만)
                if not matched_list and not is_multi:
                    for 상품명, 상품번호, exc_키워드 in matched_exceptions:
                        if normalize(exc_키워드) in normalize(옵션str):
                            matched_list.append((상품명, 상품번호))
                
                # 매칭된 모든 상품 처리
                if matched_list:
                    for matched, matched_번호 in matched_list:
                        # 거래처명 찾기
                        try:
                            번호_str = str(int(float(matched_번호)))
                        except:
                            번호_str = matched_번호
                        
                        거래처_후보 = mapping[mapping['거래처 상품번호'].astype(str).str.strip() == 번호_str]
                        
                        if not 거래처_후보.empty:
                            거래처명 = 거래처_후보.iloc[0]['거래처명']
                            
                            # 플랫폼 컬러에 대응하는 거래처 컬러 찾기
                            if 플랫폼컬러:
                                color_match = 거래처_후보[거래처_후보['플랫폼컬러'] == 플랫폼컬러]
                                if not color_match.empty:
                                    거래처컬러 = color_match.iloc[0]['거래처컬러']
                                else:
                                    거래처컬러 = 플랫폼컬러
                            else:
                                거래처컬러 = '[컬러 확인 필요]'
                        else:
                            거래처_후보2 = mapping[mapping['거래처상품명'] == matched]
                            if not 거래처_후보2.empty:
                                거래처명 = 거래처_후보2.iloc[0]['거래처명']
                                
                                # 플랫폼 컬러에 대응하는 거래처 컬러 찾기
                                if 플랫폼컬러:
                                    color_match = 거래처_후보2[거래처_후보2['플랫폼컬러'] == 플랫폼컬러]
                                    if not color_match.empty:
                                        거래처컬러 = color_match.iloc[0]['거래처컬러']
                                    else:
                                        거래처컬러 = 플랫폼컬러
                                else:
                                    거래처컬러 = '[컬러 확인 필요]'
                            else:
                                needs_review.append({'상품번호': 상품번호, '옵션': 옵션str, '수량': 수량, '플랫폼': 플랫폼})
                                continue
                        
                        거래처사이즈 = opt_사이즈 if opt_사이즈 else ''
                        
                        qty = 1 if is_multi else 수량
                        result[거래처명][matched][(거래처사이즈, 거래처컬러)] += qty
            continue

        # 일반 매핑 처리
        cands = mapping[(mapping['플랫폼'] == 플랫폼) & (mapping['플랫폼상품번호'] == 상품번호)].copy()
        if cands.empty:
            no_mapping.append({'상품번호': 상품번호, '옵션': 옵션str, '수량': 수량, '플랫폼': 플랫폼})
            continue

        items = parse_option_items(옵션str)
        is_multi = (len(items) > 1)
        
        for 키워드, 플랫폼컬러, opt_사이즈 in items:
            if cands.empty:
                needs_review.append({'상품번호': 상품번호, '옵션': 옵션str, '수량': 수량, '플랫폼': 플랫폼})
                continue

            # 플랫폼 컬러와 매칭되는 거래처 컬러 찾기
            if 플랫폼컬러:
                color_match = cands[cands['플랫폼컬러'] == 플랫폼컬러]
                if not color_match.empty:
                    match = color_match.iloc[0]
                else:
                    match = cands.iloc[0]
            else:
                match = cands.iloc[0]
            
            거래처명 = match['거래처명']
            거래처상품명 = match['거래처상품명']
            거래처컬러 = match['거래처컬러'] if 플랫폼컬러 else '[컬러 확인 필요]'
            거래처사이즈 = opt_사이즈 if opt_사이즈 else ''

            qty = 1 if is_multi else 수량
            result[거래처명][거래처상품명][(거래처사이즈, 거래처컬러)] += qty

    print(
        f"[process_orders] platform={플랫폼} rows={len(df)} valid_order_rows={valid_order_rows} "
        f"total_order_qty={total_order_qty} "
        f"skipped_number={skipped_number} skipped_option={skipped_option} "
        f"new_no_mapping={len(no_mapping) - no_mapping_before} "
        f"new_needs_review={len(needs_review) - needs_review_before}",
        flush=True,
    )
