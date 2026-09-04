// The response shape returned by POST /api/ask on the FastAPI backend.
// Matches the API contract in docs/architecture.md section 6 exactly —
// do not change this shape without updating that doc first.

export type TrustTier = "high" | "medium" | "medium-low" | "low";

export interface ReasoningStep {
  step: number;
  action: string;
  found: string;
}

export interface Source {
  title: string;
  trust: TrustTier;
  snippet: string;
}

export interface Contradiction {
  topic: string;
  sources_disagree: string[];
}

export interface ArchivistResponse {
  answer: string;
  reasoning_steps: ReasoningStep[];
  sources: Source[];
  contradictions: Contradiction[];
}
