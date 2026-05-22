from pathlib import Path
import base64
import shutil
import tempfile
from typing import Annotated
from urllib.parse import quote
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from io import StringIO
import re
import traceback

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pandas as pd

try:
    from main import OrderGenerationError, run_generate
    from mapping import build_mapping, load_exception_mapping
except ModuleNotFoundError:
    from backend.main import OrderGenerationError, run_generate
    from backend.mapping import build_mapping, load_exception_mapping


class LoadSheetsRequest(BaseModel):
    sheets_url: str


LOAD_SHEETS_ERROR = "구글시트를 불러올 수 없습니다. 공유 설정과 탭 이름을 확인하세요."

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "beclo-order backend running"}


def _extract_sheet_id(sheets_url: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheets_url)
    if not match:
        raise ValueError("Invalid Google Sheets URL")
    return match.group(1)


def _read_google_sheet_csv(sheet_id: str, sheet_name: str) -> pd.DataFrame:
    csv_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={quote(sheet_name, safe='')}"
    )
    print(f"[load-sheets] {sheet_name} CSV URL: {csv_url}", flush=True)
    request = Request(csv_url, headers={"User-Agent": "beclo-order/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            csv_text = response.read().decode("utf-8-sig", errors="replace")
            print(f"[load-sheets] {sheet_name} status_code: {response.status}", flush=True)
            print(f"[load-sheets] {sheet_name} response preview: {csv_text[:300]}", flush=True)
    except HTTPError as exc:
        body = exc.read().decode("utf-8-sig", errors="replace")
        print(f"[load-sheets] {sheet_name} status_code: {exc.code}", flush=True)
        print(f"[load-sheets] {sheet_name} response preview: {body[:300]}", flush=True)
        raise
    return pd.read_csv(StringIO(csv_text), dtype=str).fillna("")


def _exception_map_to_json(exception_map):
    return {
        "|".join(map(str, key)): [list(product) for product in products]
        for key, products in exception_map.items()
    }


@app.post("/load-sheets")
def load_sheets(payload: LoadSheetsRequest):
    try:
        sheets_url = payload.sheets_url.strip()
        print(f"[load-sheets] sheets_url: {sheets_url}", flush=True)

        sheet_id = _extract_sheet_id(sheets_url)
        print(f"[load-sheets] spreadsheet_id: {sheet_id}", flush=True)

        mapping_rows = _read_google_sheet_csv(sheet_id, "상품리스트")
        exception_rows = _read_google_sheet_csv(sheet_id, "예외매핑")

        mapping = build_mapping(mapping_rows)
        exception_map = load_exception_mapping(exception_rows)

        return {
            "mapping": mapping.to_dict(orient="records"),
            "exceptionMap": _exception_map_to_json(exception_map),
            "mappingRowsCount": len(mapping_rows),
            "exceptionRowsCount": len(exception_rows),
        }
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(
            status_code=400,
            detail={
                "message": LOAD_SHEETS_ERROR,
                "error": f"{type(exc).__name__}: {exc}",
            },
        ) from exc


@app.post("/generate")
async def generate(
    background_tasks: BackgroundTasks,
    naver_files: Annotated[list[UploadFile] | None, File()] = None,
    hyber_files: Annotated[list[UploadFile] | None, File()] = None,
    ably_files: Annotated[list[UploadFile] | None, File()] = None,
    sheets_url: Annotated[str | None, Form()] = None,
    naver_password: Annotated[str | None, Form()] = None,
    mapping_json: Annotated[str | None, Form()] = None,
    exception_json: Annotated[str | None, Form()] = None,
):
    naver_files = naver_files or []
    hyber_files = hyber_files or []
    ably_files = ably_files or []
    all_files = naver_files + hyber_files + ably_files

    print(
        "[generate] received files: "
        f"naver={len(naver_files)} {[f.filename for f in naver_files]}, "
        f"hyber={len(hyber_files)} {[f.filename for f in hyber_files]}, "
        f"ably={len(ably_files)} {[f.filename for f in ably_files]}",
        flush=True,
    )

    if not all_files:
        raise HTTPException(status_code=400, detail="주문서 파일을 1개 이상 업로드해 주세요.")

    work_dir = Path(tempfile.mkdtemp(prefix="beclo-order-"))
    upload_dir = work_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    try:
        saved_paths: list[str] = []
        for upload_file in all_files:
            filename = Path(upload_file.filename or "upload.xlsx").name
            path = upload_dir / filename
            with path.open("wb") as file:
                shutil.copyfileobj(upload_file.file, file)
            saved_paths.append(str(path))

        print(f"[generate] saved_paths ({len(saved_paths)}): {saved_paths}", flush=True)

        generate_result = run_generate(
            saved_paths,
            work_dir,
            mapping_json=mapping_json,
            exception_json=exception_json,
            return_details=True,
        )
    except OrderGenerationError as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        print("[generate] OrderGenerationError traceback:", flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        print("[generate] unexpected error traceback:", flush=True)
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="발주서 생성 중 오류가 발생했습니다. 업로드 파일과 상품리스트 연결 상태를 확인해 주세요.",
        ) from exc

    output_path = Path(generate_result["output_path"])
    output_name = output_path.name
    converted_files = []
    for file_info in generate_result.get("prepared_files", []):
        file_path = Path(file_info["path"])
        converted_files.append({
            "platform": file_info["platform"],
            "label": file_info["label"],
            "filename": file_info["filename"],
            "contentBase64": base64.b64encode(file_path.read_bytes()).decode("ascii"),
        })

    response = {
        "filename": output_name,
        "txt": output_path.read_text(encoding="utf-8"),
        "convertedFiles": converted_files,
    }
    background_tasks.add_task(shutil.rmtree, work_dir, ignore_errors=True)

    return JSONResponse(response, background=background_tasks)
