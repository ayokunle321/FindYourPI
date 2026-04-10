"""Shared utilities for FindYourPI faculty scrapers.

Every school scraper imports from here. School-specific logic (how to find
faculty candidates on a directory page) lives in each scraper. Everything
else — data types, text cleaning, HTTP fetching, LLM enrichment — lives here.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

try:
    from groq import Groq
    _groq_available = True
except ImportError:
    _groq_available = False

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LLM_MODEL = "llama-3.1-8b-instant"


@dataclass
class FacultyEntry:
    name: str
    title: str | None
    email: str | None
    profile_url: str | None
    research_areas: list[str] = field(default_factory=list)
    research_interests: list[str] = field(default_factory=list)
    research_tags: list[str] = field(default_factory=list)
    section: str | None = None


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def split_research(field_value: str) -> list[str]:
    """Split a comma/semicolon/pipe-delimited research string into clean items."""
    if not field_value:
        return []
    cleaned = clean_text(field_value)
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


def looks_like_name(value: str) -> bool:
    text = clean_text(value)
    parts = text.split()
    if len(parts) < 2 or len(parts) > 5:
        return False
    return all(part[0].isalpha() for part in parts if part)


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def fetch_html(url: str, timeout: int = 30) -> str:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "FindYourPI/1.0"})
    resp.raise_for_status()
    return resp.text


def load_directory_html(input_html: str | None, directory_url: str) -> str:
    from pathlib import Path
    if input_html:
        html_path = Path(input_html)
        if not html_path.exists():
            raise FileNotFoundError(
                f"Input HTML not found: {html_path}. "
                "Pass a valid file path, or omit --input-html for live scraping."
            )
        return html_path.read_text(encoding="utf-8")
    return fetch_html(directory_url)


# ---------------------------------------------------------------------------
# Field extraction — generic regex over page text (legacy fallback)
# ---------------------------------------------------------------------------

def extract_labeled_fields(text_blob: str) -> tuple[str | None, list[str], list[str]]:
    """Extract title, research_areas, research_interests from a block of text.

    Works on both flat directory text and full profile page text.
    Returns (title, areas, interests) — any of which may be empty.
    """
    normalized = clean_text(text_blob)

    title: str | None = None
    title_match = re.search(
        r"(?:Position|Title|Rank)\s*:?\s*(.+?)(?=(?:Email|Research|Interests?)\s*:|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if title_match:
        title = clean_text(title_match.group(1))

    research_areas: list[str] = []
    areas_match = re.search(
        r"Research Areas?\s*:?\s*(.+?)(?=(?:Research Interests?|Email)\s*:|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if areas_match:
        research_areas = split_research(areas_match.group(1))

    research_interests: list[str] = []
    interests_match = re.search(
        r"Research Interests?\s*:?\s*(.+?)(?=(?:Research Areas?|Email)\s*:|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if interests_match:
        research_interests = split_research(interests_match.group(1))

    return title, research_areas, research_interests


# ---------------------------------------------------------------------------
# LLM enrichment via Groq
# ---------------------------------------------------------------------------

def get_groq_client() -> "Groq":
    if not _groq_available:
        raise RuntimeError("groq package not installed — run: pip install groq")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set")
    return Groq(api_key=api_key)


def extract_main_text(html: str, max_chars: int = 4000) -> str:
    """Strip nav/header/footer/sidebar noise and return clean body text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style", "noscript",
                     "aside", "menu"]):
        tag.decompose()
    # Also kill elements with class/id names that scream "navigation"
    for tag in soup.find_all(True, {"class": re.compile(r"nav|menu|sidebar|breadcrumb", re.I)}):
        tag.decompose()
    for tag in soup.find_all(True, {"id": re.compile(r"nav|menu|sidebar|breadcrumb", re.I)}):
        tag.decompose()
    text = clean_text(soup.get_text(" ", strip=True))
    return text[:max_chars]


def llm_tags_from_text(
    client: "Groq",
    page_text: str,
    name: str,
    title: str | None,
    institution: str | None,
    raw_tags: list[str] | None = None,
) -> list[str]:
    """Call Groq Llama to extract exactly 5 research tags.

    Builds context from page text + any raw scraped tags already available.
    Retries once on empty response before raising.
    """
    # Build the best possible context from what we have
    context_parts: list[str] = []
    if page_text and page_text != "(no page available)":
        context_parts.append(f"Page text:\n{page_text}")
    if raw_tags:
        context_parts.append(f"Known research areas: {', '.join(raw_tags)}")
    if not context_parts:
        context_parts.append("(no page or research data available — infer from name and title)")

    context = "\n\n".join(context_parts)

    prompt = (
        f"Professor profile:\n"
        f"Name: {name}\n"
        f"Title: {title or 'Unknown'}\n"
        f"Institution: {institution or 'Unknown'}\n\n"
        f"{context}\n\n"
        f"Return exactly 5 short, specific research area tags (2–5 words each) "
        f"that best describe this professor's research focus.\n"
        f"Use lowercase only. No duplicates.\n"
        f"Return ONLY a JSON array of exactly 5 strings, no other text.\n"
        f'Example: ["machine learning", "computer vision", "robotics", "neural networks", "autonomous systems"]'
    )

    def _call() -> list[str]:
        response = client.chat.completions.create(
            model=_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.1,
        )
        raw = (response.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()
        if not raw:
            raise ValueError("empty response from model")
        tags = json.loads(raw)
        if not isinstance(tags, list):
            raise ValueError(f"expected list, got {type(tags)}: {raw}")
        return [str(t).lower() for t in tags[:5]]

    try:
        return _call()
    except Exception:
        import time
        time.sleep(1.5)
        return _call()  # one retry


def enrich_with_llm(
    entry: FacultyEntry,
    client: "Groq",
    institution: str | None = None,
    timeout: int = 20,
) -> FacultyEntry:
    """Fetch a prof's profile page, strip noise, then ask Groq for 5 clean tags.

    Passes existing scraped research areas as fallback context so the LLM
    always has something to work with even when there is no profile page.
    Also opportunistically grabs email from the page if missing.
    Never raises — logs and returns entry unchanged on any failure.
    """
    page_text = "(no page available)"

    if entry.profile_url:
        try:
            html = fetch_html(entry.profile_url, timeout=timeout)

            # Grab email from raw page before we strip anything
            if not entry.email:
                email_match = EMAIL_RE.search(html)
                if email_match:
                    entry.email = email_match.group(0)

            page_text = extract_main_text(html)
        except Exception as exc:
            print(f"    [warn] Could not fetch {entry.profile_url}: {exc}")

    raw_tags = (entry.research_areas + entry.research_interests) or None

    try:
        tags = llm_tags_from_text(
            client, page_text, entry.name, entry.title, institution,
            raw_tags=raw_tags,
        )
        entry.research_tags = tags
    except Exception as exc:
        print(f"    [warn] LLM failed for {entry.name}: {exc}")

    return entry


# ---------------------------------------------------------------------------
# Legacy profile enrichment — regex-based (kept as fallback)
# ---------------------------------------------------------------------------

def enrich_from_profile(entry: FacultyEntry, timeout: int = 20) -> FacultyEntry:
    """Fetch a professor's profile page and fill any missing fields in-place.

    Kept for backwards compatibility. Prefer enrich_with_llm for new scrapers.
    """
    if not entry.profile_url:
        return entry

    try:
        html = fetch_html(entry.profile_url, timeout=timeout)
    except Exception:
        return entry

    soup = BeautifulSoup(html, "html.parser")
    page_text = clean_text(soup.get_text(" ", strip=True))

    if not entry.email:
        email_match = EMAIL_RE.search(page_text)
        if email_match:
            entry.email = email_match.group(0)

    title, areas, interests = extract_labeled_fields(page_text)
    if title and not entry.title:
        entry.title = title
    if areas:
        entry.research_areas = areas
    if interests:
        entry.research_interests = interests

    if not entry.research_areas and not entry.research_interests:
        _enrich_from_headings(soup, entry)

    return entry


def _enrich_from_headings(soup: BeautifulSoup, entry: FacultyEntry) -> None:
    for h in soup.find_all(["h2", "h3", "h4", "strong", "b"]):
        heading_text = clean_text(h.get_text(" ", strip=True)).lower()
        if "research" not in heading_text and "interest" not in heading_text:
            continue
        parent = h.parent if isinstance(h.parent, Tag) else None
        if not parent:
            continue
        context_text = clean_text(parent.get_text(" ", strip=True))
        _, fallback_areas, fallback_interests = extract_labeled_fields(context_text)
        if fallback_areas:
            entry.research_areas = fallback_areas
        if fallback_interests:
            entry.research_interests = fallback_interests
        if entry.research_areas or entry.research_interests:
            break


# ---------------------------------------------------------------------------
# Convenience: build candidates dict from any anchor list
# ---------------------------------------------------------------------------

def extract_candidates_from_anchors(
    soup: BeautifulSoup,
    base_url: str,
    default_section: str = "Faculty",
) -> dict[str, FacultyEntry]:
    candidates: dict[str, FacultyEntry] = {}
    for anchor in soup.find_all("a", href=True):
        name = clean_text(anchor.get_text(" ", strip=True))
        href = anchor["href"].strip()
        if not looks_like_name(name):
            continue
        if not href or href.startswith("#"):
            continue
        profile_url = urljoin(base_url, href)
        key = name.lower()
        if key in candidates:
            continue
        candidates[key] = FacultyEntry(
            name=name,
            title=None,
            email=None,
            profile_url=profile_url,
            section=default_section,
        )
    return candidates
