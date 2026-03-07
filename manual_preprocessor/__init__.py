"""Manual preprocessor — convert messy manuals into structured JSON for VLM repair assistance."""

from .models import (
    BBox,
    InstructionStep,
    LayoutElement,
    LayoutType,
    NormalizedDocument,
    PageImage,
    ParsedPage,
    PreprocessedManual,
    TextBlock,
)
from .pipeline import preprocess_manual

__all__ = [
    "preprocess_manual",
    "BBox",
    "InstructionStep",
    "LayoutElement",
    "LayoutType",
    "NormalizedDocument",
    "PageImage",
    "ParsedPage",
    "PreprocessedManual",
    "TextBlock",
]
