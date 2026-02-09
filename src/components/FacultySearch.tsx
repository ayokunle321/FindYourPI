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

function normalize(value: string) {
  return value.toLowerCase();
}

export default function FacultySearch({
  faculty,
}: {
  faculty: FacultyMember[];
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
        {visible.map((member) => (
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
              {member.section ? (
                <span className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-500">
                  {member.section}
                </span>
              ) : null}
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {member.research_areas.slice(0, 4).map((area) => (
                <span
                  key={area}
                  className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700"
                >
                  {area}
                </span>
              ))}
              {member.research_areas.length === 0 ? (
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
        ))}
      </div>
    </div>
  );
}
