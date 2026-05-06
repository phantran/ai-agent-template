from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".pdf"}


async def load_upload_text(file: UploadFile) -> str:
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    content = await file.read()

    if suffix == ".pdf":
        reader = PdfReader(BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(page for page in pages if page.strip())

    if suffix in {"", ".txt", ".md", ".markdown", ".json"}:
        return content.decode("utf-8")

    supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
    raise ValueError(f"Unsupported file type '{suffix}'. Supported types: {supported}.")
