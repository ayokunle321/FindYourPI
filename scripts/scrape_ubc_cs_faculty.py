#!/usr/bin/env python3
"""Scrape UBC CS faculty directory into the FindYourPI JSON schema.

Usage:
  python3 scripts/scrape_ubc_cs_faculty.py
  python3 scripts/scrape_ubc_cs_faculty.py --input-html data/ubc_faculty_page.html

Outputs:
  data/ubc_cs_faculty.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

DIRECTORY_URL = "https://www.cs.ubc.ca/people/faculty"
BASE_URL = "https://www.cs.ubc.ca"
OUTPUT_PATH = Path("data/ubc_cs_faculty.json")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class FacultyEntry:
    name: str
    title: str | None
    email: str | None
    profile_url: str | None
    research_areas: list[str]
    research_interests: list[str]
    section: str | None


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _split_research(field_value: str) -> list[str]:
    if not field_value:
        return []
    cleaned = _clean_text(field_value)
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


def _looks_like_name(value: str) -> bool:
    text = _clean_text(value)
    parts = text.split()
    if len(parts) < 2 or len(parts) > 5:
        return False
    return all(part[0].isalpha() for part in parts if part)


def _fetch_html(url: str, timeout: int = 30) -> str:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def _load_directory_html(input_html: str | None) -> str:
    if input_html:
        html_path = Path(input_html)
        if not html_path.exists():
            raise FileNotFoundError(
                f"Input HTML not found: {html_path}. "
                "Pass a valid file path, or omit --input-html for live scraping."
            )
        return html_path.read_text(encoding="utf-8")
    return _fetch_html(DIRECTORY_URL)


def _extract_faculty_candidates(soup: BeautifulSoup) -> dict[str, FacultyEntry]:
    candidates: dict[str, FacultyEntry] = {}
    for anchor in soup.find_all("a", href=True):
        name = _clean_text(anchor.get_text(" ", strip=True))
        href = anchor["href"].strip()
        if not _looks_like_name(name):
            continue
        if not href or href.startswith("#"):
            continue
        profile_url = urljoin(BASE_URL, href)
        key = name.lower()
        if key in candidates:
            continue
        candidates[key] = FacultyEntry(
            name=name,
            title=None,
            email=None,
            profile_url=profile_url,
            research_areas=[],
            research_interests=[],
            section="Faculty",
        )
    return candidates


def _extract_labeled_fields(text_blob: str) -> tuple[str | None, list[str], list[str]]:
    normalized = _clean_text(text_blob)

    title = None
    title_match = re.search(
        r"(?:Position|Title|Rank)\s*:?\s*(.+?)(?=(?:Email|Research|Interests?)\s*:|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if title_match:
        title = _clean_text(title_match.group(1))

    research_areas: list[str] = []
    research_interests: list[str] = []

    areas_match = re.search(
        r"Research Areas?\s*:?\s*(.+?)(?=(?:Research Interests?|Email|$))",
        normalized,
        flags=re.IGNORECASE,
    )
    if areas_match:
        research_areas = _split_research(areas_match.group(1))

    interests_match = re.search(
        r"Research Interests?\s*:?\s*(.+?)(?=(?:Research Areas?|Email|$))",
        normalized,
        flags=re.IGNORECASE,
    )
    if interests_match:
        research_interests = _split_research(interests_match.group(1))

    return title, research_areas, research_interests


def _enrich_from_profile(entry: FacultyEntry, timeout: int = 20) -> FacultyEntry:
    if not entry.profile_url:
        return entry

    try:
        html = _fetch_html(entry.profile_url, timeout=timeout)
    except Exception:
        return entry

    soup = BeautifulSoup(html, "html.parser")
    page_text = _clean_text(soup.get_text(" ", strip=True))

    if not entry.email:
        email_match = EMAIL_RE.search(page_text)
        if email_match:
            entry.email = email_match.group(0)

    title, areas, interests = _extract_labeled_fields(page_text)
    if title and not entry.title:
        entry.title = title
    if areas:
        entry.research_areas = areas
    if interests:
        entry.research_interests = interests

    # Fallback: collect topic chips near research-related headings.
    if not entry.research_areas and not entry.research_interests:
        headings = soup.find_all(["h2", "h3", "h4", "strong", "b"])
        for h in headings:
            heading_text = _clean_text(h.get_text(" ", strip=True)).lower()
            if "research" not in heading_text and "interest" not in heading_text:
                continue
            parent = h.parent if isinstance(h.parent, Tag) else None
            context_text = _clean_text(parent.get_text(" ", strip=True)) if parent else ""
            _, fallback_areas, fallback_interests = _extract_labeled_fields(context_text)
            if fallback_areas:
                entry.research_areas = fallback_areas
            if fallback_interests:
                entry.research_interests = fallback_interests
            if entry.research_areas or entry.research_interests:
                break

    return entry


def scrape(input_html: str | None = None, enrich_profiles: bool = True) -> dict:
    directory_html = _load_directory_html(input_html)
    soup = BeautifulSoup(directory_html, "html.parser")

    candidates = _extract_faculty_candidates(soup)
    entries = list(candidates.values())

    if enrich_profiles:
        for idx, entry in enumerate(entries, start=1):
            entries[idx - 1] = _enrich_from_profile(entry)
            if idx % 25 == 0:
                print(f"Enriched {idx}/{len(entries)} profiles...")

    payload = {
        "institution": "University of British Columbia",
        "department": "Computer Science",
        "directory_url": DIRECTORY_URL,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "faculty": [asdict(entry) for entry in entries],
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-html",
        default=None,
        help="Optional local directory HTML path (useful when network is blocked).",
    )
    parser.add_argument(
        "--skip-profile-enrich",
        action="store_true",
        help="Skip per-profile fetches and output names/links only.",
    )
    args = parser.parse_args()

    payload = scrape(
        input_html=args.input_html,
        enrich_profiles=not args.skip_profile_enrich,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(payload['faculty'])} entries")


if __name__ == "__main__":
    main()
