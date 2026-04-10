"""
Scraper for Western University CS faculty.
URL: https://www.csd.uwo.ca/people/faculty/index.html

Real structure (confirmed via devtools):
  div.teamgrid
    div.headshot   — photo (ignored)
    div.infoleft   — h2 (name), bare text node (title), <br>, <strong> research label, research text
    div.inforight  — bare text (office/phone), <a mailto> (email), <a bio/external> (links)

No profile fetching needed — all data is on the directory page.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from scraper_utils import enrich_with_llm, get_groq_client

DIRECTORY_URL = "https://www.csd.uwo.ca/people/faculty/index.html"
BASE_URL = "https://www.csd.uwo.ca/people/faculty/"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "western_cs_faculty.json"

RESEARCH_LABEL_RE = re.compile(r"Research Interests?\s*/\s*Specializations?\s*:", re.I)


def fetch_html(url: str) -> BeautifulSoup:
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_infoleft(div: Tag) -> tuple:
    """Returns (name, title, research_areas) from div.infoleft."""
    name = None
    title = None
    research_areas = []

    h2 = div.find("h2")
    if h2:
        name = h2.get_text(" ", strip=True)

    found_research = False
    research_text_parts = []

    for child in div.children:
        if isinstance(child, Tag) and child.name == "h2":
            continue

        if isinstance(child, Tag) and child.name == "strong":
            if RESEARCH_LABEL_RE.search(child.get_text(" ", strip=True)):
                found_research = True
            continue

        if found_research:
            if isinstance(child, NavigableString):
                t = child.strip()
                if t:
                    research_text_parts.append(t)
            elif isinstance(child, Tag) and child.name != "br":
                t = child.get_text(" ", strip=True)
                if t:
                    research_text_parts.append(t)
            continue

        if title is None:
            if isinstance(child, NavigableString):
                t = child.strip()
                if t:
                    title = t
            elif isinstance(child, Tag) and child.name not in {"br", "strong"}:
                t = child.get_text(" ", strip=True)
                if t and len(t) < 120:
                    title = t

    if research_text_parts:
        raw = " ".join(research_text_parts)
        research_areas = [t.strip() for t in re.split(r"[,;]", raw) if t.strip()]

    return name, title, research_areas


def parse_inforight(div: Tag) -> tuple:
    """Returns (email, profile_url) from div.inforight."""
    email = None
    profile_url = None
    bio_url = None

    for a in div.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if href.startswith("mailto:"):
            email = href.replace("mailto:", "").strip()
        elif "biography" in text or "bios/" in href:
            if not href.startswith("http"):
                href = BASE_URL + href.lstrip("./")
            bio_url = href
        elif "external" in text:
            profile_url = href

    return email, profile_url or bio_url


def parse_faculty(soup: BeautifulSoup) -> list:
    faculty = []

    for card in soup.find_all("div", class_="teamgrid"):
        infoleft = card.find("div", class_="infoleft")
        inforight = card.find("div", class_="inforight")

        if not infoleft:
            continue

        name, title, research_areas = parse_infoleft(infoleft)
        email, profile_url = parse_inforight(inforight) if inforight else (None, None)

        if not name:
            continue

        faculty.append({
            "name": name,
            "title": title,
            "email": email,
            "profile_url": profile_url,
            "research_areas": research_areas,
            "research_interests": [],
            "section": "Full-Time Faculty",
        })

    return faculty


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-llm-enrich", action="store_true",
                        help="Skip Groq LLM tag extraction (no GROQ_API_KEY needed)")
    args = parser.parse_args()

    print(f"Fetching {DIRECTORY_URL} ...")
    soup = fetch_html(DIRECTORY_URL)
    faculty_dicts = parse_faculty(soup)
    print(f"Parsed {len(faculty_dicts)} faculty members.")

    if not args.skip_llm_enrich:
        from scraper_utils import FacultyEntry
        client = get_groq_client()
        enriched = []
        for idx, f in enumerate(faculty_dicts, start=1):
            entry = FacultyEntry(
                name=f["name"],
                title=f.get("title"),
                email=f.get("email"),
                profile_url=f.get("profile_url"),
                research_areas=f.get("research_areas", []),
                research_interests=f.get("research_interests", []),
                section=f.get("section"),
            )
            print(f"  [{idx}/{len(faculty_dicts)}] {entry.name}")
            entry = enrich_with_llm(entry, client, institution="Western University")
            d = f.copy()
            d["research_tags"] = entry.research_tags
            enriched.append(d)
        faculty_dicts = enriched

    for f in faculty_dicts:
        print(f"  {f['name']:<35} {len(f.get('research_tags') or f.get('research_areas', []))} tags   {f['email'] or '(no email)'}")

    payload = {
        "institution": "Western University",
        "department": "Computer Science",
        "directory_url": DIRECTORY_URL,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "faculty": faculty_dicts,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(faculty_dicts)} entries to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()