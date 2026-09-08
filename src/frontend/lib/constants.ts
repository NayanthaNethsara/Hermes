export const APP_NAME = "Hermes";
export const TEAM_NAME = "TheKade";
export const APP_DESCRIPTION = "Historical archive intelligence by TheKade.";

export const DEFAULT_API_URL = "http://localhost:8000";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL;

export const API_ENDPOINTS = {
  ASK: "/api/ask",
  DOCUMENTS: "/api/documents",
  VISUALS: "/api/visuals",
} as const;

export const QUERY_CONSTRAINTS = {
  MIN_LENGTH: 1,
  MAX_LENGTH: 2000,
} as const;

export const SUGGESTED_QUERIES = [
  { label: "House Morvain", query: "What is the history of House Morvain?" },
  { label: "Gauntlet of Sorrowfell", query: "What are the origins and powers of the Gauntlet of Sorrowfell?" },
  { label: "Bleeding Crown", query: "What contradictions exist regarding the Bleeding Crown?" },
  { label: "Malchior Cindervale", query: "Who was Malchior Cindervale and why was he called the Flame-Touched?" },
] as const;
