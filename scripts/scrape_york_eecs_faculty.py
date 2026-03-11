#!/usr/bin/env python3
"""Scrape York University EECS faculty directory into the FindYourPI JSON schema.

The directory page (lassonde.yorku.ca/eecs/faculty/) lists all faculty as:
  <h2><a href="/users/<slug>/">Name</a></h2>
  <h3>Title</h3>
  <a href="mailto:...">email</a>

Research data lives on each prof's profile page at /users/<slug>/ under a
"Research Interests" heading followed by a <ul> list.

So this scraper:
  1. Parses the directory page for name, title, email, profile_url
  2. Fetches each profile page for research interests (enrich_profiles=True)

Usage:
  python3 scripts/scrape_york_eecs_faculty.py
  python3 scripts/scrape_york_eecs_faculty.py --input-html data/york_faculty_page.html
  python3 scripts/scrape_york_eecs_faculty.py --skip-profile-enrich

Outputs:
  data/york_eecs_faculty.json
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
    fetch_html,
    load_directory_html,
)

DIRECTORY_URL = "https://lassonde.yorku.ca/eecs/faculty/"
OUTPUT_PATH = Path("data/york_eecs_faculty.json")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _parse_directory(soup: BeautifulSoup) -> list[FacultyEntry]:
    """Parse the directory listing page into a list of FacultyEntry stubs.

    Each faculty block looks like:
      <h2><a href="/users/aan/">Aijun An</a></h2>
      <h3>Professor</h3>
      <a href="mailto:aan@yorku.ca">aan@yorku.ca</a>
    """
    entries: list[FacultyEntry] = []
    content = soup.find("main") or soup.find("article") or soup.body

    for h2 in content.find_all("h2"):
        anchor = h2.find("a", href=re.compile(r"^https://lassonde\.yorku\.ca/users/|^/users/"))
        if not anchor:
            continue

        name = clean_text(anchor.get_text(" ", strip=True))
        if not name:
            continue

        href = anchor["href"]
        profile_url = href if href.startswith("http") else f"https://lassonde.yorku.ca{href}"

        # Title is in the next <h3> sibling
        title: str | None = None
        title_tag = h2.find_next_sibling("h3")
        if title_tag:
            title = clean_text(title_tag.get_text(" ", strip=True)) or None

        # Email is in the next mailto anchor
        email: str | None = None
        email_anchor = h2.find_next_sibling("a", href=re.compile(r"^mailto:"))
        if email_anchor:
            email = email_anchor["href"].replace("mailto:", "").strip()

        entries.append(
            FacultyEntry(
                name=name,
                title=title,
                email=email,
                profile_url=profile_url,
                research_areas=[],
                research_interests=[],
                section="Faculty",
            )
        )

    return entries


def _enrich_from_profile(entry: FacultyEntry, timeout: int = 20) -> FacultyEntry:
    """Fetch a York profile page and extract Research Interests bullet points.

    Profile page structure:
      <h2>Research Interests</h2>
      <ul>
        <li>Data mining and machine learning</li>
        ...
      </ul>
    """
    if not entry.profile_url:
        return entry

    try:
        html = fetch_html(entry.profile_url, timeout=timeout)
    except Exception:
        return entry

    soup = BeautifulSoup(html, "html.parser")

    # Find the Research Interests heading
    for heading in soup.find_all(["h2", "h3", "h4"]):
        heading_text = clean_text(heading.get_text()).lower()
        if "research interest" not in heading_text and "research area" not in heading_text:
            continue

        # Grab the next <ul> or <ol> after the heading
        ul = heading.find_next_sibling(["ul", "ol"])
        if not ul:
            # Sometimes the list is wrapped in a div after the heading
            next_el = heading.find_next_sibling()
            if next_el:
                ul = next_el.find(["ul", "ol"])

        if ul:
            interests = [
                clean_text(li.get_text(" ", strip=True))
                for li in ul.find_all("li")
                if clean_text(li.get_text(" ", strip=True))
            ]
            if interests:
                entry.research_interests = interests
                break

    # Also grab email if missing
    if not entry.email:
        page_text = soup.get_text()
        m = EMAIL_RE.search(page_text)
        if m:
            entry.email = m.group(0)

    return entry


def scrape(input_html: str | None = None, enrich_profiles: bool = True) -> dict:
    soup = BeautifulSoup(
        load_directory_html(input_html, DIRECTORY_URL), "html.parser"
    )

    faculty_entries = _parse_directory(soup)

    if enrich_profiles:
        total = len(faculty_entries)
        for idx, entry in enumerate(faculty_entries, start=1):
            faculty_entries[idx - 1] = _enrich_from_profile(entry)
            if idx % 10 == 0:
                print(f"Enriched {idx}/{total} profiles...")

    return {
        "institution": "York University",
        "department": "Electrical Engineering and Computer Science",
        "directory_url": DIRECTORY_URL,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "faculty": [asdict(entry) for entry in faculty_entries],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-html", default=None)
    parser.add_argument("--skip-profile-enrich", action="store_true")
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