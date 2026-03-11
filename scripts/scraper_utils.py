"""Shared utilities for FindYourPI faculty scrapers.

Every school scraper imports from here. School-specific logic (how to find
faculty candidates on a directory page) lives in each scraper. Everything
else — data types, text cleaning, profile enrichment — lives here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class FacultyEntry:
    name: str
    title: str | None
    email: str | None
    profile_url: str | None
    research_areas: list[str] = field(default_factory=list)
    research_interests: list[str] = field(default_factory=list)
    section: str | None = None


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def split_research(field_value: str) -> list[str]:
    """Split a comma/semicolon/pipe-delimited research string into clean items."""
    if not field_value:
        return []
    cleaned = clean_text(field_value)
    parts = re.split(r",|;|/|\band\b|\|", cleaned, flags=re.IGNORECASE)
    seen: set[str] = set()
    output: list[str] = []
    for part in parts:
        p = part.strip()
        key = p.lower()
        if p and key not in seen:
            seen.add(key)
            output.append(p)
    return output


def looks_like_name(value: str) -> bool:
    text = clean_text(value)
    parts = text.split()
    if len(parts) < 2 or len(parts) > 5:
        return False
    return all(part[0].isalpha() for part in parts if part)


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def fetch_html(url: str, timeout: int = 30) -> str:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "FindYourPI/1.0"})
    resp.raise_for_status()
    return resp.text


def load_directory_html(input_html: str | None, directory_url: str) -> str:
    from pathlib import Path
    if input_html:
        html_path = Path(input_html)
        if not html_path.exists():
            raise FileNotFoundError(
                f"Input HTML not found: {html_path}. "
                "Pass a valid file path, or omit --input-html for live scraping."
            )
        return html_path.read_text(encoding="utf-8")
    return fetch_html(directory_url)


# ---------------------------------------------------------------------------
# Field extraction — generic regex over page text
# ---------------------------------------------------------------------------

def extract_labeled_fields(text_blob: str) -> tuple[str | None, list[str], list[str]]:
    """Extract title, research_areas, research_interests from a block of text.

    Works on both flat directory text and full profile page text.
    Returns (title, areas, interests) — any of which may be empty.
    """
    normalized = clean_text(text_blob)

    title: str | None = None
    title_match = re.search(
        r"(?:Position|Title|Rank)\s*:?\s*(.+?)(?=(?:Email|Research|Interests?)\s*:|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if title_match:
        title = clean_text(title_match.group(1))

    research_areas: list[str] = []
    areas_match = re.search(
        r"Research Areas?\s*:?\s*(.+?)(?=(?:Research Interests?|Email)\s*:|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if areas_match:
        research_areas = split_research(areas_match.group(1))

    research_interests: list[str] = []
    interests_match = re.search(
        r"Research Interests?\s*:?\s*(.+?)(?=(?:Research Areas?|Email)\s*:|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if interests_match:
        research_interests = split_research(interests_match.group(1))

    return title, research_areas, research_interests


# ---------------------------------------------------------------------------
# Profile enrichment — fetch each prof's page and fill in missing data
# ---------------------------------------------------------------------------

def enrich_from_profile(entry: FacultyEntry, timeout: int = 20) -> FacultyEntry:
    """Fetch a professor's profile page and fill any missing fields in-place.

    Strategy:
      1. Try labeled-field regex on the full page text (works for most schools).
      2. If research is still empty, walk headings looking for a research
         section and extract from the nearest parent container.
      3. Fall back gracefully — never raises, just returns the entry unchanged.
    """
    if not entry.profile_url:
        return entry

    try:
        html = fetch_html(entry.profile_url, timeout=timeout)
    except Exception:
        return entry

    soup = BeautifulSoup(html, "html.parser")
    page_text = clean_text(soup.get_text(" ", strip=True))

    # Email
    if not entry.email:
        email_match = EMAIL_RE.search(page_text)
        if email_match:
            entry.email = email_match.group(0)

    # Title + research via labeled fields
    title, areas, interests = extract_labeled_fields(page_text)
    if title and not entry.title:
        entry.title = title
    if areas:
        entry.research_areas = areas
    if interests:
        entry.research_interests = interests

    # Heading-based fallback when labeled fields yield nothing
    if not entry.research_areas and not entry.research_interests:
        _enrich_from_headings(soup, entry)

    return entry


def _enrich_from_headings(soup: BeautifulSoup, entry: FacultyEntry) -> None:
    """Walk headings for a research section and extract from its parent container."""
    for h in soup.find_all(["h2", "h3", "h4", "strong", "b"]):
        heading_text = clean_text(h.get_text(" ", strip=True)).lower()
        if "research" not in heading_text and "interest" not in heading_text:
            continue
        parent = h.parent if isinstance(h.parent, Tag) else None
        if not parent:
            continue
        context_text = clean_text(parent.get_text(" ", strip=True))
        _, fallback_areas, fallback_interests = extract_labeled_fields(context_text)
        if fallback_areas:
            entry.research_areas = fallback_areas
        if fallback_interests:
            entry.research_interests = fallback_interests
        if entry.research_areas or entry.research_interests:
            break


# ---------------------------------------------------------------------------
# Convenience: build candidates dict from any anchor list
# ---------------------------------------------------------------------------

def extract_candidates_from_anchors(
    soup: BeautifulSoup,
    base_url: str,
    default_section: str = "Faculty",
) -> dict[str, FacultyEntry]:
    """Generic anchor scan — good starting point for schools without rich markup.

    Each school scraper can call this and then post-process or override.
    """
    candidates: dict[str, FacultyEntry] = {}
    for anchor in soup.find_all("a", href=True):
        name = clean_text(anchor.get_text(" ", strip=True))
        href = anchor["href"].strip()
        if not looks_like_name(name):
            continue
        if not href or href.startswith("#"):
            continue
        profile_url = urljoin(base_url, href)
        key = name.lower()
        if key in candidates:
            continue
        candidates[key] = FacultyEntry(
            name=name,
            title=None,
            email=None,
            profile_url=profile_url,
            section=default_section,
        )
    return candidates