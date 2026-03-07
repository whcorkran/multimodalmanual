"""
PDF Parser

Extracts text and images from each page of a PDF manual using PyMuPDF.
Produces a list of ManualPage objects with per-page text and exported images.
"""

from __future__ import annotations

import logging
import os

import fitz  # pymupdf

from models.machine_knowledge import ManualPage

logger = logging.getLogger(__name__)

# Minimum image dimensions to keep (skip tiny icons/decorations)
MIN_IMAGE_DIM = 100


def parse_pdf(pdf_path: str, image_output_dir: str | None = None) -> list[ManualPage]:
    """
    Parse a PDF file and extract text + images from every page.

    Args:
        pdf_path: Path to the PDF file.
        image_output_dir: Directory to save extracted images.
            If None, images are saved next to the PDF.

    Returns:
        List of ManualPage objects, one per page.
    """
    if image_output_dir is None:
        image_output_dir = os.path.join(os.path.dirname(pdf_path), "images")
    os.makedirs(image_output_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    pages: list[ManualPage] = []

    logger.info("Parsing PDF: %s (%d pages)", pdf_path, len(doc))

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()

        image_paths = _extract_page_images(page, page_num, image_output_dir)

        pages.append(ManualPage(
            page_number=page_num + 1,
            text=text,
            image_paths=image_paths,
        ))

    doc.close()

    total_images = sum(len(p.image_paths) for p in pages)
    logger.info("Parsed %d pages, extracted %d images", len(pages), total_images)

    return pages


def _extract_page_images(
    page: fitz.Page,
    page_num: int,
    output_dir: str,
) -> list[str]:
    """Extract images from a single PDF page and save to disk."""
    image_paths: list[str] = []
    image_list = page.get_images(full=True)

    for img_idx, img_info in enumerate(image_list):
        xref = img_info[0]
        try:
            base_image = page.parent.extract_image(xref)
        except Exception:
            continue

        if not base_image or not base_image.get("image"):
            continue

        width = base_image.get("width", 0)
        height = base_image.get("height", 0)
        if width < MIN_IMAGE_DIM or height < MIN_IMAGE_DIM:
            continue

        ext = base_image.get("ext", "png")
        filename = f"page{page_num + 1:04d}_img{img_idx:03d}.{ext}"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "wb") as f:
            f.write(base_image["image"])

        image_paths.append(filepath)

    return image_paths
