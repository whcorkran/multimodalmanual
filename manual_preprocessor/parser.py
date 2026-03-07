"""Multimodal document parsing: OCR and layout detection."""

from __future__ import annotations

import numpy as np
from paddleocr import PaddleOCR

from .models import (
    BBox,
    LayoutElement,
    LayoutType,
    NormalizedDocument,
    PageImage,
    ParsedPage,
    TextBlock,
)


class DocumentParser:
    """Run OCR and layout analysis on normalized document pages."""

    def __init__(self, lang: str = "en") -> None:
        self._ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def parse(self, doc: NormalizedDocument) -> list[ParsedPage]:
        """Parse every page in a NormalizedDocument."""
        return [self._parse_page(page) for page in doc.pages]

    # ------------------------------------------------------------------
    # Per-page pipeline
    # ------------------------------------------------------------------

    def _parse_page(self, page: PageImage) -> ParsedPage:
        text_blocks = self.run_ocr(page.image)
        layout_elements = self.detect_layout(page.image, text_blocks)
        figures = [
            el
            for el in layout_elements
            if el.type in {LayoutType.FIGURE, LayoutType.DIAGRAM}
        ]

        return ParsedPage(
            page_number=page.page_number,
            text_blocks=text_blocks,
            figures=figures,
            layout_elements=layout_elements,
        )

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------

    def run_ocr(self, page_image: np.ndarray) -> list[TextBlock]:
        """Extract text blocks with bounding boxes from a page image."""
        result = self._ocr.ocr(page_image, cls=True)
        blocks: list[TextBlock] = []

        if result is None:
            return blocks

        for line_group in result:
            if line_group is None:
                continue
            for detection in line_group:
                box_pts, (text, confidence) = detection
                # box_pts is [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
                xs = [p[0] for p in box_pts]
                ys = [p[1] for p in box_pts]
                bbox = BBox(
                    x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys)
                )
                blocks.append(
                    TextBlock(text=text, bbox=bbox, confidence=float(confidence))
                )

        return blocks

    # ------------------------------------------------------------------
    # Layout / diagram detection
    # ------------------------------------------------------------------

    def detect_layout(
        self,
        page_image: np.ndarray,
        text_blocks: list[TextBlock] | None = None,
    ) -> list[LayoutElement]:
        """Heuristic layout detection based on text block geometry.

        This is a lightweight rule-based detector.  For production use,
        swap in a trained layout model (e.g. LayoutLMv3, YOLO-based).
        """
        if text_blocks is None:
            text_blocks = self.run_ocr(page_image)

        elements: list[LayoutElement] = []
        h, w = page_image.shape[:2]

        for tb in text_blocks:
            el_type = self._classify_block(tb, w, h)
            elements.append(
                LayoutElement(type=el_type, bbox=tb.bbox, text=tb.text)
            )

        # Detect figure regions (large whitespace gaps between text)
        figure_regions = self._detect_figure_regions(page_image, text_blocks)
        elements.extend(figure_regions)

        return elements

    # ------------------------------------------------------------------
    # Heuristic classifiers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_block(tb: TextBlock, page_w: int, page_h: int) -> LayoutType:
        """Classify a text block by simple heuristics."""
        text = tb.text.strip()
        box_h = tb.bbox.height
        avg_char_h = box_h  # single-line assumption

        # Headings: large font, short text
        if avg_char_h > page_h * 0.03 and len(text) < 80:
            return LayoutType.HEADING

        # Numbered/bulleted lists
        if (
            text
            and (text[0].isdigit() or text[0] in "-*\u2022")
            and len(text) < 200
        ):
            return LayoutType.LIST

        # Captions: short, below-center, small
        if len(text) < 60 and tb.bbox.y0 > page_h * 0.6:
            return LayoutType.CAPTION

        return LayoutType.PARAGRAPH

    @staticmethod
    def _detect_figure_regions(
        page_image: np.ndarray, text_blocks: list[TextBlock]
    ) -> list[LayoutElement]:
        """Find large non-text regions that likely contain figures."""
        import cv2

        if not text_blocks:
            return []

        h, w = page_image.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)

        # Mark text regions
        for tb in text_blocks:
            b = tb.bbox
            cv2.rectangle(
                mask,
                (int(b.x0), int(b.y0)),
                (int(b.x1), int(b.y1)),
                255,
                -1,
            )

        # Invert to get non-text regions
        inv = cv2.bitwise_not(mask)
        contours, _ = cv2.findContours(inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        figures: list[LayoutElement] = []
        min_area = h * w * 0.02  # at least 2% of the page

        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw * ch >= min_area:
                figures.append(
                    LayoutElement(
                        type=LayoutType.FIGURE,
                        bbox=BBox(x0=x, y0=y, x1=x + cw, y1=y + ch),
                        text=None,
                    )
                )

        return figures
