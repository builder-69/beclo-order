"""
매핑 로직 모듈
상품리스트와 예외매핑 데이터를 처리하여 매핑 딕셔너리 구성
"""

import pandas as pd
from helpers import split_csv, parse_platform_color, parse_platform_size

def load_exception_mapping(exc_df):
    """
    예외매핑 시트에서 예외매핑 딕셔너리 생성
    
    Returns:
        dict: {(플랫폼, 상품번호, 키워드): [(거래처상품명, 거래처상품번호), ...]}
              - 하나의 키에 여러 상품이 매핑될 수 있음 (예: SET 옵션)
    """
    from collections import defaultdict
    exception_map = defaultdict(list)
    exc_df = exc_df.dropna(subset=['거래처 상품명'])
    
    for _, r in exc_df.iterrows():
        거래처상품명 = str(r['거래처 상품명']).strip()
        거래처상품번호 = str(r.get('거래처 상품번호', '')).strip()
        
        # 네이버
        if pd.notna(r.get('네이버 상품번호')) and pd.notna(r.get('네이버 추가옵션')):
            네이버번호 = str(int(float(r['네이버 상품번호']))).strip()
            네이버옵션 = str(r['네이버 추가옵션']).strip()
            exception_map[('naver', 네이버번호, 네이버옵션)].append((거래처상품명, 거래처상품번호))
        
        # 하이버
        if pd.notna(r.get('하이버 상품번호')) and pd.notna(r.get('하이버 추가옵션')):
            하이버번호 = str(int(float(r['하이버 상품번호']))).strip()
            하이버옵션 = str(r['하이버 추가옵션']).strip()
            exception_map[('hyber', 하이버번호, 하이버옵션)].append((거래처상품명, 거래처상품번호))
        
        # 에이블리
        if pd.notna(r.get('에이블리 상품코드')) and pd.notna(r.get('에이블리 추가옵션')):
            에이블리코드 = str(r['에이블리 상품코드']).strip()
            에이블리옵션 = str(r['에이블리 추가옵션']).strip()
            exception_map[('ably', 에이블리코드, 에이블리옵션)].append((거래처상품명, 거래처상품번호))
    
    return dict(exception_map)

def build_mapping(mapping_df):
    """
    상품리스트 시트에서 매핑 DataFrame 생성
    
    Returns:
        pd.DataFrame: 플랫폼별 상품 매핑 정보
    """
    rows = []
    mapping_df = mapping_df.dropna(subset=['거래처명'])

    for _, r in mapping_df.iterrows():
        거래처명 = str(r.get('거래처명', '')).strip()
        if not 거래처명 or 거래처명 == 'nan': 
            continue
        
        거래처상품번호 = str(r.get('거래처 상품번호', '')).strip()
        거래처상품명 = str(r.get('거래처 상품명', '')).strip()
        
        # 거래처 상품명이 없으면 네이버 상품명으로 대체
        if not 거래처상품명 or 거래처상품명 == 'nan':
            네이버상품명 = str(r.get('네이버 상품명', '')).strip()
            거래처상품명 = f"(거래처 상품명 확인) {네이버상품명}" if 네이버상품명 and 네이버상품명 != 'nan' else ''

        d_colors = split_csv(r.get('거래처 컬러', ''))
        d_sizes  = split_csv(r.get('거래처 사이즈', ''))

        platforms = [
            ('naver', '네이버 상품번호',   None,              '네이버 컬러',   '네이버 사이즈',   '네이버 추가옵션'),
            ('hyber', '하이버 상품번호',   None,              '하이버 컬러',   '하이버 사이즈',   '하이버 추가옵션'),
            ('ably',  '에이블리 상품번호', '에이블리 상품코드', '에이블리 컬러', '에이블리 사이즈', '에이블리 추가옵션'),
        ]

        for 플랫폼, 번호_col, 코드_col, 컬러_col, 사이즈_col, 추가옵션_col in platforms:
            # 매칭 키 결정
            if 코드_col:
                매칭키 = str(r.get(코드_col, '')).strip()
                if not 매칭키 or 매칭키 == 'nan':
                    매칭키 = str(r.get(번호_col, '')).strip()
                    try: 매칭키 = str(int(float(매칭키)))
                    except: pass
            else:
                매칭키 = str(r.get(번호_col, '')).strip()
                try: 매칭키 = str(int(float(매칭키)))
                except: pass

            if not 매칭키 or 매칭키 == 'nan': 
                continue

            p_colors_raw = split_csv(r.get(컬러_col, ''))
            p_sizes_raw  = split_csv(r.get(사이즈_col, ''))
            추가옵션 = str(r.get(추가옵션_col, '')).strip()
            추가옵션 = '' if 추가옵션 == 'nan' else 추가옵션

            p_colors = [parse_platform_color(c) for c in p_colors_raw]
            p_sizes  = [parse_platform_size(s) for s in p_sizes_raw]

            use_colors = d_colors if d_colors else p_colors if p_colors else ['']
            use_sizes  = d_sizes  if d_sizes  else p_sizes  if p_sizes  else ['']

            for i, p_color in enumerate(p_colors if p_colors else ['']):
                거래처컬러 = use_colors[i] if i < len(use_colors) else use_colors[-1] if use_colors else ''
                rows.append({
                    '플랫폼': 플랫폼,
                    '플랫폼상품번호': 매칭키,
                    '거래처명': 거래처명,
                    '거래처 상품번호': 거래처상품번호,
                    '거래처상품명': 거래처상품명,
                    '플랫폼컬러': p_color,
                    '거래처컬러': 거래처컬러,
                    '플랫폼사이즈리스트': p_sizes,
                    '거래처사이즈리스트': use_sizes,
                    '추가옵션': 추가옵션,
                })

    return pd.DataFrame(rows)