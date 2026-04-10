#!/usr/bin/env python3
"""Scrape McGill CS faculty directory into the FindYourPI JSON schema.

The directory page is a list of accordion cards. Each card's heading (<h4>)
contains:
  Line 1: Professor name
  Lines 2+: Research area topics (one per line)

The contact details (email, office, website) live inside the collapsed body of
each card. Section headings are <h2> tags (Professors, Faculty Lecturers, etc.)

Everything we need is on the directory page — no profile fetching required.

Usage:
  python3 scripts/scrape_mcgill_cs_faculty.py
  python3 scripts/scrape_mcgill_cs_faculty.py --input-html data/mcgill_faculty_page.html
  python3 scripts/scrape_mcgill_cs_faculty.py --skip-profile-enrich

Outputs:
  data/mcgill_cs_faculty.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from scraper_utils import (
    FacultyEntry,
    clean_text,
    enrich_with_llm,
    get_groq_client,
    load_directory_html,
)

DEFAULT_DIRECTORY_URL = "https://www.cs.mcgill.ca/people/faculty/"
BASE_URL = "https://www.cs.mcgill.ca"
OUTPUT_PATH = Path("data/mcgill_cs_faculty.json")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Noise lines that appear in card headings but are not research topics.
# Typically department affiliations like "(Mathematics and Statistics)".
AFFILIATION_RE = re.compile(r"^\(.*\)$")


def _parse_card(card: Tag, section: str | None) -> FacultyEntry | None:
    """Parse a single accordion faculty card into a FacultyEntry.

    Card structure:
      <a href="#collapse-N">
        <h4>
          Name
          Research Area 1
          Research Area 2
          ...
          <img .../>
        </h4>
      </a>
      <div id="collapse-N">
        <a href="website">Website</a>
        Office: ...
        Email: user@cs.mcgill.ca
      </div>
    """
    heading = card.find("h4")
    if not heading:
        return None

    # Get all direct text lines from the heading, ignoring the <img> tag.
    raw_lines = [
        clean_text(line)
        for line in heading.get_text("\n", strip=True).split("\n")
        if clean_text(line)
    ]

    if not raw_lines:
        return None

    name = raw_lines[0]

    # Lines 2+ are research areas, but skip affiliation notes like "(Psychology)".
    research_areas = [
        line for line in raw_lines[1:]
        if line and not AFFILIATION_RE.match(line)
    ]

    # card IS the <a href="#collapse-N"> anchor — read the id from it directly.
    body_id = card.get("href", "").lstrip("#")
    body = card.find_next("div", id=body_id) if body_id else None

    email: str | None = None
    profile_url: str | None = None
    title: str | None = None

    if body:
        body_text = body.get_text()
        email_match = EMAIL_RE.search(body_text)
        if email_match:
            email = email_match.group(0)

        # Website link
        website_anchor = body.find("a", string=re.compile(r"Website", re.IGNORECASE))
        if website_anchor and website_anchor.get("href"):
            href = website_anchor["href"].strip()
            profile_url = href if href.startswith("http") else urljoin(BASE_URL, href)

        # Title: look for lines containing rank keywords
        for line in body_text.split("\n"):
            line = clean_text(line)
            if re.search(
                r"\b(Professor|Lecturer|Director|Adjunct|Associate|Assistant)\b",
                line,
                re.IGNORECASE,
            ):
                title = line
                break

    return FacultyEntry(
        name=name,
        title=title,
        email=email,
        profile_url=profile_url,
        research_areas=research_areas,
        research_interests=[],
        section=section,
    )


def _iter_sections(soup: BeautifulSoup):
    """Yield (section_title, [card_elements]) by walking H2 headings."""
    for heading in soup.find_all("h2"):
        section_title = clean_text(heading.get_text(" ", strip=True))

        # Skip non-faculty headings.
        if not any(
            kw in section_title.lower()
            for kw in ("professor", "lecturer", "member", "emeritus", "memoriam", "director", "former")
        ):
            continue

        # Collect all accordion card anchors until the next h2.
        cards: list[Tag] = []
        for sibling in heading.next_siblings:
            if isinstance(sibling, Tag):
                if sibling.name == "h2":
                    break
                # Each card is an <a> wrapping an <h4> with a collapse href.
                if sibling.name == "a" and sibling.find("h4"):
                    cards.append(sibling)
                # Or they might be wrapped in a div
                cards.extend(
                    a for a in sibling.find_all("a", recursive=True)
                    if a.find("h4") and a.get("href", "").startswith("#collapse-")
                )

        if cards:
            yield section_title, cards


def scrape(
    directory_url: str = DEFAULT_DIRECTORY_URL,
    input_html: str | None = None,
    llm_enrich: bool = True,
) -> dict:
    soup = BeautifulSoup(
        load_directory_html(input_html, directory_url), "html.parser"
    )

    faculty_entries: list[FacultyEntry] = []
    for section_title, cards in _iter_sections(soup):
        for card in cards:
            entry = _parse_card(card, section_title)
            if entry and entry.name:
                faculty_entries.append(entry)

    # Deduplicate by name (card iteration can sometimes double-count).
    seen: set[str] = set()
    unique_entries: list[FacultyEntry] = []
    for entry in faculty_entries:
        key = entry.name.lower()
        if key not in seen:
            seen.add(key)
            unique_entries.append(entry)
    faculty_entries = unique_entries

    if llm_enrich:
        client = get_groq_client()
        total = len(faculty_entries)
        for idx, entry in enumerate(faculty_entries, start=1):
            print(f"  [{idx}/{total}] {entry.name}")
            faculty_entries[idx - 1] = enrich_with_llm(
                entry, client, institution="McGill University"
            )

    return {
        "institution": "McGill University",
        "department": "Computer Science",
        "directory_url": directory_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "faculty": [asdict(entry) for entry in faculty_entries],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory-url", default=DEFAULT_DIRECTORY_URL)
    parser.add_argument("--input-html", default=None)
    parser.add_argument("--skip-llm-enrich", action="store_true",
                        help="Skip Groq LLM tag extraction (no GROQ_API_KEY needed)")
    args = parser.parse_args()

    payload = scrape(
        directory_url=args.directory_url,
        input_html=args.input_html,
        llm_enrich=not args.skip_llm_enrich,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(payload['faculty'])} entries")


if __name__ == "__main__":
    main()