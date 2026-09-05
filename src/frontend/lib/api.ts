import type { ArchivistResponse } from "@/types/archivist";

// Falls back to the FastAPI backend's default local port only for
// zero-config local dev — the base URL always comes from
// NEXT_PUBLIC_API_URL when it's set (see .env.local.example).
const DEFAULT_API_URL = "http://localhost:8000";

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL;
}

export class ArchivistApiError extends Error {}

/** Call the backend's POST /api/ask with `question` and return its response. */
export async function askArchivist(question: string): Promise<ArchivistResponse> {
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new ArchivistApiError(
      "Could not reach the backend. Is it running at " + getApiBaseUrl() + "?"
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const message =
      data && typeof data.error === "string"
        ? data.error
        : `Request failed with status ${response.status}`;
    throw new ArchivistApiError(message);
  }

  return data as ArchivistResponse;
}
