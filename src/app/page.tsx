import path from "path";
import { readFile } from "fs/promises";
import FacultySearch, { FacultyMember } from "@/components/FacultySearch";

const steps = [
  {
    title: "Search by keyword",
    description:
      "Find professors by research area, method, or topic in seconds.",
  },
  {
    title: "Filter by institution",
    description:
      "Compare supervisors across universities without the busywork.",
  },
  {
    title: "Save and reach out",
    description:
      "Shortlist the best fits and move faster on real outreach.",
  },
];

const benefits = [
  "Stop digging through scattered faculty pages.",
  "Save hours per application cycle.",
  "Make stronger, better-aligned outreach.",
  "Build a list you can reuse and refine.",
];

type FacultyPayload = {
  institution?: string;
  faculty: FacultyMember[];
};

async function getFacultyData(): Promise<{
  faculty: FacultyMember[];
  institution: string | null;
}> {
  const filePath = path.join(process.cwd(), "data", "uoft_cs_faculty.json");
  const raw = await readFile(filePath, "utf-8");
  const parsed = JSON.parse(raw) as FacultyPayload;
  return {
    faculty: parsed.faculty ?? [],
    institution: parsed.institution ?? null,
  };
}

export default async function Home() {
  const { faculty, institution } = await getFacultyData();

  return (
    <main className="min-h-screen bg-white text-slate-900 [background-image:radial-gradient(1200px_circle_at_top,_rgba(15,23,42,0.08),_transparent_60%),radial-gradient(900px_circle_at_bottom,_rgba(15,23,42,0.05),_transparent_55%)]">
      <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 pb-20 pt-24 text-center">
        <section className="flex flex-1 flex-col items-center justify-center">
          <div className="space-y-6">
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
              Graduate research discovery
            </p>
            <h1 className="text-4xl font-semibold tracking-tight text-balance text-slate-900 sm:text-6xl">
              FindYourPI
            </h1>
            <p className="mx-auto max-w-2xl text-base leading-relaxed text-balance text-slate-600 sm:text-lg">
              A clean, centralized directory to help prospective graduate students
              find research supervisors by keyword, focus area, and institution.
            </p>
          </div>
        </section>

        <section className="mt-20 grid gap-10 text-left sm:grid-cols-3">
          {steps.map((step) => (
            <div key={step.title} className="space-y-3">
              <h2 className="text-lg font-semibold text-slate-900">
                {step.title}
              </h2>
              <p className="text-sm leading-relaxed text-slate-600">
                {step.description}
              </p>
            </div>
          ))}
        </section>

        <section className="mt-16 rounded-3xl border border-slate-200 bg-slate-50 px-6 py-10 text-left">
          <div className="grid gap-8 md:grid-cols-[1.2fr_1fr] md:items-center">
            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
                Why it matters
              </p>
              <h2 className="text-2xl font-semibold text-slate-900">
                Turn searching into signal, not noise.
              </h2>
              <p className="text-sm leading-relaxed text-slate-600">
                FindYourPI reduces the time you spend hunting across university
                sites so you can focus on fit, outreach, and real conversations.
              </p>
            </div>
            <ul className="grid gap-3 text-sm text-slate-700">
              {benefits.map((benefit) => (
                <li key={benefit} className="flex items-start gap-2">
                  <span className="mt-1 h-1.5 w-1.5 rounded-full bg-slate-900" />
                  <span>{benefit}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="mt-16 rounded-3xl border border-slate-200 bg-white/80 px-6 py-10 text-left shadow-sm backdrop-blur">
          <FacultySearch faculty={faculty} institution={institution} />
        </section>
      </div>
    </main>
  );
}
