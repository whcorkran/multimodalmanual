"""Data models for the manual preprocessing pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np


class LayoutType(str, Enum):
    PARAGRAPH = "paragraph"
    LIST = "list"
    FIGURE = "figure"
    DIAGRAM = "diagram"
    CAPTION = "caption"
    HEADING = "heading"
    TABLE = "table"


@dataclass
class BBox:
    """Axis-aligned bounding box (x0, y0, x1, y1) in pixel coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def to_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass
class PageImage:
    """A single page rendered as an image array."""

    page_number: int
    image: np.ndarray  # HWC uint8
    width: int
    height: int


@dataclass
class NormalizedDocument:
    """Unified internal representation of any input document."""

    pages: list[PageImage]
    text_layers: Optional[list[str]] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TextBlock:
    """A block of text detected by OCR."""

    text: str
    bbox: BBox
    confidence: float


@dataclass
class LayoutElement:
    """A structural element detected in the page layout."""

    type: LayoutType
    bbox: BBox
    text: Optional[str] = None


@dataclass
class ParsedPage:
    """Fully parsed representation of a single page."""

    page_number: int
    text_blocks: list[TextBlock]
    figures: list[LayoutElement]
    layout_elements: list[LayoutElement]


@dataclass
class InstructionStep:
    """A single atomic repair instruction."""

    step_id: int
    raw_text: str
    action: str
    target_object: str
    tool: Optional[str] = None
    parameters: Optional[str] = None
    page_reference: Optional[int] = None


@dataclass
class PreprocessedManual:
    """Final output of the preprocessing pipeline."""

    product_name: str
    steps: list[InstructionStep]
    pages: list[ParsedPage]
    objects: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""

        def _bbox(b: BBox) -> list[float]:
            return b.to_list()

        return {
            "product_name": self.product_name,
            "objects": self.objects,
            "steps": [
                {
                    "step_id": s.step_id,
                    "raw_text": s.raw_text,
                    "action": s.action,
                    "target_object": s.target_object,
                    "tool": s.tool,
                    "parameters": s.parameters,
                    "page_reference": s.page_reference,
                }
                for s in self.steps
            ],
            "pages": [
                {
                    "page_number": p.page_number,
                    "text_blocks": [
                        {
                            "text": tb.text,
                            "bbox": _bbox(tb.bbox),
                            "confidence": tb.confidence,
                        }
                        for tb in p.text_blocks
                    ],
                    "figures": [
                        {
                            "type": le.type.value,
                            "bbox": _bbox(le.bbox),
                            "text": le.text,
                        }
                        for le in p.figures
                    ],
                    "layout_elements": [
                        {
                            "type": le.type.value,
                            "bbox": _bbox(le.bbox),
                            "text": le.text,
                        }
                        for le in p.layout_elements
                    ],
                }
                for p in self.pages
            ],
        }
