"""Extracts plain text from uploaded resume files (PDF/DOCX) before sending to Gemini.
Mirrors what your Flask app did with pdfplumber/python-docx, just as an isolated service."""
import io

import pdfplumber
from docx import Document
from fastapi import HTTPException, UploadFile


async def extract_text_from_upload(file: UploadFile) -> str:
    filename = (file.filename or "").lower()
    content = await file.read()

    if filename.endswith(".pdf"):
        return _extract_pdf(content)
    if filename.endswith(".docx"):
        return _extract_docx(content)

    raise HTTPException(400, "Unsupported file type. Upload a .pdf or .docx file.")


def _extract_pdf(content: bytes) -> str:
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    text = "\n".join(text_parts).strip()
    if not text:
        raise HTTPException(422, "Could not extract any text from this PDF - it may be a scanned image.")
    return text


def _extract_docx(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if not text.strip():
        raise HTTPException(422, "Could not extract any text from this DOCX file.")
    return text
