// TEMPORARY MOCK DATA — delete this folder once the real backend is connected,
// see docs/architecture.md section 6 for the real API contract this mock data matches.

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

// Matches the exact API contract shape from docs/architecture.md section 6.
export interface ArchivistResponse {
  answer: string;
  reasoning_steps: ReasoningStep[];
  sources: Source[];
  contradictions: Contradiction[];
}

export interface MockExchange {
  question: string;
  response: ArchivistResponse;
}

export const MOCK_EXCHANGES: MockExchange[] = [
  {
    question: "Who repaired the artifact known as the Ember Clock?",
    response: {
      answer:
        "The sources disagree on who repaired the Ember Clock. The Codex records that it was restored by the Ember Wardens' chief artificer, Renn Duvel, during the Third Reclamation. A separate account in the Tavern Ballads instead credits a wandering tinker known only as \"the Grey Hand.\" Because these accounts conflict and cannot both be literally true, this answer surfaces the disagreement rather than picking a side.",
      reasoning_steps: [
        { step: 1, action: "Searched: 'Ember Clock repair'", found: "3 relevant chunks" },
        { step: 2, action: "Not enough info, searched: 'Ember Wardens artificer'", found: "2 relevant chunks" },
      ],
      sources: [
        { title: "Codex Vol. 2, p.114", trust: "high", snippet: "Renn Duvel, chief artificer of the Ember Wardens, restored the Ember Clock's inner gears after the Third Reclamation." },
        { title: "Tavern Ballad #7", trust: "low", snippet: "...and the Grey Hand set the frozen clock to ticking once more, asking no coin for the deed..." },
      ],
      contradictions: [
        { topic: "Who repaired the Ember Clock", sources_disagree: ["Codex Vol. 2", "Tavern Ballad #7"] },
      ],
    },
  },
  {
    question: "What caused the fall of the Ashen Sovereign?",
    response: {
      answer:
        "The Ashen Sovereign's fall is attributed to the collapse of the Cinder Wall during the siege of Marrow Keep, which let the Hollow Legion advance unopposed into the capital. The Codex frames this as a military failure; the Archive Wiki adds that the wall's collapse followed years of neglected upkeep after treasury funds were redirected to the Sovereign's private guard.",
      reasoning_steps: [
        { step: 1, action: "Searched: 'fall of the Ashen Sovereign'", found: "4 relevant chunks" },
        { step: 2, action: "Searched: 'Cinder Wall collapse cause'", found: "2 relevant chunks" },
        { step: 3, action: "Not enough info, searched: 'Hollow Legion siege Marrow Keep'", found: "3 relevant chunks" },
      ],
      sources: [
        { title: "Codex Vol. 4, p.9", trust: "high", snippet: "With the Cinder Wall breached, the Hollow Legion met no further resistance before the gates of the capital." },
        { title: "Archive Wiki: Cinder Wall", trust: "medium", snippet: "Maintenance records show funding for the Wall's upkeep was diverted for a decade prior to its collapse." },
        { title: "Marrow Keep, a novel by Iseult Farrow", trust: "medium-low", snippet: "The wall groaned like a dying beast, and none who watched believed it would hold another season." },
      ],
      contradictions: [],
    },
  },
  {
    question: "Which factions signed the Cinder Accord?",
    response: {
      answer:
        "The Cinder Accord was signed by three factions: the Ember Wardens, the Marrow Keep remnant council, and the Hollow Legion's negotiating envoy. The Codex lists all three signatories directly on the treaty's preserved text.",
      reasoning_steps: [
        { step: 1, action: "Searched: 'Cinder Accord signatories'", found: "2 relevant chunks" },
      ],
      sources: [
        { title: "Codex Vol. 5, p.201", trust: "high", snippet: "Signed this day by the Ember Wardens, the Marrow Keep remnant council, and the envoy of the Hollow Legion." },
      ],
      contradictions: [],
    },
  },
];
