"""
Image and PDF processor for Handwritten Notes and Documents.

Handles:
  - Validating and inspecting image files (.png, .jpg, .jpeg) and PDFs (.pdf)
  - Converting PDF pages to high-resolution JPEG/PNG base64 strings in memory
  - Batching multi-page documents to respect API context limits
"""

import base64
from pathlib import Path
from typing import List, Dict, Any

try:
    import pymupdf  # Modern PyMuPDF API
except ImportError:
    import fitz as pymupdf  # Fallback


SUPPORTED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg'}


def is_supported_document(file_path: str | Path) -> bool:
    """Check if the file format is supported."""
    return Path(file_path).suffix.lower() in SUPPORTED_EXTENSIONS


def get_document_info(file_path: str | Path) -> Dict[str, Any]:
    """
    Get metadata for a document or image file.

    Returns dict with:
      - filename: str
      - extension: str
      - size_bytes: int
      - page_count: int
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: {ext}. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    size = path.stat().st_size

    if ext == '.pdf':
        doc = pymupdf.open(str(path))
        page_count = len(doc)
        doc.close()
    else:
        page_count = 1

    return {
        "filename": path.name,
        "extension": ext,
        "size_bytes": size,
        "page_count": page_count,
    }


def load_document_images_b64(
    file_path: str | Path,
    zoom_factor: float = 2.0,
) -> List[str]:
    """
    Load a document (PDF or Image) and convert pages to base64 JPEG strings.

    Args:
        file_path: Path to the file (.pdf, .png, .jpg, .jpeg).
        zoom_factor: Resolution multiplier for PDF rendering (2.0 = ~150 DPI).

    Returns:
        List of base64-encoded image strings (one per page / image).
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file extension: {ext}")

    b64_list = []

    if ext == '.pdf':
        doc = pymupdf.open(str(path))
        mat = pymupdf.Matrix(zoom_factor, zoom_factor)

        for page in doc:
            # Render page to pixmap at high DPI for clear handwriting recognition
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("jpeg")
            b64_str = base64.b64encode(img_bytes).decode('utf-8')
            b64_list.append(b64_str)

        doc.close()
    else:
        # Single image file
        with open(path, "rb") as f:
            img_bytes = f.read()
        b64_str = base64.b64encode(img_bytes).decode('utf-8')
        b64_list.append(b64_str)

    return b64_list


def batch_images(
    images_b64: List[str],
    batch_size: int = 4,
) -> List[List[str]]:
    """
    Split a list of base64 page images into batches.

    Args:
        images_b64: List of base64 strings.
        batch_size: Max pages per batch (default 4).

    Returns:
        List of batches, each containing up to batch_size images.
    """
    if not images_b64:
        return []

    return [
        images_b64[i : i + batch_size]
        for i in range(0, len(images_b64), batch_size)
    ]
