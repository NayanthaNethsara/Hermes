import type {
  HermesResponse,
  DocumentDetails,
  VisualCatalogItem,
} from "@/types/hermes";
import {
  AskQuerySchema,
  DocumentIdSchema,
  VisualFilenameSchema,
} from "@/lib/validation";
import { API_BASE_URL, API_ENDPOINTS } from "@/lib/constants";
export class HermesApiError extends Error {}


export async function askHermes(question: string): Promise<HermesResponse> {
  const validated = AskQuerySchema.parse({ question });

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.ASK}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: validated.question }),
    });
  } catch {
    throw new HermesApiError(
      `Could not reach the backend. Is it running at ${API_BASE_URL}?`
    );
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const message =
      data && typeof data.error === "string"
        ? data.error
        : `Request failed with status ${response.status}`;
    throw new HermesApiError(message);
  }

  return data as HermesResponse;
}

export async function fetchDocumentDetails(docId: string): Promise<DocumentDetails> {
  const cleanId = docId.replace(/^\d+$/, "").trim() || docId;
  const validatedId = DocumentIdSchema.parse(cleanId);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${API_ENDPOINTS.DOCUMENTS}/${validatedId}`);
  } catch {
    throw new HermesApiError(`Could not reach backend to load document ${validatedId}`);
  }

  if (!response.ok) {
    throw new HermesApiError(`Document '${validatedId}' could not be loaded.`);
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
    throw new HermesApiError(`Visual asset '${validatedName}' could not be loaded.`);
  }

  return response.json();
}
