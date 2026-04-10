#!/usr/bin/env python3
"""Scrape SFU Computing Science faculty directory into the FindYourPI JSON schema.

Directory page: https://www.sfu.ca/fas/computing/people/faculty.html

Structure:
  Each <h2> section contains a <ul class="faculty-directory"> with <li> items.
  Each <li> has a <div class="clf-fdi"> containing:
    <div class="clf-fdi__profile">
      <a class="faculty-name" href="/fas/.../name.html">Last, First</a>
      <span class="position">Title</span>
      <a class="faculty-profile-icon email" href="mailto:...">email</a>

  Names are in "Last, First" format — normalized to "First Last" on output.

  Sections included:  School of Computing Science, Adjunct & Associate Faculty
  Sections skipped:   Emeriti & Retired Faculty, In Memoriam

Usage:
  python3 scripts/scrape_sfu_cs_faculty.py
  python3 scripts/scrape_sfu_cs_faculty.py --skip-llm-enrich

Outputs:
  data/sfu_cs_faculty.json
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

DIRECTORY_URL = "https://www.sfu.ca/fas/computing/people/faculty.html"
BASE_URL = "https://www.sfu.ca"
OUTPUT_PATH = Path("data/sfu_cs_faculty.json")

SKIP_SECTIONS = {"emeriti & retired faculty", "in memoriam"}


def _normalize_name(raw: str) -> str:
    """Convert "Last, First" → "First Last". Passes through if no comma."""
    raw = clean_text(raw)
    if "," in raw:
        parts = raw.split(",", 1)
        return f"{parts[1].strip()} {parts[0].strip()}"
    return raw


def _parse_card(div: Tag, section: str) -> FacultyEntry | None:
    profile_div = div.find("div", class_="clf-fdi__profile")
    if not profile_div:
        return None

    name_tag = profile_div.find("a", class_="faculty-name")
    if not name_tag:
        return None

    name = _normalize_name(name_tag.get_text(strip=True))
    if not name:
        return None

    href = name_tag.get("href", "")
    profile_url = (BASE_URL + href) if href.startswith("/") else (href or None)

    title_tag = profile_div.find("span", class_="position")
    title = clean_text(title_tag.get_text(strip=True)) if title_tag else None

    email_tag = profile_div.find("a", class_="email")
    email: str | None = None
    if email_tag and email_tag.get("href", "").startswith("mailto:"):
        email = email_tag["href"].replace("mailto:", "").strip() or None

    return FacultyEntry(
        name=name,
        title=title,
        email=email,
        profile_url=profile_url,
        research_areas=[],
        research_interests=[],
        section=section,
    )


def _iter_sections(soup: BeautifulSoup):
    """Yield (section_title, ul) for included sections only."""
    for h2 in soup.find_all("h2"):
        section_title = clean_text(h2.get_text(strip=True))
        if section_title.lower() in SKIP_SECTIONS:
            continue
        ul = h2.find_next("ul", class_="faculty-directory")
        if ul:
            yield section_title, ul


def scrape(input_html: str | None = None, llm_enrich: bool = True) -> dict:
    soup = BeautifulSoup(
        load_directory_html(input_html, DIRECTORY_URL), "html.parser"
    )

    faculty_entries: list[FacultyEntry] = []
    for section_title, ul in _iter_sections(soup):
        for div in ul.find_all("div", class_="clf-fdi"):
            entry = _parse_card(div, section_title)
            if entry:
                faculty_entries.append(entry)

    if llm_enrich:
        client = get_groq_client()
        total = len(faculty_entries)
        for idx, entry in enumerate(faculty_entries, start=1):
            print(f"  [{idx}/{total}] {entry.name}")
            faculty_entries[idx - 1] = enrich_with_llm(
                entry, client, institution="Simon Fraser University"
            )

    return {
        "institution": "Simon Fraser University",
        "department": "Computing Science",
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
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(payload['faculty'])} entries")


if __name__ == "__main__":
    main()
