import { useEffect, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { PrimaryCta } from "../components/Layout";
import { Icon, type IconName } from "../components/icons";
import { REPO_URL } from "../lib/env";
import { workspaceEnabled } from "../lib/firebase";

// --- content -------------------------------------------------------------------------

const PROOF = [
  { value: "7", label: "identity signals hidden while you screen" },
  { value: "0", label: "resume files stored, ever" },
  { value: "3", label: "signals in every score, weighted your way" },
  { value: "20", label: "PDF resumes screened per upload" },
];

const PROBLEMS = [
  {
    title: "It's slow",
    body: "Reading 50 resumes for one role takes hours, and attention fades long before the last one.",
  },
  {
    title: "It's exposed to bias",
    body: "Names, gender, age and location sway first impressions, even when nobody intends them to.",
  },
  {
    title: "Keyword filters miss people",
    body: "ATS keyword matching drops candidates who describe the same skill in different words.",
  },
];

const STEPS: { icon: IconName; title: string; body: string }[] = [
  {
    icon: "document",
    title: "Paste the job description",
    body: "FairScreen turns it into a checklist of must-have and nice-to-have requirements. You review and edit it before screening starts.",
  },
  {
    icon: "upload",
    title: "Upload up to 20 PDF resumes",
    body: "Each resume is parsed, stripped of identity details and checked against every requirement in the background, with live progress.",
  },
  {
    icon: "list",
    title: "Review a ranked, blind shortlist",
    body: "Every score comes with evidence and a short explanation. Shortlist someone to reveal who they are; each reveal is logged.",
  },
];

const FEATURES: { icon: IconName; title: string; body: string }[] = [
  {
    icon: "checkCircle",
    title: "Evidence for every verdict",
    body: "Each requirement is marked met, partial or not met, with a pointer to what in the resume supports it. No unexplained numbers.",
  },
  {
    icon: "chart",
    title: "A score computed in plain sight",
    body: "The AI judges requirements; the score is simple arithmetic you can read, reproduce and re-weight without another AI call.",
  },
  {
    icon: "eyeSlash",
    title: "Two layers of redaction",
    body: "Identity is separated when the resume is read, then a deterministic filter scrubs names, contacts, links, locations and gendered words.",
  },
  {
    icon: "lock",
    title: "A reveal gate with an audit trail",
    body: "Identity unlocks only after you shortlist a candidate, and every reveal records who opened it and when.",
  },
  {
    icon: "sliders",
    title: "Weights you control",
    body: "Decide how much must-haves, nice-to-haves and overall fit count. The ranking updates while you drag.",
  },
  {
    icon: "download",
    title: "Live progress and CSV export",
    body: "Watch each resume move from processing to scored, then export the shortlist for the rest of the hiring team.",
  },
];

const HIDDEN = ["Name", "Email and phone", "LinkedIn, GitHub and other links", "Photo", "Location and address", "Age and date of birth", "Gender, pronouns and titles"];
const VISIBLE = ["Education: college, degree, grade, year", "Employers, job titles and dates", "Skills, projects and certifications"];

interface Plan {
  name: string;
  price: string;
  unit: string;
  blurb: string;
  features: string[];
  available: boolean;
}

const PLANS: Plan[] = [
  {
    name: "Starter",
    price: "$0",
    unit: "free during early access",
    blurb: "Everything you need to screen a role blind.",
    features: [
      "Up to 50 candidates per job",
      "20 PDF resumes per upload",
      "Blind ranking with an evidence checklist",
      "Reveal gate and audit log",
      "Adjustable weights and CSV export",
    ],
    available: true,
  },
  {
    name: "Team",
    price: "$29",
    unit: "per recruiter / month",
    blurb: "For teams hiring for several roles at once.",
    features: [
      "Everything in Starter",
      "Up to 500 candidates per job",
      "Shared jobs with hiring managers",
      "AI-suggested interview questions",
      "Bias spot-check reports",
      "Paid-tier AI processing: your data isn't used to improve models",
    ],
    available: false,
  },
  {
    name: "Enterprise",
    price: "Custom",
    unit: "annual agreement",
    blurb: "For organisations with compliance needs.",
    features: ["Everything in Team", "Single sign-on (SSO)", "ATS integrations", "Data residency and a DPA", "Audit log export", "Dedicated support"],
    available: false,
  },
];

const FAQS: { q: string; a: ReactNode }[] = [
  {
    q: "Does the AI see candidates' names?",
    a: "No. When a resume is read, identity details go into a separate private record. The step that judges requirements only receives the anonymised profile, and a deterministic filter removes anything that slipped through. The number of details removed is shown on every candidate.",
  },
  {
    q: "Are resumes stored?",
    a: "No. PDFs are processed in memory and discarded. FairScreen keeps the anonymised profile, the evaluation, and, in a record only the server can read, the contact details you can reveal after shortlisting. Age, date of birth and gender are never stored.",
  },
  {
    q: "How is the score calculated?",
    a: "Must-have coverage counts for 50%, nice-to-have coverage for 20% and semantic similarity to the job for 30%, with partial matches counting half. You can change the weights per job. The AI never picks the number.",
  },
  {
    q: "Why can I see the college?",
    a: "Education is relevant to many roles, so it stays visible. But the institution is never scored: education only counts when the job asks for a degree, and then by degree and field, not by name or prestige.",
  },
  {
    q: "Does FairScreen reject candidates automatically?",
    a: "No. It ranks and explains; you decide. A missing must-have is flagged with a badge, never auto-rejected.",
  },
  {
    q: "What files can I upload?",
    a: "PDF resumes up to 5 MB each, 20 per upload and 50 per job. Scanned PDFs work as long as the text is readable.",
  },
  {
    q: "Which AI models does it use?",
    a: "Google's Gemini models through their API, with no training or fine-tuning on your data. During early access FairScreen runs on Gemini's free tier, where Google may use prompts to improve its products, so use sample or consented resumes until paid-tier processing is available.",
  },
  {
    q: "How well does the ranking work?",
    a: (
      <>
        Ranking quality is measured offline on a public resume dataset (precision at 5 and 10, and nDCG), comparing the
        combined score with each signal on its own. The method and results are{" "}
        <a href={`${REPO_URL}#evaluation`} className="font-medium text-indigo-600 hover:text-indigo-700" target="_blank" rel="noreferrer">
          published with the source code
        </a>
        .
      </>
    ),
  },
];

// --- building blocks ---------------------------------------------------------------------

function SectionHeading({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="text-sm font-semibold text-indigo-600">{eyebrow}</p>
      <h2 className="mt-2 text-3xl font-bold tracking-tight text-balance text-slate-900 sm:text-4xl">{title}</h2>
      {children && <p className="mt-4 text-base text-slate-600">{children}</p>}
    </div>
  );
}

function Container({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`mx-auto max-w-7xl px-4 sm:px-6 ${className}`}>{children}</div>;
}

const DemoLink = ({ className = "" }: { className?: string }) => (
  <Link
    to="/demo"
    className={`inline-flex items-center justify-center gap-2 rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-slate-800 shadow-sm ring-1 ring-slate-300 ring-inset hover:bg-slate-50 ${className}`}
  >
    Try the live demo <Icon name="arrowRight" className="size-4" />
  </Link>
);

/** A static picture of the ranked table, using the demo job's candidates. */
function ProductPreview() {
  const rows = [
    { anon: "CAND-3F9A", score: 89, cov: "6/6", status: "Shortlisted", tone: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
    { anon: "CAND-A71C", score: 80, cov: "4/6", status: "Shortlisted", tone: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
    { anon: "CAND-5D20", score: 65, cov: "4/6", status: "To review", tone: "bg-sky-50 text-sky-700 ring-sky-200", missing: true },
    { anon: "CAND-C0E4", score: 52, cov: "2/6", status: "To review", tone: "bg-sky-50 text-sky-700 ring-sky-200" },
  ];
  return (
    <div className="relative min-w-0" aria-hidden="true">
      <div className="absolute -inset-4 -z-10 rounded-3xl bg-gradient-to-tr from-indigo-100 via-white to-emerald-50 blur-2xl" />
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10">
        <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50 px-4 py-3">
          <span className="size-2.5 rounded-full bg-slate-300" />
          <span className="size-2.5 rounded-full bg-slate-300" />
          <span className="size-2.5 rounded-full bg-slate-300" />
          <span className="ml-3 min-w-0 truncate text-xs font-medium text-slate-500">IT Systems Administrator · ranked blind shortlist</span>
        </div>
        <div className="divide-y divide-slate-100">
          <div className="grid grid-cols-[1.5rem_6.5rem_1fr_5.5rem] sm:grid-cols-[1.5rem_6.5rem_1fr_3rem_5.5rem] items-center gap-3 px-4 py-2 text-[11px] font-medium tracking-wide text-slate-400 uppercase">
            <span>#</span>
            <span>Candidate</span>
            <span>Score</span>
            <span className="hidden sm:block">Must</span>
            <span className="text-right">Status</span>
          </div>
          {rows.map((r, i) => (
            <div key={r.anon} className="grid grid-cols-[1.5rem_6.5rem_1fr_5.5rem] sm:grid-cols-[1.5rem_6.5rem_1fr_3rem_5.5rem] items-center gap-3 px-4 py-3">
              <span className="text-sm text-slate-400 tabular-nums">{i + 1}</span>
              <span className="font-mono text-sm font-medium text-slate-900">{r.anon}</span>
              <span className="flex items-center gap-2">
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                  <span className="block h-full rounded-full bg-indigo-500" style={{ width: `${r.score}%` }} />
                </span>
                <span className="w-6 text-right text-sm font-semibold text-slate-900 tabular-nums">{r.score}</span>
              </span>
              <span className={`hidden text-sm tabular-nums sm:block ${r.missing ? "font-medium text-rose-600" : "text-slate-600"}`}>{r.cov}</span>
              <span className="text-right">
                <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${r.tone}`}>{r.status}</span>
              </span>
            </div>
          ))}
          <div className="h-14 bg-slate-50/60 px-4 py-4 text-right text-xs text-slate-400">5 candidates · 2 shortlisted · 0 names shown</div>
        </div>
      </div>
      <div className="absolute -bottom-10 -left-4 hidden w-64 rounded-xl border border-slate-200 bg-white p-3 shadow-lg sm:block">
        <p className="flex items-center gap-2 text-xs font-semibold text-slate-900">
          <Icon name="checkCircle" className="size-4 text-emerald-600" /> Windows Server and Active Directory
        </p>
        <p className="mt-1 text-xs text-slate-500">“Ran Active Directory and Group Policy for 900 users”</p>
      </div>
      <div className="absolute -top-5 -right-3 hidden items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-md sm:flex">
        <Icon name="eyeSlash" className="size-4 text-indigo-600" /> 9 identity details hidden
      </div>
    </div>
  );
}

function ScoreExample() {
  const rows = [
    { label: "Must-have", weight: 0.5, value: 1.0, note: "6 of 6 met" },
    { label: "Nice-to-have", weight: 0.2, value: 0.625, note: "2 met, 1 partial, 1 not met" },
    { label: "Semantic fit", weight: 0.3, value: 0.867, note: "similarity to the job" },
  ];
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-baseline justify-between">
        <p className="font-mono text-sm font-semibold text-slate-900">CAND-3F9A</p>
        <p className="text-3xl font-bold tracking-tight text-slate-900 tabular-nums">
          88.5<span className="text-sm font-medium text-slate-400"> / 100</span>
        </p>
      </div>
      <div className="mt-5 space-y-4">
        {rows.map((r) => (
          <div key={r.label}>
            <div className="flex justify-between text-sm">
              <span className="font-medium text-slate-700">
                {r.label} <span className="font-normal text-slate-400">× {r.weight}</span>
              </span>
              <span className="text-slate-500 tabular-nums">{Math.round(r.value * 100)}%</span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-indigo-500" style={{ width: `${r.value * 100}%` }} />
            </div>
            <p className="mt-1 text-xs text-slate-400">{r.note}</p>
          </div>
        ))}
      </div>
      <p className="mt-5 rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs text-slate-600">
        100 × (0.5 × 1.00 + 0.2 × 0.625 + 0.3 × 0.867) = 88.5
      </p>
    </div>
  );
}

// --- page ------------------------------------------------------------------------------

export function Landing() {
  const { hash } = useLocation();

  // Header and footer links point at sections ("/#pricing").
  useEffect(() => {
    if (!hash) return window.scrollTo(0, 0);
    document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [hash]);

  return (
    <div className="bg-white">
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-slate-100 bg-gradient-to-b from-indigo-50/60 to-white">
        <Container className="grid items-center gap-16 py-16 sm:py-24 lg:grid-cols-2">
          <div className="min-w-0">
            <p className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-semibold text-indigo-700 shadow-sm ring-1 ring-indigo-100">
              <span className="size-1.5 rounded-full bg-indigo-500" /> Blind resume screening for small hiring teams
            </p>
            <h1 className="mt-6 text-4xl font-bold tracking-tight text-balance text-slate-900 sm:text-6xl">Hire on skills, not on names.</h1>
            <p className="mt-6 max-w-xl text-lg text-slate-600">
              Upload a stack of PDF resumes and get a ranked, anonymised shortlist in minutes. Every score shows its evidence,
              and you only see who a candidate is once you shortlist them.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <PrimaryCta />
              {workspaceEnabled ? (
                <DemoLink />
              ) : (
                <Link
                  to={{ pathname: "/", hash: "how" }}
                  className="inline-flex items-center gap-2 px-2 py-2.5 text-sm font-semibold text-slate-700 hover:text-slate-900"
                >
                  How it works <Icon name="arrowRight" className="size-4" />
                </Link>
              )}
            </div>
            <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-500">
              {["Free during early access", "Resumes never stored", "Demo needs no sign-in"].map((x) => (
                <li key={x} className="flex items-center gap-1.5">
                  <Icon name="check" className="size-4 text-emerald-600" /> {x}
                </li>
              ))}
            </ul>
          </div>
          <ProductPreview />
        </Container>
      </section>

      {/* Proof points */}
      <section className="border-b border-slate-100">
        <Container className="grid grid-cols-2 gap-8 py-12 md:grid-cols-4">
          {PROOF.map((p) => (
            <div key={p.label} className="text-center">
              <p className="text-4xl font-bold tracking-tight text-indigo-600 tabular-nums">{p.value}</p>
              <p className="mt-1 text-sm text-slate-600">{p.label}</p>
            </div>
          ))}
        </Container>
      </section>

      {/* Problem */}
      <section className="py-20 sm:py-24">
        <Container>
          <SectionHeading eyebrow="The problem" title="Screening is where good candidates get lost">
            Small teams read every resume themselves. It's slow, it's inconsistent, and it's exposed to bias nobody intends.
          </SectionHeading>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {PROBLEMS.map((p) => (
              <div key={p.title} className="rounded-2xl border border-slate-200 bg-slate-50/60 p-6">
                <h3 className="font-semibold text-slate-900">{p.title}</h3>
                <p className="mt-2 text-sm text-slate-600">{p.body}</p>
              </div>
            ))}
          </div>
        </Container>
      </section>

      {/* How it works */}
      <section id="how" className="scroll-mt-16 bg-slate-50 py-20 sm:py-24">
        <Container>
          <SectionHeading eyebrow="How it works" title="From job description to shortlist in three steps" />
          <ol className="mt-12 grid gap-6 md:grid-cols-3">
            {STEPS.map((s, i) => (
              <li key={s.title} className="relative rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex items-center gap-3">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-indigo-600 text-white">
                    <Icon name={s.icon} />
                  </span>
                  <span className="text-sm font-semibold text-slate-400">Step {i + 1}</span>
                </div>
                <h3 className="mt-4 font-semibold text-slate-900">{s.title}</h3>
                <p className="mt-2 text-sm text-slate-600">{s.body}</p>
              </li>
            ))}
          </ol>
        </Container>
      </section>

      {/* Features */}
      <section id="features" className="scroll-mt-16 py-20 sm:py-24">
        <Container>
          <SectionHeading eyebrow="Product" title="Built for hiring decisions you can defend">
            FairScreen does the reading. You keep the judgement, with the evidence in front of you.
          </SectionHeading>
          <div className="mt-12 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex gap-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 ring-1 ring-indigo-100">
                  <Icon name={f.icon} />
                </span>
                <div>
                  <h3 className="font-semibold text-slate-900">{f.title}</h3>
                  <p className="mt-1 text-sm text-slate-600">{f.body}</p>
                </div>
              </div>
            ))}
          </div>
        </Container>
      </section>

      {/* Fairness */}
      <section id="fairness" className="scroll-mt-16 bg-slate-900 py-20 text-white sm:py-24">
        <Container className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <div>
            <p className="text-sm font-semibold text-indigo-300">Fairness</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">The blind-screening promise</h2>
            <p className="mt-4 text-slate-300">
              The scoring model only ever sees the anonymised profile. So do you, until you shortlist a candidate and choose to
              reveal them. Every reveal is logged with the time and the person who opened it.
            </p>
            <p className="mt-4 text-sm text-slate-400">
              College is visible but never scored. Education counts only when the job asks for a degree, and then by degree and
              field, not institution. Age, date of birth and gender are never stored.
            </p>
          </div>
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="rounded-2xl bg-white/5 p-6 ring-1 ring-white/10">
              <h3 className="text-sm font-semibold text-rose-300">Hidden while screening</h3>
              <ul className="mt-4 space-y-2.5 text-sm text-slate-200">
                {HIDDEN.map((x) => (
                  <li key={x} className="flex gap-2">
                    <Icon name="x" className="mt-0.5 size-4 shrink-0 text-rose-400" /> {x}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-2xl bg-white/5 p-6 ring-1 ring-white/10">
              <h3 className="text-sm font-semibold text-emerald-300">Visible</h3>
              <ul className="mt-4 space-y-2.5 text-sm text-slate-200">
                {VISIBLE.map((x) => (
                  <li key={x} className="flex gap-2">
                    <Icon name="check" className="mt-0.5 size-4 shrink-0 text-emerald-400" /> {x}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Container>
      </section>

      {/* Scoring */}
      <section id="scoring" className="scroll-mt-16 py-20 sm:py-24">
        <Container className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <div>
            <p className="text-sm font-semibold text-indigo-600">Transparent scoring</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">No black-box numbers</h2>
            <p className="mt-4 text-slate-600">
              The AI answers one narrow question per requirement: is there evidence for it? The score is then plain arithmetic, so
              the same resume always gets the same number, and you can see exactly where it came from.
            </p>
            <ul className="mt-6 space-y-3 text-sm text-slate-700">
              {[
                "Partial matches count half; missing ones count zero.",
                "Change the weights per job and the ranking updates instantly, with no new AI calls.",
                "A missing must-have is flagged, never auto-rejected. People make the call.",
              ].map((x) => (
                <li key={x} className="flex gap-2">
                  <Icon name="check" className="mt-0.5 size-4 shrink-0 text-indigo-600" /> {x}
                </li>
              ))}
            </ul>
          </div>
          <ScoreExample />
        </Container>
      </section>

      {/* Pricing */}
      <section id="pricing" className="scroll-mt-16 bg-slate-50 py-20 sm:py-24">
        <Container>
          <SectionHeading eyebrow="Pricing" title="Start free. Grow when you're ready.">
            FairScreen is in early access: the Starter plan is free while we build the paid plans below.
          </SectionHeading>
          <div className="mt-12 grid gap-6 lg:grid-cols-3">
            {PLANS.map((p) => (
              <div
                key={p.name}
                className={`flex flex-col rounded-2xl bg-white p-8 shadow-sm ${
                  p.available ? "ring-2 ring-indigo-600" : "ring-1 ring-slate-200"
                }`}
              >
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-slate-900">{p.name}</h3>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      p.available ? "bg-indigo-50 text-indigo-700" : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {p.available ? "Available now" : "Coming soon"}
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-500">{p.blurb}</p>
                <p className="mt-6">
                  <span className="text-4xl font-bold tracking-tight text-slate-900">{p.price}</span>
                  <span className="ml-2 text-sm text-slate-500">{p.unit}</span>
                </p>
                <ul className="mt-6 flex-1 space-y-3 text-sm text-slate-700">
                  {p.features.map((f) => (
                    <li key={f} className="flex gap-2">
                      <Icon name="check" className="mt-0.5 size-4 shrink-0 text-indigo-600" /> {f}
                    </li>
                  ))}
                </ul>
                <div className="mt-8">
                  {p.available ? (
                    <PrimaryCta fullWidth />
                  ) : (
                    <span className="block rounded-lg bg-slate-100 px-4 py-2.5 text-center text-sm font-medium text-slate-500">
                      Coming soon
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
          <p className="mt-8 text-center text-xs text-slate-500">
            Paid plans aren't on sale yet; prices shown are planned and may change.
          </p>
        </Container>
      </section>

      {/* FAQ */}
      <section id="faq" className="scroll-mt-16 py-20 sm:py-24">
        <Container className="max-w-3xl">
          <SectionHeading eyebrow="FAQ" title="Questions recruiters ask" />
          <div className="mt-12 divide-y divide-slate-200 rounded-2xl border border-slate-200">
            {FAQS.map((f) => (
              <details key={f.q} className="group px-6 py-5">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium text-slate-900 [&::-webkit-details-marker]:hidden">
                  {f.q}
                  <Icon name="chevronDown" className="size-5 shrink-0 text-slate-400 transition-transform group-open:rotate-180" />
                </summary>
                <div className="mt-3 text-sm leading-relaxed text-slate-600">{f.a}</div>
              </details>
            ))}
          </div>
        </Container>
      </section>

      {/* Final call to action */}
      <section className="px-4 pb-20 sm:px-6 sm:pb-24">
        <div className="mx-auto max-w-5xl rounded-3xl bg-indigo-600 px-6 py-14 text-center shadow-xl shadow-indigo-600/20 sm:px-12">
          <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">See a blind shortlist in 30 seconds</h2>
          <p className="mx-auto mt-4 max-w-xl text-indigo-100">
            Open the demo: a sample job, a ranked set of anonymised candidates, and the shortlist-then-reveal flow. No sign-in.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/demo" className="inline-flex items-center gap-2 rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-indigo-700 shadow-sm hover:bg-indigo-50">
              Open the live demo <Icon name="arrowRight" className="size-4" />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
