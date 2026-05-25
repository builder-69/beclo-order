from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from helpers import normalize_filename


SUPPORTED_ORDER_EXTENSIONS = {".xlsx", ".xls", ".csv"}


class FilePreparationError(Exception):
    """User-facing upload preparation failure."""


def _basename(path: str | os.PathLike[str]) -> str:
    return normalize_filename(os.path.basename(str(path)))


def _is_naver_file(path: str | os.PathLike[str]) -> bool:
    name = _basename(path)
    return "스마트스토어" in name or "네이버" in name


def _is_hyber_file(path: str | os.PathLike[str], mapping_file: str | None = None) -> bool:
    name = _basename(path)
    return str(path) != str(mapping_file) and ("배송준비" in name or "하이버" in name)


def _safe_output_path(output_dir: Path, member_name: str) -> Path:
    pure = PurePosixPath(member_name.replace("\\", "/"))
    filename = Path(pure.name).name
    if not filename:
        raise FilePreparationError("zip 내부 파일명을 확인할 수 없습니다.")
    return output_dir / filename


def _is_supported_order_file(path: str | os.PathLike[str]) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_ORDER_EXTENSIONS


def _copy_with_unique_name(source: Path, output_dir: Path) -> str:
    target = output_dir / source.name
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        index = 2
        while target.exists():
            target = output_dir / f"{stem}_{index}{suffix}"
            index += 1
    shutil.copy2(source, target)
    return str(target)


def _decrypt_excel_if_needed(source: Path, output_dir: Path, password: str | None) -> str:
    try:
        import pandas as pd
        excel = pd.ExcelFile(source)
        excel.close()
        return str(source)
    except Exception:
        pass

    try:
        import msoffcrypto
    except ImportError as exc:
        raise FilePreparationError("암호화된 엑셀 파일을 처리하려면 msoffcrypto-tool 설치가 필요합니다.") from exc

    with source.open("rb") as file:
        try:
            office_file = msoffcrypto.OfficeFile(file)
            is_encrypted = office_file.is_encrypted()
        except Exception as exc:
            raise FilePreparationError("네이버 주문서 파일을 열 수 없습니다.") from exc

        if not is_encrypted:
            raise FilePreparationError("네이버 주문서 파일을 열 수 없습니다.")

        if not password:
            raise FilePreparationError("네이버 주문서 비밀번호가 설정되어 있지 않습니다.")

        target = output_dir / source.name
        try:
            office_file.load_key(password=password)
            with target.open("wb") as output:
                office_file.decrypt(output)
        except Exception as exc:
            raise FilePreparationError("네이버 주문서 비밀번호가 올바르지 않거나 파일을 열 수 없습니다.") from exc

    return str(target)


def _extract_zip(source: Path, output_dir: Path, password: str | None) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    password_bytes = password.encode("utf-8") if password else None

    try:
        import pyzipper
        zip_class = pyzipper.AESZipFile
    except ImportError:
        zip_class = zipfile.ZipFile

    extracted: list[str] = []
    try:
        with zip_class(source) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            supported = [
                info for info in members
                if Path(info.filename).suffix.lower() in SUPPORTED_ORDER_EXTENSIONS
            ]
            if not supported:
                raise FilePreparationError("하이버 zip 내부에 xlsx/xls/csv 파일이 없습니다.")

            for info in supported:
                target = _safe_output_path(output_dir, info.filename)
                if target.exists():
                    stem = target.stem
                    suffix = target.suffix
                    index = 2
                    while target.exists():
                        target = output_dir / f"{stem}_{index}{suffix}"
                        index += 1
                try:
                    data = archive.read(info.filename, pwd=password_bytes)
                except TypeError:
                    if password_bytes and hasattr(archive, "setpassword"):
                        archive.setpassword(password_bytes)
                    data = archive.read(info.filename)
                except RuntimeError as exc:
                    if "password" in str(exc).lower() or "encrypted" in str(exc).lower():
                        if not password:
                            raise FilePreparationError("하이버 zip 비밀번호가 설정되어 있지 않습니다.") from exc
                        raise FilePreparationError("하이버 zip 비밀번호가 올바르지 않습니다.") from exc
                    raise

                if target.suffix.lower() == ".csv" and data.startswith(b"PK"):
                    target = target.with_suffix(".xlsx")
                target.write_bytes(data)
                extracted.append(str(target))
    except zipfile.BadZipFile as exc:
        raise FilePreparationError("하이버 zip 파일이 손상되었거나 올바른 zip 형식이 아닙니다.") from exc
    except FilePreparationError:
        raise
    except Exception as exc:
        raise FilePreparationError("하이버 zip 파일을 압축 해제할 수 없습니다.") from exc

    return extracted


def prepare_uploaded_order_files(
    uploaded: list[str],
    work_dir: str | os.PathLike[str],
    mapping_file: str | None = None,
) -> list[str]:
    output_dir = Path(work_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    naver_password = os.getenv("NAVER_ORDER_PASSWORD")
    hyber_password = os.getenv("HYBER_ORDER_PASSWORD")

    prepared: list[str] = []
    for raw_path in uploaded:
        path = Path(raw_path)
        suffix = path.suffix.lower()

        if str(path) == str(mapping_file):
            prepared.append(str(path))
            continue

        if _is_hyber_file(path, mapping_file) and suffix == ".zip":
            prepared.extend(_extract_zip(path, output_dir / path.stem, hyber_password))
            continue

        if _is_naver_file(path) and suffix in {".xlsx", ".xls"}:
            prepared.append(_decrypt_excel_if_needed(path, output_dir, naver_password))
            continue

        if suffix == ".zip":
            raise FilePreparationError("지원하지 않는 zip 파일입니다. 하이버 zip 파일인지 확인해 주세요.")

        if _is_supported_order_file(path):
            prepared.append(str(path))
            continue

        raise FilePreparationError(f"지원하지 않는 파일 형식입니다: {path.name}")

    print(f"[file_prepare] prepared files: {[Path(path).name for path in prepared]}", flush=True)
    return prepared
