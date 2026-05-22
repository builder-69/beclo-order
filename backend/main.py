"""
Order generation entry point.

This module keeps the existing processing pipeline together so api.py can stay
as a thin HTTP adapter.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
import re

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mapping import build_mapping, load_exception_mapping
from output import generate_output, validate_quantities
from process import process_orders
from file_prepare import FilePreparationError, prepare_uploaded_order_files


class OrderGenerationError(Exception):
    """User-facing order generation failure."""


def _load_mapping_from_json(mapping_json: str | None) -> pd.DataFrame | None:
    if not mapping_json:
        return None
    try:
        rows = json.loads(mapping_json)
    except json.JSONDecodeError as exc:
        raise OrderGenerationError("상품 매핑 정보를 읽을 수 없습니다. Google Sheets를 다시 불러와 주세요.") from exc
    if not isinstance(rows, list):
        raise OrderGenerationError("상품 매핑 형식이 올바르지 않습니다. Google Sheets를 다시 불러와 주세요.")
    return pd.DataFrame(rows)


def _load_exception_map_from_json(exception_json: str | None) -> dict[tuple[str, str, str], list[list[str]]]:
    if not exception_json:
        return {}
    try:
        raw = json.loads(exception_json)
    except json.JSONDecodeError as exc:
        raise OrderGenerationError("예외 매핑 정보를 읽을 수 없습니다. Google Sheets를 다시 불러와 주세요.") from exc
    if not isinstance(raw, dict):
        raise OrderGenerationError("예외 매핑 형식이 올바르지 않습니다. Google Sheets를 다시 불러와 주세요.")

    exception_map: dict[tuple[str, str, str], list[list[str]]] = {}
    for key, products in raw.items():
        parts = str(key).split("|", 2)
        if len(parts) != 3:
            continue
        exception_map[(parts[0], parts[1], parts[2])] = products
    return exception_map


def _load_mapping_from_file(mapping_file: str) -> tuple[pd.DataFrame, dict[tuple[str, str, str], Any]]:
    try:
        mapping_df = pd.read_excel(mapping_file, sheet_name="상품리스트")
        exc_df = pd.read_excel(mapping_file, sheet_name="예외매핑")
    except Exception as exc:
        raise OrderGenerationError("거래처 상품리스트 파일을 읽을 수 없습니다.") from exc
    return build_mapping(mapping_df), load_exception_mapping(exc_df)


def _find_mapping_file(uploaded: list[str]) -> str | None:
    keywords = ["베클로", "거래처", "상품리스트"]
    return next(
        (path for path in uploaded if any(keyword in os.path.basename(path) for keyword in keywords)),
        None,
    )


def run_generate(
    uploaded_files: list[str],
    work_dir: str | os.PathLike[str],
    mapping_json: str | None = None,
    exception_json: str | None = None,
    return_details: bool = False,
) -> str | dict[str, Any]:
    """
    Run the existing order generation pipeline and return one TXT file path.
    """
    uploaded = [str(Path(path)) for path in uploaded_files]
    if not uploaded:
        raise OrderGenerationError("주문서 파일을 1개 이상 업로드해 주세요.")

    print(f"[run_generate] uploaded files ({len(uploaded)}): {[Path(path).name for path in uploaded]}", flush=True)

    output_dir = Path(work_dir) / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    mapping_file = _find_mapping_file(uploaded)
    mapping = _load_mapping_from_json(mapping_json)
    exception_map = _load_exception_map_from_json(exception_json)
    print(
        "[run_generate] mapping source: "
        f"json_rows={0 if mapping is None else len(mapping)}, "
        f"exception_keys={len(exception_map)}, "
        f"mapping_file={Path(mapping_file).name if mapping_file else None}",
        flush=True,
    )

    if mapping is None:
        if not mapping_file:
            raise OrderGenerationError("거래처 상품리스트가 연결되지 않았습니다. Google Sheets를 먼저 불러와 주세요.")
        mapping, exception_map = _load_mapping_from_file(mapping_file)

    if mapping_file is None:
        mapping_file = str(Path(work_dir) / "_mapping_placeholder.xlsx")

    try:
        prepared_uploaded = prepare_uploaded_order_files(
            uploaded,
            Path(work_dir) / "prepared",
            mapping_file=mapping_file,
        )
    except FilePreparationError as exc:
        raise OrderGenerationError(str(exc)) from exc

    print(f"[run_generate] passing to process_orders: {[Path(path).name for path in prepared_uploaded]}", flush=True)
    result, needs_review, no_mapping = process_orders(prepared_uploaded, mapping_file, mapping, exception_map)
    print(
        "[run_generate] process_orders result: "
        f"suppliers={len(result)}, needs_review={len(needs_review)}, no_mapping={len(no_mapping)}",
        flush=True,
    )

    output_path_temp = generate_output(
        result,
        needs_review,
        no_mapping,
        prepared_uploaded,
        mapping_file,
        output_dir=str(output_dir),
    )

    validation_summary = validate_quantities(
        prepared_uploaded,
        mapping_file,
        output_path_temp,
        result=result,
        no_mapping=no_mapping,
        exception_map=exception_map,
    )
    validation_summary["거래처_수"] = len(result)

    output_path = generate_output(
        result,
        needs_review,
        no_mapping,
        prepared_uploaded,
        mapping_file,
        validation_summary,
        output_dir=str(output_dir),
    )

    if return_details:
        return {
            "output_path": output_path,
            "prepared_files": _build_prepared_file_info(prepared_uploaded, mapping_file),
        }
    return output_path


def _build_prepared_file_info(prepared_uploaded: list[str], mapping_file: str | None) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    seen_platforms: set[str] = set()

    for path in prepared_uploaded:
        if mapping_file and str(path) == str(mapping_file):
            continue

        name = Path(path).name
        platform = _detect_platform(name)
        if not platform or platform in seen_platforms:
            continue

        files.append({
            "platform": platform,
            "label": _platform_label(platform),
            "path": path,
            "filename": _converted_order_filename(platform, name, Path(path).suffix),
        })
        seen_platforms.add(platform)

    return files


def _detect_platform(filename: str) -> str | None:
    if "스마트스토어" in filename or "네이버" in filename:
        return "naver"
    if "배송준비" in filename or "하이버" in filename:
        return "hyber"
    if "에이블리" in filename:
        return "ably"
    return None


def _platform_label(platform: str) -> str:
    return {
        "naver": "네이버 주문서",
        "hyber": "하이버 주문서",
        "ably": "에이블리 주문서",
    }.get(platform, "주문서")


def _converted_order_filename(platform: str, original_name: str, suffix: str) -> str:
    label = _platform_label(platform)
    suffix = suffix if suffix else ".xlsx"

    if platform in {"naver", "hyber"}:
        match = re.search(r"(20\d{6})[_-]?(\d{4})", original_name)
        if match:
            yyyymmdd = match.group(1)
            hhmm = match.group(2)
            return f"{label}_{yyyymmdd[2:]}_{hhmm}{suffix}"

    if platform == "ably":
        match = re.search(r"(20\d{6})", original_name)
        if match:
            return f"{label}_{match.group(1)[2:]}{suffix}"

    return f"{label}{suffix}"
