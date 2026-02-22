import os
from typing import List
import fitz
from docx import Document as DocxDocument
import chardet
import tiktoken

TEXT_EXTS = {".txt", ".md"}
DOCX_EXTS = {".docx"}
PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

def read_text_file(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()
    enc = chardet.detect(data).get("encoding") or "utf-8"
    return data.decode(enc, errors="ignore")

def read_pdf(path: str) -> str:
    text_parts = []
    with fitz.open(path) as doc:
        for page in doc:
            text_parts.append(page.get_text("text"))
    return "\n".join(text_parts).strip()

def read_docx(path: str) -> str:
    doc = DocxDocument(path)
    return "\n".join([p.text for p in doc.paragraphs]).strip()

def chunk_text_by_tokens(text: str, max_tokens: int, overlap_ratio: float = 0.2, model_name: str = "cl100k_base") -> List[str]:
    if max_tokens <= 0:
        max_tokens = 1024
    enc = tiktoken.get_encoding(model_name)
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return [text]
    step = int(max_tokens * (1 - overlap_ratio))
    chunks = []
    i = 0
    while i < len(tokens):
        window = tokens[i:i+max_tokens]
        if not window:
            break
        chunk_text = enc.decode(window)
        chunks.append(chunk_text)
        if i + max_tokens >= len(tokens):
            break
        i += step
    return chunks

def is_text_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in TEXT_EXTS or ext in DOCX_EXTS or ext in PDF_EXTS

def is_image_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in IMAGE_EXTS
