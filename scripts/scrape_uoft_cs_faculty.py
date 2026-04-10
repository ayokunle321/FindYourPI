#!/usr/bin/env python3
"""Scrape UofT CS faculty directory into the FindYourPI JSON schema.

The directory page uses a clean HTML table with 3 columns:
  [Name & Position] | [Contact] | [Research]

We parse that table directly instead of flattening tokens, which gives us
clean research areas and interests without any sentence bleed.

Usage:
  python3 scripts/scrape_uoft_cs_faculty.py
  python3 scripts/scrape_uoft_cs_faculty.py --input-html data/uoft_faculty_page.html
  python3 scripts/scrape_uoft_cs_faculty.py --skip-profile-enrich

Outputs:
  data/uoft_cs_faculty.json
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
    split_research,
)

DIRECTORY_URL = "https://web.cs.toronto.edu/people/faculty-directory"
OUTPUT_PATH = Path("data/uoft_cs_faculty.json")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _parse_name_cell(cell: Tag) -> tuple[str | None, str | None, str | None]:
    """Return (name, title, profile_url) from the name+position table cell."""
    anchor = cell.find("a")
    name = clean_text(anchor.get_text(" ", strip=True)) if anchor else None
    profile_url = anchor["href"] if anchor and anchor.get("href") else None

    cell_text = clean_text(cell.get_text(" ", strip=True))
    if name:
        title_blob = cell_text.replace(name, "", 1).strip()
    else:
        title_blob = cell_text

    # Take only the first meaningful chunk — strip admin role annotations.
    title = re.split(r"\s{2,}|\n", title_blob)[0].strip() if title_blob else None
    title = title or None

    return name, title, profile_url


def _parse_research_cell(cell: Tag) -> tuple[list[str], list[str]]:
    """Return (research_areas, research_interests) from the research table cell.

    The cell looks like:
      <strong>Research Areas:</strong> topic, topic
      <strong>Research Interests:</strong> interest; interest

    We locate the bold labels and grab the text that immediately follows each.
    """
    research_areas: list[str] = []
    research_interests: list[str] = []

    for bold in cell.find_all(["strong", "b"]):
        label = clean_text(bold.get_text()).lower()

        # Collect text siblings until the next bold tag.
        following_parts: list[str] = []
        for sibling in bold.next_siblings:
            if isinstance(sibling, Tag) and sibling.name in {"strong", "b"}:
                break
            sibling_text = clean_text(
                sibling.get_text(" ", strip=True)
                if isinstance(sibling, Tag)
                else str(sibling)
            )
            if sibling_text:
                following_parts.append(sibling_text)

        following = clean_text(" ".join(following_parts))
        # Strip trailing "not accepting new students" notes.
        following = re.sub(
            r"\*?Professor\s+\w+\s+is not accepting.*",
            "",
            following,
            flags=re.IGNORECASE,
        ).strip()

        if "research areas" in label:
            research_areas = split_research(following)
        elif "research interests" in label:
            research_interests = split_research(following)

    return research_areas, research_interests


def _parse_contact_cell(cell: Tag) -> str | None:
    email_match = EMAIL_RE.search(cell.get_text())
    return email_match.group(0) if email_match else None


def _parse_table(table: Tag, section: str | None) -> list[FacultyEntry]:
    entries: list[FacultyEntry] = []

    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells or cells[0].name == "th":
            continue
        if len(cells) < 2:
            continue

        name, title, profile_url = _parse_name_cell(cells[0])
        if not name:
            continue

        research_areas: list[str] = []
        research_interests: list[str] = []
        email: str | None = None

        for cell in cells[1:]:
            cell_text = cell.get_text()
            if "Research" in cell_text and not research_areas and not research_interests:
                research_areas, research_interests = _parse_research_cell(cell)
            if EMAIL_RE.search(cell_text) and not email:
                email = _parse_contact_cell(cell)

        entries.append(
            FacultyEntry(
                name=name,
                title=title,
                email=email,
                profile_url=profile_url,
                research_areas=research_areas,
                research_interests=research_interests,
                section=section,
            )
        )

    return entries


def _iter_sections(soup: BeautifulSoup):
    """Yield (section_title, table) pairs by walking H2 headings."""
    for heading in soup.find_all("h2"):
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
                entry, client, institution="University of Toronto"
            )

    return {
        "institution": "University of Toronto",
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