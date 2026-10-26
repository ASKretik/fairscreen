// Mirrors backend/app/models.py (SPEC §6.1) and the Firestore layout (SPEC §6.2).

export type ReqKind = "skill" | "experience" | "education" | "certification" | "other";

/** A screening tag. `weight` (1–5, default 3) is its importance within its group. */
export interface Requirement {
  id: string;
  text: string;
  kind: ReqKind;
  weight?: number;
}

export interface JobRequirements {
  role_title: string;
  must_have: Requirement[];
  nice_to_have: Requirement[];
  min_years_experience: number | null;
  education_requirement: string | null;
}

export interface Education {
  institution: string | null;
  degree: string | null;
  field: string | null;
  grade: string | null;
  start_year: number | null;
  end_year: number | null;
}

export interface Experience {
  title: string | null;
  organisation: string | null;
  start: string | null;
  end: string | null;
  months: number | null;
  summary: string;
}

export interface Project {
  title: string;
  summary: string;
}

export interface BlindProfile {
  headline: string;
  education: Education[];
  experience: Experience[];
  total_experience_months: number | null;
  skills: string[];
  projects: Project[];
  certifications: string[];
}

export type Verdict = "met" | "partial" | "not_met";

export interface RequirementVerdict {
  req_id: string;
  verdict: Verdict;
  evidence: string;
}

export interface CandidateEvaluation {
  must_have: RequirementVerdict[];
  nice_to_have: RequirementVerdict[];
  strengths: string[];
  gaps: string[];
  summary: string;
}

export interface ScoreBreakdown {
  must_have: number;
  nice_to_have: number;
  semantic: number;
  semantic_raw: number;
  total: number;
  missing_must_have: boolean;
}

export interface Weights {
  must: number;
  nice: number;
  semantic: number;
}

export interface Counts {
  total: number;
  processing: number;
  scored: number;
  failed: number;
  shortlisted: number;
}

export interface Job {
  id: string;
  ownerUid?: string;
  title: string;
  jdText: string;
  requirements: JobRequirements;
  requirementsLocked: boolean;
  weights: Weights;
  counts: Counts;
  createdAt: Date | null;
  updatedAt: Date | null;
}

export type CandidateStatus = "processing" | "scored" | "failed" | "shortlisted" | "rejected";
export type Decision = "shortlisted" | "rejected" | "scored";

export interface RevealedIdentity {
  name: string | null;
  email: string | null;
  phone: string | null;
  links: string[];
  location: string | null;
}

export interface Candidate {
  id: string;
  anonId: string;
  fileName: string; // never rendered; CSV only after reveal
  status: CandidateStatus;
  error: string | null;
  profile: BlindProfile | null;
  evaluation: CandidateEvaluation | null;
  score: ScoreBreakdown | null;
  photoPresent: boolean;
  redactionCount: number;
  revealed: RevealedIdentity | null;
  revealedAt: Date | null;
  revealedBy: string | null;
  createdAt: Date | null;
  updatedAt: Date | null;
  /** Demo only: the resume's dataset category, shown so viewers can judge the ranking. */
  label?: string | null;
}

export interface RevealResult {
  identity: RevealedIdentity;
  revealedAt: Date | null;
  revealedBy: string | null;
}

/** Actions a workspace can perform. Live mode calls the API; demo mode edits local state. */
export interface WorkspaceActions {
  setStatus(candidateId: string, status: Decision): Promise<void>;
  reveal(candidateId: string): Promise<RevealResult>;
  upload?(files: File[]): Promise<string[]>;
  /** Retry is possible only from the tab that uploaded the PDF, which still holds the file. */
  canRetry?(candidateId: string): boolean;
  retry?(candidateId: string): Promise<void>;
  saveRequirements?(requirements: JobRequirements): Promise<void>;
  /** Group weights plus tag weights by requirement ID. */
  saveWeights?(weights: Weights, tagWeights: Record<string, number>): Promise<void>;
  deleteJob?(): Promise<void>;
}
