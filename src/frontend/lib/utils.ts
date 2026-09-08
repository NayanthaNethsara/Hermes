import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function cleanWikilinks(text: string): string {
  if (!text) return "";
  return text.replace(/\[\[(.*?)\]\]/g, "$1");
}

export const CITATION_LINK_PREFIX = "#hermes-source-";

export function linkifyCitations(text: string, knownDocIds: string[]): string {
  if (!text || knownDocIds.length === 0) return text;

  return text.replace(
    /(!?)\[([^\]\n]+)\](\()?/g,
    (match, imagePrefix: string, label: string, linkSuffix: string) => {
      if (imagePrefix || linkSuffix) return match;
      const docId = label.trim();
      return knownDocIds.includes(docId)
        ? `[${docId}](${CITATION_LINK_PREFIX}${docId})`
        : match;
    }
  );
}
