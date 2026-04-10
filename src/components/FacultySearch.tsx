"use client";

import { useMemo, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";

export type FacultyMember = {
  name: string;
  title: string | null;
  email: string | null;
  profile_url: string | null;
  research_areas: string[];
  research_interests: string[];
  research_tags?: string[];
  section: string | null;
  institution: string | null;
};

const PAGE_SIZE = 24;
const MAX_RESEARCH_TAGS = 5;
type SortOption = "relevance" | "name" | "institution";

const PERSON_BLOB_RE =
  /\b[A-Z][A-Za-z''. -]+(?:\s+[A-Z][A-Za-z''. -]+){1,3}\s+(?:Adjunct|Assistant|Associate|Consultant|Distinguished|Professor|Lecturer|Engineer|Scientist|Director|Faculty)\b.*/;
const INVALID_TOPIC_RE =
  /\b(?:Department of|Innovation Lab|co-founder|Distinguished Executive in Residence)\b/i;

function normalize(value: string) {
  return value.toLowerCase();
}

function cleanResearchTag(value: string) {
  let cleaned = value.replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  cleaned = cleaned.replace(PERSON_BLOB_RE, "").trim();
  cleaned = cleaned
    .replace(/^Research Areas?:\s*/i, "")
    .replace(/^Research Interests?:\s*/i, "")
    .trim();
  if (!cleaned || INVALID_TOPIC_RE.test(cleaned)) return "";
  return cleaned;
}

function getResearchTags(member: FacultyMember) {
  // Prefer LLM-enriched tags — they're clean and consistently formatted
  if (member.research_tags && member.research_tags.length > 0) {
    return member.research_tags.slice(0, MAX_RESEARCH_TAGS);
  }

  // Fallback: regex-based extraction from raw scraped data
  const unique = new Set<string>();
  const ordered = [...member.research_areas, ...member.research_interests];
  ordered.forEach((value) => {
    const cleanedSource = value.replace(/\s+/g, " ").trim();
    if (!cleanedSource || INVALID_TOPIC_RE.test(cleanedSource)) return;
    const withoutPeople = cleanedSource.replace(PERSON_BLOB_RE, "").trim();
    const segments = withoutPeople
      .split(/Research Areas?:|Research Interests?:/i)
      .map((segment) => cleanResearchTag(segment));
    segments.forEach((segment) => {
      if (segment) unique.add(segment);
    });
  });
  return Array.from(unique).slice(0, MAX_RESEARCH_TAGS);
}

function scoreMatch(member: FacultyMember, q: string): number {
  let score = 0;
  if (normalize(member.name).includes(q)) score += 10;
  if ((member.research_tags ?? []).some((t) => normalize(t).includes(q))) score += 7;
  if (member.research_areas.some((a) => normalize(a).includes(q))) score += 6;
  if (member.research_interests.some((i) => normalize(i).includes(q))) score += 5;
  if (normalize(member.title ?? "").includes(q)) score += 2;
  if (normalize(member.institution ?? "").includes(q)) score += 1;
  return score;
}

export default function FacultySearch({ faculty }: { faculty: FacultyMember[] }) {
  const searchParams = useSearchParams();

  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [institutionFilter, setInstitutionFilter] = useState(
    searchParams.get("uni") ?? "all"
  );
  const sort: SortOption = (searchParams.get("sort") as SortOption) ?? "relevance";
  const [page, setPage] = useState(1);

  const updateURL = useCallback((q: string, uni: string, s: string) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (uni !== "all") params.set("uni", uni);
    if (s !== "relevance") params.set("sort", s);
    const qs = params.toString();
    window.history.replaceState(
      null,
      "",
      qs ? `?${qs}` : window.location.pathname
    );
  }, []);

  const handleQueryChange = (value: string) => {
    setQuery(value);
    setPage(1);
    updateURL(value, institutionFilter, sort);
  };

  const handleUniChange = (value: string) => {
    setInstitutionFilter(value);
    setPage(1);
    updateURL(query, value, sort);
  };

  const clearFilters = () => {
    setQuery("");
    setInstitutionFilter("all");
    setPage(1);
    updateURL("", "all", sort);
  };

  const institutions = useMemo(() => {
    const unique = new Set<string>();
    faculty.forEach((m) => {
      if (m.institution) unique.add(m.institution);
    });
    return ["all", ...Array.from(unique).sort()];
  }, [faculty]);

  const filtered = useMemo(() => {
    const q = normalize(query.trim());

    let results = faculty.filter((member) => {
      if (institutionFilter !== "all" && member.institution !== institutionFilter)
        return false;
      if (!q) return true;
      const haystack = normalize(
        [
          member.name,
          member.title ?? "",
          member.institution ?? "",
          member.research_areas.join(" "),
          member.research_interests.join(" "),
          (member.research_tags ?? []).join(" "),
        ].join(" ")
      );
      return haystack.includes(q);
    });

    if (sort === "name") {
      results = [...results].sort((a, b) => a.name.localeCompare(b.name));
    } else if (sort === "institution") {
      results = [...results].sort((a, b) =>
        (a.institution ?? "").localeCompare(b.institution ?? "")
      );
    } else if (q) {
      results = [...results].sort((a, b) => scoreMatch(b, q) - scoreMatch(a, q));
    }

    return results;
  }, [faculty, query, institutionFilter, sort]);

  const visible = filtered.slice(0, page * PAGE_SIZE);
  const hasMore = visible.length < filtered.length;
  const remaining = filtered.length - visible.length;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-2xl font-semibold text-slate-900">
          Search faculty across Canadian universities.
        </h2>
        <div className="shrink-0 text-xs font-semibold text-slate-500">
          {filtered.length === faculty.length
            ? `${faculty.length.toLocaleString()} faculty members`
            : `${filtered.length.toLocaleString()} of ${faculty.length.toLocaleString()} results`}
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="relative flex-1">
          <span className="sr-only">Search faculty</span>
          <input
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder='Try "compilers", "HCI", or a name'
            className="w-full rounded-full border border-slate-200 bg-white px-5 py-3 pr-10 text-sm text-slate-700 shadow-sm outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
          />
          {query && (
            <button
              onClick={() => handleQueryChange("")}
              aria-label="Clear search"
              className="absolute right-4 top-1/2 -translate-y-1/2 text-xl leading-none text-slate-400 transition hover:text-slate-600"
            >
              ×
            </button>
          )}
        </label>
        <label>
          <span className="sr-only">Filter by institution</span>
          <select
            value={institutionFilter}
            onChange={(e) => handleUniChange(e.target.value)}
            className="w-full rounded-full border border-slate-200 bg-white pl-4 pr-8 py-3 text-sm text-slate-700 shadow-sm outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
          >
            {institutions.map((v) => (
              <option key={v} value={v}>
                {v === "all" ? "All universities" : v}
              </option>
            ))}
          </select>
        </label>
      </div>

      {filtered.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-sm text-slate-500">
            No results for{" "}
            <strong className="text-slate-700">&ldquo;{query}&rdquo;</strong>
            {institutionFilter !== "all" ? ` at ${institutionFilter}` : ""}.
          </p>
          <button
            onClick={clearFilters}
            className="mt-3 text-xs font-semibold text-slate-500 underline underline-offset-2 transition hover:text-slate-700"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {visible.map((member) => {
              const researchTags = getResearchTags(member);
              return (
                <div
                  key={`${member.institution}-${member.name}`}
                  className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="text-lg font-semibold text-slate-900">
                        {member.name}
                      </h3>
                      {member.title ? (
                        <p className="mt-1 text-sm text-slate-600">
                          {member.title}
                        </p>
                      ) : null}
                    </div>
                    {member.institution ? (
                      <span className="whitespace-nowrap rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-500">
                        {member.institution}
                      </span>
                    ) : null}
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2">
                    {researchTags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700"
                      >
                        {tag}
                      </span>
                    ))}
                    {researchTags.length === 0 ? (
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">
                        Research areas pending
                      </span>
                    ) : null}
                  </div>

                  <div className="mt-4 flex items-center justify-between text-xs text-slate-500">
                    {member.email ? <span>{member.email}</span> : <span />}
                    {member.profile_url ? (
                      <a
                        href={member.profile_url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-semibold text-slate-700 transition hover:text-slate-900"
                      >
                        Profile →
                      </a>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>

          {hasMore && (
            <div className="flex justify-center pt-4">
              <button
                onClick={() => setPage((p) => p + 1)}
                className="rounded-full border border-slate-200 bg-white px-6 py-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
              >
                Load more · {remaining.toLocaleString()} remaining
              </button>
            </div>
          )}

          {!hasMore && filtered.length > PAGE_SIZE && (
            <p className="pt-2 text-center text-xs text-slate-400">
              All {filtered.length.toLocaleString()} results shown
            </p>
          )}
        </>
      )}
    </div>
  );
}
