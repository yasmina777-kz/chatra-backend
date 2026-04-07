"""
services/extractor.py
─────────────────────
Convert uploaded bytes to plain text.

Supported:
  PDF  → pypdf (text layer) or page-by-page Tesseract OCR for scanned pages
  Image (png/jpg/webp/…) → Tesseract OCR
  Plain text / markdown / csv → UTF-8 decode
"""

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_text(data: bytes, filename: str) -> str:
    """
    Returns extracted plain text.
    Raises ValueError for unsupported types.
    """
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        return _extract_pdf(data)

    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}:
        return _ocr_image(data)

    if ext in {".txt", ".md", ".csv", ".log"}:
        return data.decode("utf-8", errors="replace").strip()

    raise ValueError(f"Unsupported file type: {ext}")


# ── PDF ───────────────────────────────────────────────────────────────────────

def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []

    for page_num, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = text.strip()

        if text:
            parts.append(text)
        else:
            # Scanned page — fall back to OCR
            logger.debug("PDF page %d has no text layer, running OCR", page_num)
            ocr_text = _ocr_pdf_page(page)
            if ocr_text:
                parts.append(ocr_text)

    return "\n\n".join(parts)


def _ocr_pdf_page(page) -> str:
    """Render a single pypdf page to image, then run Tesseract."""
    try:
        import pytesseract
        from PIL import Image

        # pypdf ≥ 4: page can render to a PIL image
        pil_image = page.to_image(resolution=200).original  # type: ignore[attr-defined]
        return pytesseract.image_to_string(pil_image, lang="rus+eng").strip()
    except Exception as exc:
        logger.warning("OCR failed for PDF page: %s", exc)
        return ""


# ── Image ─────────────────────────────────────────────────────────────────────

def _ocr_image(data: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(image, lang="rus+eng").strip()
    except Exception as exc:
        logger.error("OCR failed: %s", exc)
        return ""
