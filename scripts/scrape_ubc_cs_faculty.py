#!/usr/bin/env python3
"""Scrape UBC CS faculty directory into the FindYourPI JSON schema.

The directory page is a clean HTML table with columns:
  [Photo] | [Name + links] | [Contact Info] | [Research Areas] | [Research Groups]

Research areas are already structured as <a> tags in the Research Areas column —
no regex, no profile page fetching needed for most faculty.

Usage:
  python3 scripts/scrape_ubc_cs_faculty.py
  python3 scripts/scrape_ubc_cs_faculty.py --input-html data/ubc_faculty_page.html
  python3 scripts/scrape_ubc_cs_faculty.py --skip-profile-enrich

Outputs:
  data/ubc_cs_faculty.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from scraper_utils import (
    FacultyEntry,
    clean_text,
    enrich_with_llm,
    get_groq_client,
    load_directory_html,
)

DIRECTORY_URL = "https://www.cs.ubc.ca/people/faculty"
BASE_URL = "https://www.cs.ubc.ca"
OUTPUT_PATH = Path("data/ubc_cs_faculty.json")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Research area links all point to /cs-research/research-area/...
RESEARCH_AREA_HREF_RE = re.compile(r"/cs-research/research-area/")


def _parse_name_cell(cell: Tag) -> tuple[str | None, str | None, str | None]:
    """Return (name, title, profile_url) from the name cell.

    The cell contains:
      - An <a> linking to /people/<slug> — that's the profile
      - Possibly additional <a> tags for Personal Page / Google Scholar
      - Plain text for the job title
    """
    profile_anchor = cell.find("a", href=re.compile(r"^/people/"))
    if not profile_anchor:
        return None, None, None

    name = clean_text(profile_anchor.get_text(" ", strip=True))
    profile_url = BASE_URL + profile_anchor["href"]

    # Title is whatever text remains after removing all anchor text.
    full_text = clean_text(cell.get_text(" ", strip=True))
    for anchor in cell.find_all("a"):
        full_text = full_text.replace(
            clean_text(anchor.get_text(" ", strip=True)), ""
        )
    title = clean_text(full_text) or None

    return name, title, profile_url


def _parse_research_cell(cell: Tag) -> list[str]:
    """Extract research area tags from the research areas column.

    Each area is an <a> tag pointing to /cs-research/research-area/<slug>.
    We just read the link text — no regex needed.
    """
    areas: list[str] = []
    for anchor in cell.find_all("a", href=RESEARCH_AREA_HREF_RE):
        label = clean_text(anchor.get_text(" ", strip=True))
        if label:
            areas.append(label)
    return areas


def _parse_contact_cell(cell: Tag) -> str | None:
    email_match = EMAIL_RE.search(cell.get_text())
    return email_match.group(0) if email_match else None


def _parse_table(table: Tag, section: str | None) -> list[FacultyEntry]:
    entries: list[FacultyEntry] = []

    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        # Skip header rows and rows with too few cells.
        if not cells or cells[0].name == "th" or len(cells) < 3:
            continue

        # Column layout: [photo/initials] [name+links] [contact] [research areas] [research groups]
        # We match by content rather than index since some rows vary.
        name_cell = None
        contact_cell = None
        research_cell = None

        for cell in cells:
            cell_text = cell.get_text()
            if cell.find("a", href=re.compile(r"^/people/")):
                name_cell = cell
            elif EMAIL_RE.search(cell_text) and not contact_cell:
                contact_cell = cell
            elif cell.find("a", href=RESEARCH_AREA_HREF_RE) and not research_cell:
                research_cell = cell

        if not name_cell:
            continue

        name, title, profile_url = _parse_name_cell(name_cell)
        if not name:
            continue

        email = _parse_contact_cell(contact_cell) if contact_cell else None
        research_areas = _parse_research_cell(research_cell) if research_cell else []

        entries.append(
            FacultyEntry(
                name=name,
                title=title,
                email=email,
                profile_url=profile_url,
                research_areas=research_areas,
                research_interests=[],
                section=section,
            )
        )

    return entries


def _iter_sections(soup: BeautifulSoup):
    """Yield (section_title, table) for each H3 section heading."""
    for heading in soup.find_all("h3"):
        section_title = clean_text(heading.get_text(" ", strip=True))
        table = heading.find_next("table")
        if table:
            yield section_title, table


def scrape(input_html: str | None = None, llm_enrich: bool = True) -> dict:
    soup = BeautifulSoup(
        load_directory_html(input_html, DIRECTORY_URL), "html.parser"
    )

    faculty_entries: list[FacultyEntry] = []
    for section_title, table in _iter_sections(soup):
        faculty_entries.extend(_parse_table(table, section_title))

    if llm_enrich:
        client = get_groq_client()
        total = len(faculty_entries)
        for idx, entry in enumerate(faculty_entries, start=1):
            print(f"  [{idx}/{total}] {entry.name}")
            faculty_entries[idx - 1] = enrich_with_llm(
                entry, client, institution="University of British Columbia"
            )

    return {
        "institution": "University of British Columbia",
        "department": "Computer Science",
        "directory_url": DIRECTORY_URL,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "faculty": [asdict(entry) for entry in faculty_entries],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-html", default=None)
    parser.add_argument("--skip-llm-enrich", action="store_true",
                        help="Skip Groq LLM tag extraction (no GROQ_API_KEY needed)")
    args = parser.parse_args()

    payload = scrape(
        input_html=args.input_html,
        llm_enrich=not args.skip_llm_enrich,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(payload['faculty'])} entries")


if __name__ == "__main__":
    main()