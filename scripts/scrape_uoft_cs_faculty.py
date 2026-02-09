#!/usr/bin/env python3
"""Scrape UofT CS faculty directory into a minimal JSON schema.

Usage:
  python3 scripts/scrape_uoft_cs_faculty.py

Outputs:
  data/uoft_cs_faculty.json
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

DIRECTORY_URL = "https://web.cs.toronto.edu/people/faculty-directory"
OUTPUT_PATH = Path("data/uoft_cs_faculty.json")

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
    return re.sub(r"\s+", " ", value).strip()


def _split_research(field_value: str) -> list[str]:
    if not field_value:
        return []
    cleaned = _clean_text(field_value)
    parts = re.split(r",|;|/|\band\b", cleaned, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def _iter_section_blocks(container: Tag) -> Iterator[tuple[str | None, Tag]]:
    """Yield (section_title, block_root) pairs under the main content.

    The page uses H2 headings like "Research Stream Faculty". We collect the
    content between each H2 into a wrapper div for parsing.
    """

    headings = container.find_all(["h2", "h3"])
    if not headings:
        yield None, container
        return

    for heading in headings:
        section_title = _clean_text(heading.get_text(" ", strip=True))
        block = Tag(name="div")
        for sibling in heading.next_siblings:
            if isinstance(sibling, Tag) and sibling.name in {"h2", "h3"}:
                break
            if isinstance(sibling, (Tag, NavigableString)):
                block.append(sibling)
        yield section_title, block


def _flatten_tokens(block: Tag) -> list[tuple[str, str | None]]:
    """Flatten a block into ordered tokens.

    Each token is (kind, value). kind is "link" or "text".
    """

    tokens: list[tuple[str, str | None]] = []
    for element in block.descendants:
        if isinstance(element, Tag) and element.name == "a":
            text = _clean_text(element.get_text(" ", strip=True))
            href = element.get("href")
            if text:
                tokens.append(("link", f"{text}|||{href}"))
        elif isinstance(element, NavigableString):
            text = _clean_text(str(element))
            if text:
                tokens.append(("text", text))
    return tokens


def _looks_like_name(value: str) -> bool:
    if len(value.split()) < 2:
        return False
    return all(part[0].isalpha() for part in value.split())


def _parse_entry_details(text_blob: str) -> tuple[str | None, str | None, list[str], list[str]]:
    """Parse title, email, research areas, interests from a text blob."""

    email_match = EMAIL_RE.search(text_blob)
    email = email_match.group(0) if email_match else None

    research_areas: list[str] = []
    research_interests: list[str] = []

    areas_match = re.search(r"Research Areas?:\s*(.+)", text_blob, flags=re.IGNORECASE)
    if areas_match:
        research_areas = _split_research(areas_match.group(1))

    interests_match = re.search(
        r"Research Interests?:\s*(.+)", text_blob, flags=re.IGNORECASE
    )
    if interests_match:
        research_interests = _split_research(interests_match.group(1))

    cleaned = text_blob
    if email:
        cleaned = cleaned.replace(email, " ")
    cleaned = re.sub(r"Research Areas?:.*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Research Interests?:.*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Room:.*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = _clean_text(cleaned)

    title = cleaned or None
    return title, email, research_areas, research_interests


def _extract_entries(block: Tag, section: str | None) -> Iterable[FacultyEntry]:
    tokens = _flatten_tokens(block)
    entries: list[FacultyEntry] = []

    index = 0
    while index < len(tokens):
        kind, value = tokens[index]
        if kind == "link" and value:
            name, href = value.split("|||", 1)
            if _looks_like_name(name):
                # Accumulate text until next link token.
                detail_parts: list[str] = []
                index += 1
                while index < len(tokens) and tokens[index][0] != "link":
                    detail_parts.append(tokens[index][1] or "")
                    index += 1
                detail_text = _clean_text(" ".join(detail_parts))
                title, email, research_areas, research_interests = _parse_entry_details(
                    detail_text
                )
                entries.append(
                    FacultyEntry(
                        name=name,
                        title=title,
                        email=email,
                        profile_url=href,
                        research_areas=research_areas,
                        research_interests=research_interests,
                        section=section,
                    )
                )
                continue
        index += 1
    return entries


def scrape() -> dict:
    response = requests.get(DIRECTORY_URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    main = soup.find("main") or soup.find("article") or soup.body
    if main is None:
        raise RuntimeError("Unable to locate main content on the page.")

    faculty_entries: list[FacultyEntry] = []
    for section_title, block in _iter_section_blocks(main):
        faculty_entries.extend(_extract_entries(block, section_title))

    payload = {
        "institution": "University of Toronto",
        "department": "Computer Science",
        "directory_url": DIRECTORY_URL,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "faculty": [asdict(entry) for entry in faculty_entries],
    }
    return payload


def main() -> None:
    payload = scrape()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {len(payload['faculty'])} entries")


if __name__ == "__main__":
    main()
