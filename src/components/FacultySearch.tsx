"use client";

import { useMemo, useState } from "react";

export type FacultyMember = {
  name: string;
  title: string | null;
  email: string | null;
  profile_url: string | null;
  research_areas: string[];
  research_interests: string[];
  section: string | null;
};

const MAX_RESULTS = 12;
const MAX_RESEARCH_TAGS = 5;
const PERSON_BLOB_RE =
  /\b[A-Z][A-Za-z'’. -]+(?:\s+[A-Z][A-Za-z'’. -]+){1,3}\s+(?:Adjunct|Assistant|Associate|Consultant|Distinguished|Professor|Lecturer|Engineer|Scientist|Director|Faculty)\b.*/;
const INVALID_TOPIC_RE =
  /\b(?:Department of|Innovation Lab|co-founder|Distinguished Executive in Residence)\b/i;

function normalize(value: string) {
  return value.toLowerCase();
}

function cleanResearchTag(value: string) {
  let cleaned = value.replace(/\s+/g, " ").trim();
  if (!cleaned) {
    return "";
  }

  cleaned = cleaned.replace(PERSON_BLOB_RE, "").trim();
  cleaned = cleaned
    .replace(/^Research Areas?:\s*/i, "")
    .replace(/^Research Interests?:\s*/i, "")
    .trim();

  if (!cleaned || INVALID_TOPIC_RE.test(cleaned)) {
    return "";
  }

  return cleaned;
}

function getResearchTags(member: FacultyMember) {
  const unique = new Set<string>();
  const ordered = [...member.research_areas, ...member.research_interests];

  ordered.forEach((value) => {
    const cleanedSource = value.replace(/\s+/g, " ").trim();
    if (!cleanedSource || INVALID_TOPIC_RE.test(cleanedSource)) {
      return;
    }

    const withoutPeople = cleanedSource.replace(PERSON_BLOB_RE, "").trim();
    const segments = withoutPeople
      .split(/Research Areas?:|Research Interests?:/i)
      .map((segment) => cleanResearchTag(segment));

    segments.forEach((segment) => {
      if (segment) {
        unique.add(segment);
      }
    });
  });

  return Array.from(unique).slice(0, MAX_RESEARCH_TAGS);
}

export default function FacultySearch({
  faculty,
  institution,
}: {
  faculty: FacultyMember[];
  institution: string | null;
}) {
  const [query, setQuery] = useState("");
  const [section, setSection] = useState("all");

  const sections = useMemo(() => {
    const unique = new Set<string>();
    faculty.forEach((member) => {
      if (member.section) {
        unique.add(member.section);
      }
    });
    return ["all", ...Array.from(unique).sort()];
  }, [faculty]);

  const filtered = useMemo(() => {
    const q = normalize(query.trim());
    return faculty.filter((member) => {
      if (section !== "all" && member.section !== section) {
        return false;
      }
      if (!q) {
        return true;
      }
      const haystack = normalize(
        [
          member.name,
          member.title ?? "",
          member.section ?? "",
          member.research_areas.join(" "),
          member.research_interests.join(" "),
        ].join(" ")
      );
      return haystack.includes(q);
    });
  }, [faculty, query, section]);

  const visible = filtered.slice(0, MAX_RESULTS);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
            Live preview
          </p>
          <h2 className="text-2xl font-semibold text-slate-900">
            Search real UofT faculty data.
          </h2>
        </div>
        <div className="text-xs font-semibold text-slate-500">
          Showing {visible.length} of {filtered.length}
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="flex-1">
          <span className="sr-only">Search faculty</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder='Try "compilers", "HCI", or a name'
            className="w-full rounded-full border border-slate-200 bg-white px-5 py-3 text-sm text-slate-700 shadow-sm outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
          />
        </label>
        <label>
          <span className="sr-only">Filter by section</span>
          <select
            value={section}
            onChange={(event) => setSection(event.target.value)}
            className="w-full rounded-full border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
          >
            {sections.map((value) => (
              <option key={value} value={value}>
                {value === "all" ? "All sections" : value}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {visible.map((member) => {
          const researchTags = getResearchTags(member);

          return (
            <div
              key={member.name}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">
                    Faculty
                  </p>
                  <h3 className="mt-2 text-lg font-semibold text-slate-900">
                    {member.name}
                  </h3>
                  {member.title ? (
                    <p className="mt-1 text-sm text-slate-600">{member.title}</p>
                  ) : null}
                </div>
                {institution ? (
                  <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-500">
                    {institution}
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
    </div>
  );
}
