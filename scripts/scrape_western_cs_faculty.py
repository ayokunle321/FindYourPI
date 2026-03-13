"""
Scraper for Western University CS faculty.
URL: https://www.csd.uwo.ca/people/faculty/index.html

Structure: flat list of faculty blocks. Each block starts with an <h2> (name),
followed by a <p> containing title, research interests (after bold label),
office/phone, email anchor, and optional bio/external links.

Research interests are comma/semicolon-separated text after the bold label
"Research Interests / Specializations:" — no profile fetching needed.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

DIRECTORY_URL = "https://www.csd.uwo.ca/people/faculty/index.html"
BASE_URL = "https://www.csd.uwo.ca"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "western_cs_faculty.json"

RESEARCH_LABEL_RE = re.compile(r"Research Interests?\s*/\s*Specializations?\s*:", re.I)
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def fetch_html(url: str) -> BeautifulSoup:
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_research(p_tag: Tag) -> list[str]:
    """
    Find the bold 'Research Interests / Specializations:' label in a <p>,
    then collect all text that follows it (text siblings + remaining bold text).
    Split on commas and semicolons.
    """
    text_after = []
    found = False
    for child in p_tag.descendants:
        if hasattr(child, "get_text"):
            text = child.get_text(" ", strip=True)
            if not found and RESEARCH_LABEL_RE.search(text):
                # grab the part after the colon
                after = RESEARCH_LABEL_RE.split(text, maxsplit=1)[-1].strip()
                if after:
                    text_after.append(after)
                found = True
        elif found and isinstance(child, str):
            stripped = child.strip()
            if stripped:
                text_after.append(stripped)

    raw = " ".join(text_after)
    tags = [t.strip() for t in re.split(r"[,;]", raw) if t.strip()]
    return tags


def parse_faculty_blocks(soup: BeautifulSoup) -> list[dict]:
    """
    Each faculty member starts with an <h2> inside the main content area.
    The block content lives between that <h2> and the next <h2> (or end of content).
    """
    content = soup.find("div", class_="col-md-9") or soup.find("main") or soup.body

    faculty = []
    h2_tags = content.find_all("h2")

    for h2 in h2_tags:
        name = h2.get_text(" ", strip=True)
        if not name or len(name) < 3:
            continue
        # skip section headings like "People"
        if name.lower() in {"people", "full-time faculty"}:
            continue

        # collect siblings until next h2
        siblings = []
        for sib in h2.next_siblings:
            if isinstance(sib, Tag) and sib.name == "h2":
                break
            siblings.append(sib)

        title = None
        research_areas = []
        email = None
        profile_url = None
        bio_url = None

        for sib in siblings:
            if not isinstance(sib, Tag):
                continue

            if sib.name == "p":
                text = sib.get_text(" ", strip=True)

                # title: first <p> that doesn't contain email or research label
                if title is None and not RESEARCH_LABEL_RE.search(text) and "@" not in text:
                    # title is usually first line before any bolded research label
                    # grab just the first sentence / line
                    first_line = text.split("\n")[0].strip()
                    if first_line and len(first_line) < 120:
                        title = first_line

                # research
                if RESEARCH_LABEL_RE.search(text):
                    research_areas = parse_research(sib)
                    # also grab title if it precedes research label in same <p>
                    before_label = RESEARCH_LABEL_RE.split(text)[0].strip()
                    if title is None and before_label and len(before_label) < 120:
                        title = before_label.rstrip(",").strip()

                # email
                email_anchor = sib.find("a", href=lambda h: h and h.startswith("mailto:"))
                if email_anchor and email is None:
                    email = email_anchor["href"].replace("mailto:", "").strip()

                # profile / bio links
                for a in sib.find_all("a", href=True):
                    href = a["href"]
                    link_text = a.get_text(strip=True).lower()
                    if "biography" in link_text or "bios/" in href:
                        if not href.startswith("http"):
                            href = BASE_URL + "/people/faculty/" + href.lstrip("./")
                        bio_url = href
                    elif "external" in link_text or link_text == "external link":
                        profile_url = href

        # prefer external link as profile_url, fall back to bio
        if profile_url is None:
            profile_url = bio_url

        if name:
            faculty.append(
                {
                    "name": name,
                    "title": title,
                    "email": email,
                    "profile_url": profile_url,
                    "research_areas": research_areas,
                    "research_interests": [],
                    "section": "Full-Time Faculty",
                }
            )

    return faculty


def main():
    print(f"Fetching {DIRECTORY_URL} ...")
    soup = fetch_html(DIRECTORY_URL)
    faculty = parse_faculty_blocks(soup)

    print(f"Parsed {len(faculty)} faculty members.")
    for f in faculty:
        tag_count = len(f["research_areas"])
        print(f"  {f['name']:<35} {tag_count} tags   {f['email'] or '(no email)'}")

    payload = {
        "institution": "Western University",
        "department": "Computer Science",
        "directory_url": DIRECTORY_URL,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "faculty": faculty,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(faculty)} entries to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()