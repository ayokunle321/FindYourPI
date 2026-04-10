#!/usr/bin/env python3
"""
Backfill research_tags for existing JSON data using Groq (llama-3.1-8b-instant).

Useful for enriching already-scraped data without re-running a full scrape.
For new scrapes, enrichment is built into each scraper automatically.

Usage:
    # dry run — count candidates, no API calls, no writes
    python3 scripts/enrich_tags.py --dry-run

    # enrich all data files
    GROQ_API_KEY=gsk_... python3 scripts/enrich_tags.py

    # enrich a single file only
    GROQ_API_KEY=gsk_... python3 scripts/enrich_tags.py --file ubc_cs_faculty.json

    # re-enrich even if research_tags already exists
    GROQ_API_KEY=gsk_... python3 scripts/enrich_tags.py --force
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_FILES = [
    "uoft_cs_faculty.json",
    "ubc_cs_faculty.json",
    "mcgill_cs_faculty.json",
    "york_eecs_faculty.json",
    "western_cs_faculty.json",
]

# A single raw tag longer than this is almost certainly nav/boilerplate
GARBLED_THRESHOLD = 300


def needs_enrichment(member: dict, force: bool = False) -> bool:
    if not force and member.get("research_tags"):
        return False
    areas = member.get("research_areas", [])
    interests = member.get("research_interests", [])
    combined = areas + interests
    if not combined:
        return True
    if any(len(t) > GARBLED_THRESHOLD for t in combined):
        return True
    return False


def enrich_file(client, filename: str, dry_run: bool, force: bool) -> int:
    from scraper_utils import FacultyEntry, enrich_with_llm

    filepath = DATA_DIR / filename
    if not filepath.exists():
        print(f"  Skipping — not found: {filepath}", file=sys.stderr)
        return 0

    data = json.loads(filepath.read_text(encoding="utf-8"))
    institution = data.get("institution")
    faculty = data.get("faculty", [])

    candidates = [m for m in faculty if needs_enrichment(m, force=force)]
    if not candidates:
        print(f"  Nothing to enrich")
        return 0

    enriched = 0
    for member in candidates:
        if dry_run:
            combined_len = sum(len(t) for t in member.get("research_areas", []) + member.get("research_interests", []))
            flag = "garbled" if any(len(t) > GARBLED_THRESHOLD for t in member.get("research_areas", []) + member.get("research_interests", [])) else "empty"
            print(f"  [dry-run] {member.get('name')} ({flag}, {combined_len} chars)")
            enriched += 1
            continue

        entry = FacultyEntry(
            name=member.get("name", ""),
            title=member.get("title"),
            email=member.get("email"),
            profile_url=member.get("profile_url"),
            research_areas=member.get("research_areas", []),
            research_interests=member.get("research_interests", []),
            section=member.get("section"),
        )
        entry = enrich_with_llm(entry, client, institution=institution)
        if entry.research_tags:
            member["research_tags"] = entry.research_tags
            enriched += 1
            print(f"  {member['name']} → {entry.research_tags}")

    if not dry_run and enriched > 0:
        filepath.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  Saved {filepath.name}")

    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill research_tags with Groq")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--file", help="e.g. ubc_cs_faculty.json")
    parser.add_argument("--force", action="store_true", help="Re-enrich existing tags")
    args = parser.parse_args()

    if args.dry_run:
        client = None
    else:
        from scraper_utils import get_groq_client
        client = get_groq_client()

    files = [args.file] if args.file else DATA_FILES
    total = 0

    for filename in files:
        print(f"\n{filename}")
        count = enrich_file(client, filename, dry_run=args.dry_run, force=args.force)
        total += count

    verb = "would be" if args.dry_run else ""
    print(f"\nDone — {total} faculty members {verb} enriched".strip())


if __name__ == "__main__":
    main()
