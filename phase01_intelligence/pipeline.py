"""
Phase 01 — Manual Acquisition & Preprocessing Pipeline

Two input paths, same output:
  1. User uploads a PDF  ->  parse + classify  ->  ProcessedManual
  2. Machine ID provided  ->  web search + download  ->  parse + classify  ->  ProcessedManual

The ProcessedManual contains structured page text, extracted images,
and classified sections ready for the VLM and subtask generator.
"""

from __future__ import annotations

import json
import logging
import os

from config.settings import Settings, get_settings
from doc_preprocessing.pdf_parser import parse_pdf
from doc_preprocessing.section_classifier import classify_sections
from models.machine_knowledge import ManualSource, ProcessedManual
from phase01_intelligence.crawler import crawl_for_manual

logger = logging.getLogger(__name__)


def process_manual(
    machine_id: str,
    pdf_path: str | None = None,
    settings: Settings | None = None,
    output_dir: str | None = None,
) -> ProcessedManual:
    """
    Acquire and preprocess a machine's operating manual.

    Either processes a user-provided PDF or searches the web for one,
    then parses and classifies it into structured data.

    Args:
        machine_id: Machine name/model identifier.
        pdf_path: Path to a local PDF. If None, searches the web.
        settings: Optional settings override.
        output_dir: Directory for downloaded PDFs and extracted images.

    Returns:
        A ProcessedManual with pages, images, and classified sections.
    """
    if settings is None:
        settings = get_settings()

    if output_dir is None:
        output_dir = os.path.join("output", machine_id.replace(" ", "_"))
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: Acquire the PDF
    if pdf_path:
        logger.info("Using uploaded manual: %s", pdf_path)
        source = ManualSource(origin="upload", local_path=pdf_path)
    else:
        logger.info("Searching web for manual: %s", machine_id)
        result = crawl_for_manual(machine_id, settings, output_dir=output_dir)
        if result is None:
            logger.error("No manual found for '%s'", machine_id)
            return ProcessedManual(
                machine_id=machine_id,
                source=ManualSource(origin="web_search"),
            )
        pdf_path, url, title = result
        source = ManualSource(
            origin="web_search",
            url=url,
            local_path=pdf_path,
            title=title,
        )

    # Step 2: Parse PDF — extract text and images per page
    image_dir = os.path.join(output_dir, "images")
    pages = parse_pdf(pdf_path, image_output_dir=image_dir)

    # Step 3: Classify sections
    sections = classify_sections(pages)

    full_text = "\n".join(p.text for p in pages)

    manual = ProcessedManual(
        machine_id=machine_id,
        source=source,
        pages=pages,
        sections=sections,
        full_text=full_text,
    )

    logger.info(
        "Manual processed: %d pages, %d sections, %d images",
        len(manual.pages),
        len(manual.sections),
        sum(len(p.image_paths) for p in manual.pages),
    )

    return manual


def save_processed_manual(manual: ProcessedManual, path: str) -> None:
    """Serialize a ProcessedManual to JSON (excludes full_text to keep size down)."""
    data = manual.model_dump(exclude={"full_text"})
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info("Processed manual saved to %s", path)
