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
  category?: string;
  epistemic_weight?: number;
  vector_score?: number | null;
  keyword_score?: number | null;
  relevance_score?: number;
  figures?: string[];
  section?: string;
}

export interface Contradiction {
  topic: string;
  sources_disagree: string[];
}

export interface HermesResponse {
  answer: string;
  reasoning_steps: ReasoningStep[];
  sources: Source[];
  contradictions: Contradiction[];
  referenced_figures?: string[];
  citations?: string[];
}


export interface DocumentChunk {
  chunk_id: string;
  section_title: string;
  content: string;
  figures: string[];
  tables: string[];
}

export interface DocumentDetails {
  doc_id: string;
  source_category: string;
  epistemic_weight: number;
  total_chunks: number;
  chunks: DocumentChunk[];
}

export interface VisualCatalogItem {
  title: string;
  extracted_text: string;
  visual_description: string;
  attributes: Record<string, unknown>;
  asset_path: string;
  rich_content?: string;
}

export interface ChatTurn {
  question: string;
  response: HermesResponse | null;
}

export interface AskQueryPayload {
  question: string;
}

export interface ChatInputBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}
