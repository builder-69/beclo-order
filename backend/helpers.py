"""
헬퍼 함수 모듈
발주서 생성에 필요한 기본 유틸리티 함수들
"""

import re
import pandas as pd

def normalize(s):
    """문자열 정규화 - 공백, 특수문자 제거"""
    return str(s).replace(' ','').replace('/','').replace('-','').replace('_','').lower().strip()

def clean_color_for_output(컬러):
    """
    발주서 출력용 컬러 정리
    - 예외매핑 키워드(SET, 팬츠, 셔츠 등) 제거
    - 공백 정리
    """
    컬러 = str(컬러).strip()
    
    # SET, 팬츠, 셔츠 등 예외매핑 키워드 제거
    # 대소문자 구분 없이 제거
    keywords_to_remove = ['SET', 'set', 'Set', '팬츠', '셔츠', '자켓', '투턱', '원턱', '바람막이', '바지']
    
    for keyword in keywords_to_remove:
        컬러 = 컬러.replace(keyword, '')
    
    # 연속된 공백 정리
    컬러 = ' '.join(컬러.split())
    
    return 컬러.strip()

def normalize_size(s):
    """사이즈 정규화 - One Size, Free는 빈 문자열로 변환"""
    s = str(s).strip()
    normalized = s.replace(' ', '').lower()
    if normalized in ['onesize', 'free', 'freesize']:
        return ''
    return s

def split_csv(s):
    """콤마로 구분된 문자열을 리스트로 변환"""
    s = str(s).strip()
    if not s or s == 'nan': return []
    return [x.strip() for x in s.split(',') if x.strip()]

def parse_platform_color(c):
    """하이버 컬러의 '(카라넥) 블랙' → '블랙' 접두어 괄호 제거"""
    return re.sub(r'^\([^)]+\)\s*', '', str(c).strip())

def clean_prefix_parens(s):
    """접두어 괄호 제거: '(투턱) 차콜' → '차콜'"""
    return re.sub(r'^\([^)]+\)\s*', '', str(s).strip())

def parse_platform_size(s):
    """'L (95~100)', 'M(2)', 'S(~30)', 'XL(3)' → 'L', 'M', 'S', 'XL' (괄호 제거)"""
    s = s.strip()
    m = re.match(r'^((?:\d+)?XL|XS|[SML])\s*[\(\[].*?[\)\]]?\s*$', s, re.IGNORECASE)
    if m: return m.group(1).upper()
    m = re.match(r'^((?:\d+)?XL|XS|[SML])\s*[\(\[ ]', s, re.IGNORECASE)
    return m.group(1).upper() if m else s

def strip_label(s):
    """'컬러: 블랙', '사이즈: XL(4)', '색상: 블루', '타입: 투턱' → 접두어 제거"""
    return re.sub(r'^(컬러|색상|사이즈|타입|선택\d*)\s*[:：]\s*', '', s.strip())

def parse_option_items(옵션):
    """
    옵션 문자열 → [(키워드, 플랫폼컬러, 사이즈)] 리스트
    
    처리 케이스:
    - '(자켓) 블랙 L/(원턱) 블랙 L' → [('자켓', '블랙', 'L'), ('원턱', '블랙', 'L')]
    - '자켓: 차콜 L / 바지: (투턱) 차콜 L' → [('자켓', '차콜', 'L'), ('투턱', '차콜', 'L')]
    - '타입: 카라넥 / 컬러: 네이비 / 사이즈: L' → [('카라넥', '네이비', 'L')]
    - '딥블루/XL(100)' → [('', '딥블루', 'XL')]
    - '블랙/L' → [('', '블랙', 'L')]
    - '라운드넥/블랙/L' → [('라운드넥', '블랙', 'L')]
    - '블랙/XL(4)' → [('', '블랙', 'XL')]
    """
    옵션 = 옵션.strip()

    # 슬래시 분리: 괄호 밖의 '/'만 구분자로 사용 (괄호 안 슬래시는 무시)
    def split_slash_outside_parens(s):
        parts = []
        depth = 0
        current = []
        for ch in s:
            if ch in '([':
                depth += 1
                current.append(ch)
            elif ch in ')]':
                depth -= 1
                current.append(ch)
            elif ch == '/' and depth == 0:
                parts.append(''.join(current).strip())
                current = []
            else:
                current.append(ch)
        parts.append(''.join(current).strip())
        return [p for p in parts if p]

    # 레이블 기반 파싱: '컬러: 블랙 / 사이즈: L / 안감: 기모안감' 형식
    # 파트 수 관계없이 컬러/사이즈 레이블을 직접 추출하고, 나머지는 키워드로 수집
    raw_parts = split_slash_outside_parens(옵션)
    label_map = {}
    extra_keywords = []
    color_labels = {'컬러', '색상'}
    size_labels = {'사이즈', '크기'}
    known_labels = {'컬러', '색상', '사이즈', '크기', '타입', '안감'}
    
    has_known_label = False
    for part in raw_parts:
        m = re.match(r'^(컬러|색상|사이즈|크기|타입|안감|선택\d*)\s*[:：]\s*(.+)$', part)
        if m and m.group(1) in known_labels:
            has_known_label = True
            break
    
    if has_known_label:
        # 레이블 기반 파싱 전에 옵션 전체에서 괄호 안 텍스트(재고안내 등) 제거
        # 단, 예외매핑 키워드용 괄호(자켓, 원턱 등)는 유지 — 여기서는 컬러 레이블 뒤 괄호만 제거
        # 전략: 각 파트에서 컬러/색상 레이블이 있는 경우, 그 값의 괄호 제거
        cleaned_raw_parts = []
        for part in raw_parts:
            m = re.match(r'^(컬러|색상)\s*[:：]\s*(.+)$', part)
            if m:
                val = re.sub(r'\s*\([^)]*\)', '', m.group(2)).strip()
                cleaned_raw_parts.append(f'{m.group(1)}: {val}')
            else:
                cleaned_raw_parts.append(part)
        raw_parts = cleaned_raw_parts

        # 레이블 기반 파싱
        for part in raw_parts:
            m = re.match(r'^(컬러|색상|사이즈|크기|타입|선택\d*)\s*[:：]\s*(.+)$', part)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                if key in color_labels:
                    label_map['컬러'] = val
                elif key in size_labels:
                    label_map['사이즈'] = val
                else:
                    # 타입이나 기타 옵션은 값만 키워드로
                    extra_keywords.append(val)
            else:
                # 레이블 없는 파트 - '안감: 기모안감' 같은 기타 레이블도 값만 추출
                m2 = re.match(r'^[^:：]+\s*[:：]\s*(.+)$', part)
                if m2:
                    extra_keywords.append(m2.group(1).strip())
                else:
                    extra_keywords.append(part)
        
        if '컬러' in label_map or '사이즈' in label_map:
            컬러 = label_map.get('컬러', '')
            사이즈_raw = label_map.get('사이즈', '')
            사이즈_clean = re.sub(r'[\(\[].*', '', 사이즈_raw).strip().upper() if 사이즈_raw else ''
            사이즈_clean = 사이즈_clean.rstrip('-')  # '2XL-' → '2XL' 말미 하이픈 제거
            사이즈 = normalize_size(사이즈_clean)
            # 키워드: 타입/기타 옵션값 합치기 (예외매핑 매칭용)
            keyword = ' '.join(extra_keywords) if extra_keywords else ''
            # '자켓+원턱 슬랙스' 처럼 + 구분자로 여러 구성이 합쳐진 경우 분리
            # 단, 괄호 안의 + (예: +19800원)는 분리하지 않음
            def split_plus_outside_parens(s):
                parts = []
                depth = 0
                current = []
                for ch in s:
                    if ch in '([':
                        depth += 1
                        current.append(ch)
                    elif ch in ')]':
                        depth -= 1
                        current.append(ch)
                    elif ch == '+' and depth == 0:
                        parts.append(''.join(current).strip())
                        current = []
                    else:
                        current.append(ch)
                parts.append(''.join(current).strip())
                return [p for p in parts if p]

            plus_parts = split_plus_outside_parens(keyword)
            if len(plus_parts) > 1:
                # 각 파트에서 괄호 수식어 및 "세트" 같은 불필요한 단어 제거
                def clean_keyword(k):
                    k = re.sub(r'\([^)]*\)', '', k)  # 괄호 제거
                    k = re.sub(r'\s*(세트|단품)\s*', '', k)  # 세트/단품 제거
                    return k.strip()
                cleaned = [clean_keyword(p) for p in plus_parts]
                return [(p, clean_prefix_parens(컬러), 사이즈) for p in cleaned if p]
            return [(keyword, clean_prefix_parens(컬러), 사이즈)]

    slash_parts = [strip_label(p.strip()) for p in raw_parts]



    # 2파트 형식: 컬러/사이즈 (예: 딥블루/XL(100), 블랙/L)
    if len(slash_parts) == 2:
        second_part = slash_parts[1]
        # 괄호나 공백 제거 후 사이즈 확인
        size_clean = re.sub(r'[\(\[].*', '', second_part).strip()
        
        if re.match(r'^((?:\d+)?XL|XS|[SML])$', size_clean, re.IGNORECASE):
            사이즈 = normalize_size(size_clean.upper())
            return [('', clean_prefix_parens(slash_parts[0]), 사이즈)]
    
    # 3파트 형식: 추가옵션/컬러/사이즈
    if len(slash_parts) == 3:
        last_part = slash_parts[2]
        size_clean = re.sub(r'[\(\[].*', '', last_part).strip()
        
        if re.match(r'^((?:\d+)?XL|XS|[SML])$', size_clean, re.IGNORECASE):
            사이즈 = normalize_size(size_clean.upper())
            return [(slash_parts[0], clean_prefix_parens(slash_parts[1]), 사이즈)]

    results = []
    
    for part in slash_parts:
        keyword = ''
        content = part
        
        # 1. 괄호 키워드 체크 - 전체 문자열에서 괄호 내용 추출
        # '바지: (투턱) 차콜 L' → keyword='투턱', content='바지: 차콜 L'
        # 단, '(100)', '(95~100)' 같은 사이즈 치수는 키워드가 아니므로 제거만 함
        m_paren = re.search(r'\(([^)]+)\)', part)
        if m_paren:
            paren_content = m_paren.group(1).strip()
            # 숫자만 있거나 사이즈 치수 형식(95~100, 100 등)이 아닌 경우만 키워드로 추출
            if not re.match(r'^[\d~\-\+]+$', paren_content):
                keyword = paren_content
            # 괄호 부분 제거
            content = part.replace(m_paren.group(0), '').strip()
            # 콜론 접두어 제거 ('바지: 차콜 L' → '차콜 L')
            content = re.sub(r'^[^:：]+\s*[:：]\s*', '', content)
        
        # 2. 콜론 접두어 제거 (괄호가 없는 경우)
        # '자켓: 차콜 L' → keyword='자켓', content='차콜 L'
        if not keyword:
            m_colon = re.match(r'^([^:：]+)\s*[:：]\s*(.+)$', content)
            if m_colon:
                keyword = m_colon.group(1).strip()
                content = m_colon.group(2).strip()
        
        # 2. 컬러-사이즈 분리형 (하이픈)
        if '-' in content and re.match(r'^(.+?)[- ]((?:\d+)?XL|XS|[SML])(\s*[\(\[].*)?$', content, re.IGNORECASE):
            cm = re.match(r'^(.+?)[- ]((?:\d+)?XL|XS|[SML])(\s*[\(\[].*)?$', content, re.IGNORECASE)
            사이즈 = normalize_size(cm.group(2).upper())
            results.append((keyword, clean_prefix_parens(cm.group(1).strip()), 사이즈))
            continue
        
        # 3. 키워드 컬러 사이즈 형식 (3단어 이상)
        parts_words = content.split()
        if len(parts_words) >= 3:
            last_word = parts_words[-1]
            size_clean = re.sub(r'[\(\[].*', '', last_word).strip()
            if re.match(r'^((?:\d+)?XL|XS|[SML])$', size_clean, re.IGNORECASE):
                사이즈 = normalize_size(size_clean.upper())
                앞부분 = ' '.join(parts_words[:-1])
                
                if keyword:
                    컬러 = 앞부분
                else:
                    앞단어들 = 앞부분.split()
                    if len(앞단어들) >= 2:
                        keyword = 앞단어들[0]
                        컬러 = ' '.join(앞단어들[1:])
                    else:
                        컬러 = 앞부분
                
                results.append((keyword, clean_prefix_parens(컬러), 사이즈))
                continue
        
        # 4. XL(4), M(2) 괄호 제거
        size_match = re.match(r'^(.+?)\s+((?:\d+)?XL|XS|[SML])\s*[\(\[].*?[\)\]]?\s*$', content, re.IGNORECASE)
        if size_match:
            사이즈 = normalize_size(size_match.group(2).upper())
            results.append((keyword, clean_prefix_parens(size_match.group(1).strip()), 사이즈))
            continue
        
        # 5. L (95~100)
        size_match2 = re.match(r'^(.+?)\s+((?:\d+)?XL|XS|[SML])\s*[\(\[ ]', content, re.IGNORECASE)
        if size_match2:
            사이즈 = normalize_size(size_match2.group(2).upper())
            results.append((keyword, clean_prefix_parens(size_match2.group(1).strip()), 사이즈))
            continue
        
        # 6. 컬러 사이즈
        size_match3 = re.match(r'^(.+?)\s+((?:\d+)?XL|XS|[SML])$', content, re.IGNORECASE)
        if size_match3:
            사이즈 = normalize_size(size_match3.group(2).upper())
            results.append((keyword, clean_prefix_parens(size_match3.group(1).strip()), 사이즈))
            continue
        
        # 7. 사이즈 없음
        results.append((keyword, clean_prefix_parens(content), ''))
    
    return results