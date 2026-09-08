import type {
  HermesResponse,
  DocumentDetails,
  VisualCatalogItem,
  Source,
  ReasoningStep,
  Contradiction,
  StreamStatusPayload,
  StreamMetadataPayload,
  StreamDonePayload,
  SessionSummary,
  SessionDetails,
  SearchResponse,
  SearchResultChunk,
  ArchiveDocument,
} from "@/types/hermes";
import {
  AskQuerySchema,
  ArchiveSearchSchema,
  DocumentIdSchema,
  VisualFilenameSchema,
} from "@/lib/validation";
import {
  API_BASE_URL,
  API_ENDPOINTS,
  LIBRARY_SEARCH_LIMITS,
} from "@/lib/constants";
export class HermesApiError extends Error {}


export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function describeErrorBody(body: unknown, fallback: string): string {
  if (body && typeof body === "object") {
    const { message, error } = body as { message?: unknown; error?: unknown };
    if (typeof message === "string" && message.trim()) return message;
    if (typeof error === "string" && error.trim()) return error;
  }
  return fallback;
}

export interface StreamHandlers {
  onStatus?: (status: StreamStatusPayload) => void;
  onMetadata?: (metadata: StreamMetadataPayload) => void;
  onToken?: (delta: string) => void;
  onDone?: (payload: StreamDonePayload) => void;
  onError?: (error: Error) => void;
}

export async function askHermes(
  question: string,
  sessionId?: string
): Promise<HermesResponse> {
  const validated = AskQuerySchema.parse({ question, sessionId });

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.ASK}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: validated.question,
        session_id: sessionId || "default",
      }),
    });
  } catch {
    throw new HermesApiError(
      `Could not reach the backend. Is it running at ${API_BASE_URL}?`
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new HermesApiError(
      describeErrorBody(data, `Request failed with status ${response.status}`)
    );
  }

  return data as HermesResponse;
}

export async function askHermesStream(
  question: string,
  handlers: StreamHandlers,
  sessionId?: string,
  signal?: AbortSignal
): Promise<HermesResponse> {
  const validated = AskQuerySchema.parse({ question, sessionId });

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.ASK_STREAM}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: validated.question,
        session_id: sessionId || "default",
      }),
      signal,
    });
  } catch (err: unknown) {
    if (isAbortError(err)) {
      throw err;
    }

    const message = err instanceof Error ? err.message : "Network error";
    throw new HermesApiError(
      `Could not reach the backend. Is it running at ${API_BASE_URL}? (${message})`
    );
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new HermesApiError(
      describeErrorBody(data, `Request failed with status ${response.status}`)
    );
  }

  if (!response.body) {
    throw new HermesApiError("Response body is not readable for streaming.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  let accumulatedAnswer = "";
  let sources: Source[] = [];
  let referencedFigures: string[] = [];
  let citations: string[] = [];
  let reasoningSteps: ReasoningStep[] = [];
  let contradictions: Contradiction[] = [];

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const eventBlock of events) {
        if (!eventBlock.trim()) continue;

        let eventType = "message";
        let dataStr = "";

        const lines = eventBlock.split("\n");
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            dataStr = line.slice(6).trim();
          }
        }

        if (!dataStr) continue;

        try {
          const parsedData = JSON.parse(dataStr);

          switch (eventType) {
            case "status":
              handlers.onStatus?.(parsedData as StreamStatusPayload);
              break;

            case "metadata": {
              const meta = parsedData as StreamMetadataPayload;
              sources = meta.sources || [];
              referencedFigures = meta.referenced_figures || [];
              citations = meta.citations || [];
              reasoningSteps = meta.reasoning_steps || [];
              handlers.onMetadata?.(meta);
              break;
            }

            case "token": {
              const delta = typeof parsedData.delta === "string" ? parsedData.delta : "";
              accumulatedAnswer += delta;
              handlers.onToken?.(delta);
              break;
            }

            case "done": {
              const donePayload = parsedData as StreamDonePayload;
              if (donePayload.answer) accumulatedAnswer = donePayload.answer;
              if (donePayload.sources) sources = donePayload.sources;
              if (donePayload.referenced_figures) referencedFigures = donePayload.referenced_figures;
              if (donePayload.citations) citations = donePayload.citations;
              if (donePayload.reasoning_steps) reasoningSteps = donePayload.reasoning_steps;
              if (donePayload.contradictions) contradictions = donePayload.contradictions;

              handlers.onDone?.(donePayload);
              break;
            }

            case "error": {
              const errorMsg = parsedData.error || "Streaming error";
              const err = new HermesApiError(errorMsg);
              handlers.onError?.(err);
              throw err;
            }
          }
        } catch (jsonErr) {
          if (jsonErr instanceof HermesApiError) throw jsonErr;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  return {
    answer: accumulatedAnswer,
    reasoning_steps: reasoningSteps,
    sources,
    contradictions,
    referenced_figures: referencedFigures,
    citations,
  };
}

export async function fetchDocumentDetails(docId: string): Promise<DocumentDetails> {
  const cleanId = docId.split("|")[0].trim().replace(/^\d+$/, "").trim() || docId;
  const validatedId = DocumentIdSchema.parse(cleanId);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.DOCUMENTS}/${validatedId}`);
  } catch {
    throw new HermesApiError(`Could not reach backend to load document ${validatedId}`);
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new HermesApiError(
      describeErrorBody(data, `Document '${validatedId}' could not be loaded.`)
    );
  }

  return response.json();
}

export async function fetchVisualDetails(filename: string): Promise<VisualCatalogItem> {
  const cleanName = filename.split("/").pop() || filename;
  const validatedName = VisualFilenameSchema.parse(cleanName);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.VISUALS}/${validatedName}`);
  } catch {
    throw new HermesApiError(`Could not reach backend to load visual asset ${validatedName}`);
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new HermesApiError(
      describeErrorBody(data, `Visual asset '${validatedName}' could not be loaded.`)
    );
  }

  return response.json();
}

export async function searchArchive(
  query: string,
  signal?: AbortSignal
): Promise<SearchResponse> {
  const validated = ArchiveSearchSchema.parse({ query });

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.SEARCH}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: validated.query,
        top_k: LIBRARY_SEARCH_LIMITS.TOP_K,
        rerank_top_k: LIBRARY_SEARCH_LIMITS.RERANK_TOP_K,
        min_score: LIBRARY_SEARCH_LIMITS.MIN_SCORE,
      }),
      signal,
    });
  } catch (err) {
    if (isAbortError(err)) throw err;
    throw new HermesApiError(
      `Could not reach the backend. Is it running at ${API_BASE_URL}?`
    );
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new HermesApiError(
      describeErrorBody(data, `Search failed with status ${response.status}`)
    );
  }

  return response.json();
}

export function groupChunksIntoDocuments(
  chunks: SearchResultChunk[]
): ArchiveDocument[] {
  const documents = new Map<string, ArchiveDocument>();

  for (const chunk of chunks) {
    const metadata = chunk.metadata_payload || {};
    const existing = documents.get(chunk.doc_id);

    if (!existing) {
      documents.set(chunk.doc_id, {
        doc_id: chunk.doc_id,
        category: String(metadata.source_category || "unknown"),
        epistemic_weight:
          typeof metadata.epistemic_weight === "number"
            ? metadata.epistemic_weight
            : null,
        section:
          typeof metadata.section_title === "string"
            ? metadata.section_title
            : null,
        excerpt: chunk.content,
        figures: [...chunk.figure_references],
        chunk_count: 1,
        best_relevance: chunk.relevance_score,
      });
      continue;
    }

    existing.chunk_count += 1;
    for (const figure of chunk.figure_references) {
      if (!existing.figures.includes(figure)) existing.figures.push(figure);
    }
    if (chunk.relevance_score > existing.best_relevance) {
      existing.best_relevance = chunk.relevance_score;
      existing.excerpt = chunk.content;
    }
  }

  return [...documents.values()].sort(
    (a, b) => b.best_relevance - a.best_relevance
  );
}

export async function fetchSessions(): Promise<SessionSummary[]> {
  try {
    const response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.SESSIONS}`);
    if (!response.ok) return [];
    return await response.json();
  } catch {
    return [];
  }
}

export async function fetchSessionDetails(sessionId: string): Promise<SessionDetails | null> {
  try {
    const response = await fetch(
      `${API_BASE_URL}${API_ENDPOINTS.SESSIONS}/${encodeURIComponent(sessionId)}`
    );
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export async function deleteSession(sessionId: string): Promise<boolean> {
  try {
    const response = await fetch(
      `${API_BASE_URL}${API_ENDPOINTS.SESSIONS}/${encodeURIComponent(sessionId)}`,
      {
        method: "DELETE",
      }
    );
    return response.ok;
  } catch {
    return false;
  }
}
