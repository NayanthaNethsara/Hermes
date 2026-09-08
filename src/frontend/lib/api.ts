import type {
  ArchivistResponse,
  DocumentDetails,
  VisualCatalogItem,
} from "@/types/archivist";

const DEFAULT_API_URL = "http://localhost:8000";

function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL;
}

export class ArchivistApiError extends Error {}

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

export async function fetchDocumentDetails(docId: string): Promise<DocumentDetails> {
  const cleanId = docId.replace(/^\d+$/, "").trim() || docId;
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/api/documents/${cleanId}`);
  } catch {
    throw new ArchivistApiError(`Could not reach backend to load document ${cleanId}`);
  }

  if (!response.ok) {
    throw new ArchivistApiError(`Document '${cleanId}' could not be loaded.`);
  }

  return response.json();
}

export async function fetchVisualDetails(filename: string): Promise<VisualCatalogItem> {
  const cleanName = filename.split("/").pop() || filename;
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/api/visuals/${cleanName}`);
  } catch {
    throw new ArchivistApiError(`Could not reach backend to load visual asset ${cleanName}`);
  }

  if (!response.ok) {
    throw new ArchivistApiError(`Visual asset '${cleanName}' could not be loaded.`);
  }

  return response.json();
}
