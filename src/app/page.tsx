import path from "path";
import { readFile } from "fs/promises";
import FacultySearch, { FacultyMember } from "@/components/FacultySearch";

type FacultyPayload = {
  institution?: string;
  faculty: FacultyMember[];
};

const DATA_FILES = [
  "uoft_cs_faculty.json",
  "ubc_cs_faculty.json",
  "mcgill_cs_faculty.json",
];

async function getFacultyData(): Promise<FacultyMember[]> {
  const results = await Promise.allSettled(
    DATA_FILES.map(async (filename) => {
      const filePath = path.join(process.cwd(), "data", filename);
      const raw = await readFile(filePath, "utf-8");
      const parsed = JSON.parse(raw) as FacultyPayload;
      const institution = parsed.institution ?? null;
      return (parsed.faculty ?? []).map((member) => ({
        ...member,
        institution: member.institution ?? institution,
      }));
    })
  );
  return results.flatMap((result) =>
    result.status === "fulfilled" ? result.value : []
  );
}

export default async function Home() {
  const faculty = await getFacultyData();
  const totalProfs = faculty.length;
  const totalInstitutions = new Set(
    faculty.map((f) => f.institution).filter(Boolean)
  ).size;

  return (
    <main className="min-h-screen bg-[#F5F4F0] text-[#0D0D0D]">

      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-8 py-5 bg-[#F5F4F0]/80 backdrop-blur-md border-b border-black/5">
        <span className="text-sm font-semibold tracking-tight">FindYourPI</span>
        <span className="text-xs text-[#0D0D0D]/40 font-medium tracking-widest uppercase">
          Graduate Research Discovery
        </span>
      </nav>

      {/* Hero — full viewport, type-first */}
      <section className="min-h-screen flex flex-col justify-end px-8 pb-20 pt-32 max-w-7xl mx-auto">
        <div className="space-y-8">
          <p className="text-xs font-semibold tracking-[0.3em] text-[#0D0D0D]/35 uppercase">
            {totalProfs.toLocaleString()} professors &middot; {totalInstitutions} universities
          </p>

          <h1 className="text-[clamp(3.5rem,11vw,10rem)] font-semibold leading-[0.92] tracking-[-0.04em]">
            Find your<br />
            <span className="text-[#0D0D0D]/18">next</span> PI.
          </h1>

          <p className="max-w-md text-lg leading-relaxed text-[#0D0D0D]/50 font-normal">
            Stop crawling through a dozen faculty pages.
            Search every professor, every research area, every university — in one place.
          </p>

          <a
            href="#search"
            className="inline-flex items-center gap-3 bg-[#0D0D0D] text-[#F5F4F0] px-7 py-3.5 rounded-full text-sm font-semibold hover:bg-[#0D0D0D]/80 transition-colors duration-200"
          >
            Start searching
            <span className="opacity-60">↓</span>
          </a>
        </div>

        {/* Stat strip anchored to bottom of hero */}
        <div className="mt-24 pt-8 border-t border-black/10 grid grid-cols-3 gap-8 max-w-sm">
          {[
            { value: totalProfs.toLocaleString(), label: "Faculty profiles" },
            { value: String(totalInstitutions), label: "Universities" },
            { value: "Free", label: "Always" },
          ].map((stat) => (
            <div key={stat.label}>
              <p className="text-2xl font-semibold tracking-tight">{stat.value}</p>
              <p className="text-xs text-[#0D0D0D]/40 mt-1">{stat.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="px-8 py-24 max-w-7xl mx-auto border-t border-black/10">
        <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-16 items-start">
          <div>
            <p className="text-xs font-semibold tracking-[0.3em] text-[#0D0D0D]/35 uppercase mb-4">
              How it works
            </p>
            <h2 className="text-3xl font-semibold tracking-tight leading-tight">
              Three steps.<br />One less headache.
            </h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-10">
            {[
              {
                num: "01",
                title: "Search by keyword",
                body: "Type a research area, method, or topic. Results update instantly.",
              },
              {
                num: "02",
                title: "Filter by university",
                body: "Narrow by institution. Compare supervisors side by side.",
              },
              {
                num: "03",
                title: "Reach out",
                body: "Click through to their profile. Their email is right there.",
              },
            ].map((step) => (
              <div key={step.num} className="space-y-3">
                <p className="text-xs font-mono text-[#0D0D0D]/20 font-semibold tracking-widest">
                  {step.num}
                </p>
                <h3 className="text-sm font-semibold">{step.title}</h3>
                <p className="text-sm text-[#0D0D0D]/45 leading-relaxed">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Search */}
      <section
        id="search"
        className="px-8 py-24 max-w-7xl mx-auto border-t border-black/10"
      >
        <div className="mb-12">
          <p className="text-xs font-semibold tracking-[0.3em] text-[#0D0D0D]/35 uppercase mb-3">
            Directory
          </p>
          <h2 className="text-3xl font-semibold tracking-tight">
            Search faculty
          </h2>
        </div>
        <FacultySearch faculty={faculty} />
      </section>

      {/* Footer */}
      <footer className="border-t border-black/10 px-8 py-10 max-w-7xl mx-auto flex items-center justify-between">
        <span className="text-sm font-semibold">FindYourPI</span>
        <span className="text-xs text-[#0D0D0D]/35">
          Built for grad school applicants everywhere.
        </span>
      </footer>

    </main>
  );
}
