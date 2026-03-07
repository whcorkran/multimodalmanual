"""
Manual Document Crawler

Creates a Browserbase session, connects Playwright, and searches for
PDF operating manuals for a given machine. Stops after finding results
or after a 2-minute timeout. Downloads the first PDF found.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
import urllib.request

from browserbase import Browserbase
from playwright.sync_api import Page, sync_playwright

from config.settings import Settings

logger = logging.getLogger(__name__)

SEARCH_TIMEOUT = 120  # 2 minutes total search budget


def _build_search_queries(machine_id: str) -> list[str]:
    """Generate search queries targeting PDF manuals."""
    return [
        f"{machine_id} operating manual filetype:pdf",
        f"{machine_id} user guide filetype:pdf",
        f"{machine_id} service manual filetype:pdf",
        f"{machine_id} instruction manual pdf",
        f"{machine_id} owner's manual pdf",
    ]


def _extract_pdf_urls(page: Page, max_results: int) -> list[tuple[str, str]]:
    """Extract PDF links from a Google search results page. Returns (url, title) pairs."""
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    links = page.query_selector_all("div#search a[href]")
    for link in links:
        href = link.get_attribute("href") or ""
        if not href or "google." in href:
            continue

        is_pdf = href.lower().endswith(".pdf") or ".pdf" in href.lower()
        if not is_pdf:
            continue

        if href in seen:
            continue
        seen.add(href)

        title = link.inner_text().strip() or href.split("/")[-1]
        results.append((href, title))

        if len(results) >= max_results:
            break

    return results


def download_pdf(url: str, output_dir: str) -> str:
    """Download a PDF from a URL and return the local file path."""
    filename = url.split("/")[-1].split("?")[0]
    if not filename.endswith(".pdf"):
        filename += ".pdf"
    local_path = os.path.join(output_dir, filename)
    logger.info("Downloading PDF: %s -> %s", url, local_path)
    urllib.request.urlretrieve(url, local_path)
    return local_path


def crawl_for_manual(
    machine_id: str,
    settings: Settings,
    output_dir: str | None = None,
) -> tuple[str, str, str] | None:
    """
    Search the web for a PDF operating manual and download it.

    Returns:
        (local_path, url, title) of the first PDF found, or None if nothing found.
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="manual_")

    start_time = time.monotonic()

    bb = Browserbase(api_key=settings.browserbase_api_key)
    session = bb.sessions.create(
        project_id=settings.browserbase_project_id,
        browser_settings={"blockAds": True},
    )

    logger.info("Created Browserbase session: %s", session.id)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(session.connect_url)
        context = browser.contexts[0]
        page = context.pages[0]

        queries = _build_search_queries(machine_id)

        for query in queries:
            elapsed = time.monotonic() - start_time
            if elapsed >= SEARCH_TIMEOUT:
                logger.warning("Search timeout reached (%.0fs). Stopping.", elapsed)
                break

            logger.info("Searching: %s", query)
            try:
                page.goto(
                    f"https://www.google.com/search?q={query.replace(' ', '+')}",
                    timeout=settings.crawler_timeout * 1000,
                )
                page.wait_for_load_state("domcontentloaded")

                pdf_results = _extract_pdf_urls(page, settings.max_pages_per_search)
                for url, title in pdf_results:
                    logger.info("Found manual: %s", title[:80])
                    try:
                        local_path = download_pdf(url, output_dir)
                        browser.close()
                        elapsed = time.monotonic() - start_time
                        logger.info("Manual downloaded in %.0fs", elapsed)
                        return local_path, url, title
                    except Exception:
                        logger.warning("Failed to download %s", url, exc_info=True)

            except Exception:
                logger.warning("Failed search query: %s", query, exc_info=True)

        browser.close()

    elapsed = time.monotonic() - start_time
    logger.warning("No manuals found after %.0fs", elapsed)
    return None
