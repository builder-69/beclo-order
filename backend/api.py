from pathlib import Path
import shutil
import tempfile
from typing import Annotated
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

try:
    from main import OrderGenerationError, run_generate
except ModuleNotFoundError:
    from backend.main import OrderGenerationError, run_generate

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

        output_path = run_generate(
            saved_paths,
            work_dir,
            mapping_json=mapping_json,
            exception_json=exception_json,
        )
    except OrderGenerationError as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail="발주서 생성 중 오류가 발생했습니다. 업로드 파일과 상품리스트 연결 상태를 확인해 주세요.",
        ) from exc

    output_name = Path(output_path).name
    background_tasks.add_task(shutil.rmtree, work_dir, ignore_errors=True)

    return FileResponse(
        output_path,
        media_type="text/plain; charset=utf-8",
        filename=output_name,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(output_name)}"},
    )
