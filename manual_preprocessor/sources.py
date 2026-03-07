"""Input source handling: web search downloads and user uploads."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from duckduckgo_search import DDGS

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}

_DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "manual_preprocessor_downloads"


class ManualSource:
    """Acquire manuals from web search or user uploads."""

    def __init__(self, download_dir: Path | None = None) -> None:
        self.download_dir = download_dir or _DOWNLOAD_DIR
        self.download_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Web search
    # ------------------------------------------------------------------

    def download_manual_from_query(self, product_query: str) -> Path:
        """Search the web for a product manual PDF and download it.

        Prefers .pdf results.  Falls back to the first downloadable hit.
        """
        query = f"{product_query} instruction manual filetype:pdf"
        results = DDGS().text(query, max_results=10)

        pdf_url: str | None = None
        fallback_url: str | None = None

        for r in results:
            href: str = r.get("href", "")
            if href.lower().endswith(".pdf"):
                pdf_url = href
                break
            if fallback_url is None and href:
                fallback_url = href

        url = pdf_url or fallback_url
        if url is None:
            raise RuntimeError(f"No manual found for query: {product_query!r}")

        return self._download(url)

    # ------------------------------------------------------------------
    # User upload
    # ------------------------------------------------------------------

    @staticmethod
    def load_uploaded_manual(file_path: Path) -> Path:
        """Validate an uploaded manual and return its canonical path."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format {path.suffix!r}. "
                f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
            )
        return path.resolve()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _download(self, url: str) -> Path:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()

        parsed = urlparse(url)
        filename = Path(parsed.path).name or "manual.pdf"
        dest = self.download_dir / filename

        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)

        return dest
