"""Main preprocessing pipeline: source -> structured manual JSON."""

from __future__ import annotations

from pathlib import Path

from .document_normalizer import normalize_document
from .instruction_extractor import extract_all_instructions
from .models import PreprocessedManual
from .parser import DocumentParser
from .sources import ManualSource


def preprocess_manual(
    source_input: str | Path,
    *,
    product_name: str | None = None,
    lang: str = "en",
) -> PreprocessedManual:
    """End-to-end pipeline: input -> normalization -> parsing -> extraction.

    Args:
        source_input: Either a file path (Path or str to existing file)
                      or a product query string for web search.
        product_name: Override the product name in the output.
                      Defaults to the query or file stem.
        lang: OCR language code (default "en").

    Returns:
        PreprocessedManual ready for JSON serialization.
    """
    source = ManualSource()

    # 1. Acquire the file
    path = Path(source_input)
    if path.exists():
        file_path = source.load_uploaded_manual(path)
        product_name = product_name or path.stem
    else:
        # Treat as a search query
        query = str(source_input)
        file_path = source.download_manual_from_query(query)
        product_name = product_name or query

    # 2. Normalize
    normalized = normalize_document(file_path)

    # 3. Parse (OCR + layout)
    parser = DocumentParser(lang=lang)
    parsed_pages = parser.parse(normalized)

    # 4. Extract instructions
    steps = extract_all_instructions(parsed_pages)

    # 5. Collect unique objects
    objects = sorted({s.target_object for s in steps if s.target_object != "component"})

    return PreprocessedManual(
        product_name=product_name,
        steps=steps,
        pages=parsed_pages,
        objects=objects,
    )
