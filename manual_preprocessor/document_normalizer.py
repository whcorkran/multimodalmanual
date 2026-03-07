"""Convert any supported document into a NormalizedDocument."""

from __future__ import annotations

from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np

from .models import NormalizedDocument, PageImage

# ---------------------------------------------------------------
# Public API
# ---------------------------------------------------------------


def normalize_document(file_path: Path) -> NormalizedDocument:
    """Entry point: dispatch on file extension."""
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return _normalize_pdf(file_path)
    if ext in {".png", ".jpg", ".jpeg", ".tiff", ".tif"}:
        return _normalize_image(file_path)
    raise ValueError(f"Unsupported file type: {ext}")


# ---------------------------------------------------------------
# PDF handling
# ---------------------------------------------------------------


def _normalize_pdf(pdf_path: Path) -> NormalizedDocument:
    doc = fitz.open(str(pdf_path))
    pages: list[PageImage] = []
    text_layers: list[str] = []

    for page_num, page in enumerate(doc):
        # Embedded text
        text_layers.append(page.get_text())

        # Render page to image at 150 DPI (good balance of speed/quality)
        pix = page.get_pixmap(dpi=150)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        if pix.n == 4:  # RGBA -> RGB
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)

        pages.append(
            PageImage(
                page_number=page_num,
                image=img,
                width=img.shape[1],
                height=img.shape[0],
            )
        )

    doc.close()

    return NormalizedDocument(
        pages=pages,
        text_layers=text_layers,
        metadata={"source": str(pdf_path), "page_count": len(pages)},
    )


# ---------------------------------------------------------------
# Image handling
# ---------------------------------------------------------------


def _normalize_image(image_path: Path) -> NormalizedDocument:
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")

    img = _preprocess_image(img)

    page = PageImage(
        page_number=0,
        image=img,
        width=img.shape[1],
        height=img.shape[0],
    )

    return NormalizedDocument(
        pages=[page],
        text_layers=None,
        metadata={"source": str(image_path), "page_count": 1},
    )


# ---------------------------------------------------------------
# Image preprocessing helpers
# ---------------------------------------------------------------


def _preprocess_image(img: np.ndarray) -> np.ndarray:
    """Deskew, denoise, and normalize contrast."""
    img = _deskew(img)
    img = _denoise(img)
    img = _normalize_contrast(img)
    return img


def _deskew(img: np.ndarray) -> np.ndarray:
    """Correct small rotation using Hough line detection."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=100, maxLineGap=10)

    if lines is None:
        return img

    angles: list[float] = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if abs(angle) < 15:  # only consider near-horizontal lines
            angles.append(angle)

    if not angles:
        return img

    median_angle = float(np.median(angles))
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _denoise(img: np.ndarray) -> np.ndarray:
    """Light non-local-means denoising."""
    return cv2.fastNlMeansDenoisingColored(img, None, 6, 6, 7, 21)


def _normalize_contrast(img: np.ndarray) -> np.ndarray:
    """CLAHE contrast normalization on the L channel."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
