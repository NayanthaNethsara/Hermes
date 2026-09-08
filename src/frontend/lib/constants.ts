export const APP_NAME = "Hermes";
export const TEAM_NAME = "TheKade";
export const APP_DESCRIPTION = "Historical archive intelligence by TheKade.";

export const DEFAULT_API_URL = "http://localhost:8000";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL;

export const API_ENDPOINTS = {
  ASK: "/api/ask",
  ASK_STREAM: "/api/ask/stream",
  DOCUMENTS: "/api/documents",
  VISUALS: "/api/visuals",
  SESSIONS: "/api/sessions",
} as const;

export const QUERY_CONSTRAINTS = {
  MIN_LENGTH: 1,
  MAX_LENGTH: 2000,
} as const;

export const SUGGESTED_QUERIES = [
  {
    label: "Gauntlet of Sorrowfell",
    query: "What motif is engraved on Gauntlet of Sorrowfell in its official illustration?",
  },
  {
    label: "House Morvain Banner",
    query: "What is the central emblem on the banner of House Morvain?",
  },
  {
    label: "Weeping Lurker Threat",
    query: "According to the official threat-classification plate, what numerical rating is assigned to the creature known as the Weeping Lurker?",
  },
  {
    label: "Greyfell Citadel Garrison",
    query: "According to the figure plate, what is the recorded garrison strength of Greyfell Citadel?",
  },
  {
    label: "Ignatz Ashgrove Portrait",
    query: "In the portrait of Ignatz Ashgrove the Oathless, what object are they holding?",
  },
  {
    label: "Emberdeep Garrison",
    query: "According to the figure plate illustrating Emberdeep’s forces, what is the recorded total of its garrison strength?",
  },
] as const;
