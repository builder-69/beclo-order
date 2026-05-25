"""
출력 및 검수 모듈
발주서 텍스트 생성 및 수량 검수
"""

import pandas as pd
import os
import re
from datetime import date
from collections import defaultdict
from helpers import clean_color_for_output, normalize_filename, parse_option_items


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


def generate_output(result, needs_review, no_mapping, uploaded, mapping_file, validation_summary=None, output_dir="/mnt/user-data/outputs"):
    """
    발주서 텍스트 생성 및 파일 저장
    
    Args:
        result: 발주 데이터
        needs_review: 확인 필요 항목
        no_mapping: 매핑 없는 항목
        uploaded: 업로드된 파일 목록
        mapping_file: 매핑 파일 경로
        validation_summary: 수량 검수 요약 (optional)
    
    Returns:
        str: 저장된 파일 경로
    """
    output_lines = []
    size_order = {'XS': 0, 'S': 1, 'M': 2, 'L': 3, 'XL': 4, '2XL': 5, '3XL': 6}

    # 수량 검수 결과 추가
    if validation_summary:
        output_lines.append("=" * 60)
        output_lines.append("수량 검수 결과")
        output_lines.append("=" * 60)
        output_lines.append("")
        output_lines.append(f"* 주문서: {validation_summary['주문서_총수량']}개 ({validation_summary['주문서_상세']})")
        output_lines.append(f"* 발주서: {validation_summary['발주서_총수량']}개 ({validation_summary['발주서_상세']})")
        output_lines.append(f"* 거래처 수: {validation_summary['거래처_수']}개")
        output_lines.append("")
        if validation_summary['검수_통과']:
            output_lines.append("✅ 검수 통과")
        else:
            output_lines.append(f"⚠️  수량 불일치: 차이 {validation_summary['차이']}개")
        output_lines.append("=" * 60)
        output_lines.append("")
        output_lines.append("")

    # 거래처별 발주서 생성
    for 거래처명 in sorted(result.keys()):
        output_lines.append(f"[{거래처명}]")
        output_lines.append("")
        output_lines.append("안녕하세요.")
        output_lines.append("")

        for 상품명, items in result[거래처명].items():
            상품_총수량 = sum(items.values())
            output_lines.append(f"# {상품명} (총 {상품_총수량}개)")

            size_groups = defaultdict(list)
            for (사이즈, 컬러), 수량 in items.items():
                size_groups[사이즈].append((컬러, 수량))

            sorted_sizes = sorted(size_groups.keys(), key=lambda s: size_order.get(s.upper(), 99) if s else -1)
            
            for 사이즈 in sorted_sizes:
                for 컬러, 수량 in size_groups[사이즈]:
                    # SET 등 예외매핑 키워드 제거
                    컬러_clean = clean_color_for_output(컬러)
                    
                    if 사이즈:
                        output_lines.append(f"{컬러_clean} {사이즈} {수량}")
                    else:
                        output_lines.append(f"{컬러_clean} {수량}")
            output_lines.append("")

        output_lines.append("주문부탁드립니다.")
        output_lines.append("")

    # 확인 필요 항목
    if needs_review:
        output_lines.append("[확인 필요]")
        for item in needs_review:
            output_lines.append(f"상품번호: {item['상품번호']} / 옵션: {item['옵션']} / 수량: {item['수량']} ({item['플랫폼']})")
        output_lines.append("─" * 30)
        output_lines.append("")

    # 매핑 정보 없음
    if no_mapping:
        output_lines.append("[매핑 정보 없음 — 거래처 상품리스트에 등록 필요]")
        for item in no_mapping:
            output_lines.append(f"상품번호: {item['상품번호']} / 옵션: {item['옵션']} / 수량: {item['수량']} ({item['플랫폼']})")
        output_lines.append("─" * 30)

    output = '\n'.join(output_lines)

    # 파일명 생성
    dates = []
    
    naver_files = [f for f in uploaded if '스마트스토어' in _basename(f) or '네이버' in _basename(f)]
    for nf in naver_files:
        try:
            df = _read_order_table(nf, header=1)
            d = pd.to_datetime(df['결제일'].dropna().iloc[0])
            dates.append(d)
        except: 
            pass

    hyber_files = [f for f in uploaded if _is_hyber_file(f, mapping_file)]
    for hf in hyber_files:
        try:
            df = _read_order_table(hf, header=0)
            d = pd.to_datetime(df['결제일자'].dropna().iloc[0])
            dates.append(d)
        except: 
            pass

    if dates:
        latest = max(dates)
        file_date = f"{latest.month:02d}{latest.day:02d}"
    else:
        today = date.today()
        file_date = today.strftime('%m%d')

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"발주서_{file_date}.txt")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output)

    return output_path


def validate_quantities(uploaded, mapping_file, output_path, result=None, no_mapping=None, exception_map=None):
    """
    주문서와 발주서 수량 검수
    
    Args:
        uploaded: 업로드된 파일 목록
        mapping_file: 매핑 파일 경로
        output_path: 발주서 파일 경로 (미사용, 하위 호환용)
        result: process_orders 결과 딕셔너리 (발주서 수량 직접 합산용)
        no_mapping: 매핑없음 항목 리스트
    
    Returns:
        dict: 검수 요약 정보
    """
    # 예외매핑 로드 (SET, 1+1 등으로 분리되는 케이스 확인용)
    if exception_map is None:
        from mapping import load_exception_mapping
        try:
            exc_df = pd.read_excel(mapping_file, sheet_name='예외매핑')
            exception_map = load_exception_mapping(exc_df)
        except:
            exception_map = {}
    
    def calculate_order_quantity(df, 옵션col, 수량col, 상품번호col, platform):
        """
        주문서 수량 계산 - 예외매핑으로 분리되는 케이스 반영
        
        Args:
            df: 주문 데이터프레임
            옵션col: 옵션정보 컬럼명
            수량col: 수량 컬럼명
            상품번호col: 상품번호 컬럼명
            platform: 'naver', 'hyber', 'ably'
        
        Returns:
            int: 실제 발주 항목 개수
        """
        total = 0
        df = df.dropna(subset=[옵션col])
        
        for _, row in df.iterrows():
            옵션str = str(row[옵션col]).strip()
            if not 옵션str or 옵션str == 'nan': 
                continue
            
            try: 
                기본수량 = int(row[수량col])
            except: 
                기본수량 = 1
            
            # 상품번호 추출
            try:
                if platform == 'naver':
                    상품번호 = str(int(float(row[상품번호col]))).strip()
                elif platform == 'hyber':
                    상품번호 = str(int(float(row[상품번호col]))).strip()
                else:  # ably
                    상품번호 = str(row[상품번호col]).strip()
            except:
                상품번호 = str(row[상품번호col]).strip()
            
            # 예외매핑 체크 (옵션 전체 문자열로 한 번만)
            matched_exception = False
            matched_count = 0
            
            for (exc_platform, exc_상품번호, exc_키워드), mapped_products in exception_map.items():
                if exc_platform == platform and exc_상품번호 == 상품번호:
                    # 옵션 문자열 전체에 키워드가 포함되어 있는지 확인
                    if exc_키워드 in 옵션str:
                        # 예외매핑된 상품 개수 누적 (SET의 경우 여러 키워드가 매칭될 수 있음)
                        matched_count += len(mapped_products)
                        matched_exception = True
            
            if matched_exception:
                # 예외매핑이 있으면 매핑된 개수만큼 카운트
                total += 기본수량 * matched_count
            else:
                # 예외매핑이 없으면 일반 파싱
                items = parse_option_items(옵션str)
                total += 기본수량 * len(items)
        
        return total

    print(f"\n{'='*60}")
    print(f"수량 검수 시작")
    print(f"{'='*60}\n")

    주문_total = {'naver': 0, 'hyber': 0, 'ably': 0}

    # 네이버
    naver_files = [f for f in uploaded if '스마트스토어' in _basename(f) or '네이버' in _basename(f)]
    for nf in naver_files:
        df = _read_order_table(nf, header=1)
        주문_total['naver'] += calculate_order_quantity(df, '옵션정보', '수량', '상품번호', 'naver')

    # 하이버
    hyber_files = [f for f in uploaded if _is_hyber_file(f, mapping_file)]
    for hf in hyber_files:
        df = _read_order_table(hf, header=0)
        주문_total['hyber'] += calculate_order_quantity(df, '옵션정보', '수량', '상품번호', 'hyber')

    # 에이블리
    ably_files = [f for f in uploaded if '에이블리' in _basename(f)]
    for af in ably_files:
        xl = pd.ExcelFile(af)
        ably_sheet = next((s for s in xl.sheet_names if '에이블리_발송 관리' in s), None)
        if ably_sheet:
            df = pd.read_excel(af, sheet_name=ably_sheet, header=0)
            주문_total['ably'] += calculate_order_quantity(df, '옵션 정보', '수량', '판매자 상품코드', 'ably')

    주문서_총수량 = sum(주문_total.values())

    print(f"【주문서 수량】")
    if 주문_total['naver'] > 0:
        print(f"  네이버: {주문_total['naver']}개")
    if 주문_total['hyber'] > 0:
        print(f"  하이버: {주문_total['hyber']}개")
    if 주문_total['ably'] > 0:
        print(f"  에이블리: {주문_total['ably']}개")
    print(f"  ──────────────")
    print(f"  합계: {주문서_총수량}개")

    # 발주서 수량 계산 - result 딕셔너리 직접 합산 (텍스트 파싱 오류 방지)
    발주서_정상 = 0
    발주서_매핑없음 = 0

    if result is not None:
        for 거래처, 상품들 in result.items():
            for 상품명, items in 상품들.items():
                발주서_정상 += sum(items.values())

    if no_mapping is not None:
        발주서_매핑없음 = sum(item.get('수량', 0) for item in no_mapping)

    발주서_총수량 = 발주서_정상 + 발주서_매핑없음

    print(f"\n【발주서 수량】")
    print(f"  정상 처리: {발주서_정상}개")
    if 발주서_매핑없음 > 0:
        print(f"  매핑 없음: {발주서_매핑없음}개")
    print(f"  ──────────────")
    print(f"  합계: {발주서_총수량}개")

    print(f"\n{'='*60}")
    검수_통과 = (주문서_총수량 == 발주서_총수량)
    if 검수_통과:
        print(f"✅ 검수 통과: 주문서 {주문서_총수량}개 = 발주서 {발주서_총수량}개")
    else:
        print(f"⚠️  수량 불일치 발견!")
        print(f"   주문서: {주문서_총수량}개")
        print(f"   발주서: {발주서_총수량}개")
        print(f"   차이: {abs(주문서_총수량 - 발주서_총수량)}개")
    print(f"{'='*60}\n")
    
    # 주문서 표시용 카운트: 수량 합계 기준
    주문서_표시용 = {'naver': 0, 'hyber': 0, 'ably': 0}
    
    # 네이버
    naver_files = [f for f in uploaded if '스마트스토어' in _basename(f) or '네이버' in _basename(f)]
    for nf in naver_files:
        try:
            df = _read_order_table(nf, header=1)
            df_clean = df.dropna(subset=['옵션정보'])
            for _, row in df_clean.iterrows():
                try:
                    수량 = int(row['수량'])
                except:
                    수량 = 1
                주문서_표시용['naver'] += 수량
        except:
            pass
    
    # 하이버
    hyber_files = [f for f in uploaded if _is_hyber_file(f, mapping_file)]
    for hf in hyber_files:
        try:
            df = _read_order_table(hf, header=0)
            df_clean = df.dropna(subset=['옵션정보'])
            for _, row in df_clean.iterrows():
                try:
                    수량 = int(row['수량'])
                except:
                    수량 = 1
                주문서_표시용['hyber'] += 수량
        except:
            pass
    
    # 에이블리
    ably_files = [f for f in uploaded if '에이블리' in _basename(f)]
    for af in ably_files:
        try:
            xl = pd.ExcelFile(af)
            ably_sheet = next((s for s in xl.sheet_names if '에이블리_발송 관리' in s), None)
            if ably_sheet:
                df = pd.read_excel(af, sheet_name=ably_sheet, header=0)
                df_clean = df.dropna(subset=['옵션 정보'])
                for _, row in df_clean.iterrows():
                    try:
                        수량 = int(row['수량'])
                    except:
                        수량 = 1
                    주문서_표시용['ably'] += 수량
        except:
            pass
    
    주문서_표시용_총수량 = sum(주문서_표시용.values())
    
    # 주문서 상세 문자열 생성 (수량 합계 기준)
    주문서_parts = []
    if 주문서_표시용['naver'] > 0:
        주문서_parts.append(f"네이버 {주문서_표시용['naver']}")
    if 주문서_표시용['hyber'] > 0:
        주문서_parts.append(f"하이버 {주문서_표시용['hyber']}")
    if 주문서_표시용['ably'] > 0:
        주문서_parts.append(f"에이블리 {주문서_표시용['ably']}")
    주문서_상세 = " + ".join(주문서_parts)
    
    # 발주서 상세 문자열 생성 (예외매핑으로 분리된 케이스 감지)
    발주서_parts = []
    
    def format_platform_label(label, total, 표시용):
        if total > 표시용:
            증가분 = total - 표시용
            순수_단일 = 표시용 - 증가분
            분리된_최종 = 증가분 * 2
            return f"{label} {순수_단일} + SET {분리된_최종}분리 = {total}"
        return f"{label} {total}"

    if 주문_total['naver'] > 0:
        발주서_parts.append(format_platform_label("네이버", 주문_total['naver'], 주문서_표시용['naver']))
    if 주문_total['hyber'] > 0:
        발주서_parts.append(format_platform_label("하이버", 주문_total['hyber'], 주문서_표시용['hyber']))
    if 주문_total['ably'] > 0:
        발주서_parts.append(format_platform_label("에이블리", 주문_total['ably'], 주문서_표시용['ably']))
    발주서_상세 = ", ".join(발주서_parts)
    
    # 요약 정보 반환
    return {
        '주문서_총수량': 주문서_표시용_총수량,  # 옵션 파싱 기준 (예외매핑 제외)
        '발주서_총수량': 발주서_총수량,
        '주문서_상세': 주문서_상세,
        '발주서_상세': 발주서_상세,
        '검수_통과': 검수_통과,
        '차이': abs(주문서_총수량 - 발주서_총수량),  # 실제 차이는 계산된 수량 기준
        '거래처_수': 0  # main.py에서 설정
    }
