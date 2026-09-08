"use client";

import { useState } from "react";
import { BookOpen, ChevronDown, ChevronUp, Scale } from "lucide-react";
import type { Contradiction, Source } from "@/types/hermes";

interface ContradictionBannerProps {
  contradictions: Contradiction[];
  sources?: Source[];
  onSelectDocument?: (docId: string) => void;
}

function formatDocumentTitle(docId: string): string {
  let cleaned = docId
    .replace(/^atmo_relic_artifact_/, "")
    .replace(/^plate_\d+_/, "")
    .replace(/^atmo_[a-z]+_[a-z]+_/, "")
    .replace(/^atmo_[a-z]+_/, "")
    .replace(/\.(png|pdf|docx|txt|scan)$/i, "");

  cleaned = cleaned
    .replace(/volume_i\b/gi, "Vol. I")
    .replace(/volume_ii\b/gi, "Vol. II")
    .replace(/volume_iii\b/gi, "Vol. III")
    .replace(/volume_iv\b/gi, "Vol. IV");

  const words = cleaned.split("_");
  return words
    .map((word, idx) => {
      const lower = word.toLowerCase();
      if (idx > 0 && ["the", "of", "and", "in", "for", "concerning", "at"].includes(lower)) {
        return lower;
      }
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");
}

function resolveCategory(docId: string, matchingSource?: Source): string {
  const cat = (
    matchingSource?.category ||
    (docId.includes("artifact") || docId.includes("plate")
      ? "Illustration"
      : docId.includes("chronicles")
        ? "Novel"
        : docId.includes("codex")
          ? "Codex"
          : "Ephemera")
  ).toLowerCase();

  if (cat === "image" || cat === "illustration") return "Illustration (Canon)";
  if (cat === "codex") return "Codex (Canon)";
  if (cat === "wiki") return "Wiki (Consensus)";
  if (cat === "novel") return "Chronicle (Narrative)";
  return "Ephemera";
}

export function ContradictionBanner({
  contradictions,
  sources = [],
  onSelectDocument,
}: ContradictionBannerProps) {
  const [showDetails, setShowDetails] = useState(false);

  if (!contradictions || contradictions.length === 0) {
    return null;
  }

  const uniqueContradictions = contradictions.filter(
    (item, index, self) =>
      index ===
      self.findIndex(
        (target) => target.topic.trim().toLowerCase() === item.topic.trim().toLowerCase()
      )
  );

  return (
    <div className="my-2 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2 text-[12px] text-[#a1a1aa] space-y-1.5">
      {uniqueContradictions.map((item, index) => {
        const sourceTitles = item.sources_disagree.map((rawDocId) => {
          const docId = rawDocId.split("|")[0].trim();
          const matched = sources.find(
            (s) => s.title === docId || s.title.includes(docId) || docId.includes(s.title)
          );
          return {
            docId,
            title: formatDocumentTitle(docId),
            category: resolveCategory(docId, matched),
          };
        });

        return (
          <div key={`${item.topic}-${index}`} className="space-y-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-[#d4d4d8]">
                <Scale className="h-3.5 w-3.5 text-[#71717a] shrink-0" />
                <span className="font-medium text-[#ededed]">Archival Discrepancy:</span>
                <span className="text-[#a1a1aa]">{item.topic}</span>
              </div>
              <button
                type="button"
                onClick={() => setShowDetails(!showDetails)}
                className="inline-flex items-center gap-1 text-[11px] text-[#71717a] hover:text-white transition-colors cursor-pointer"
              >
                <span>{showDetails ? "Hide" : "Sources"}</span>
                {showDetails ? (
                  <ChevronUp className="h-3 w-3" />
                ) : (
                  <ChevronDown className="h-3 w-3" />
                )}
              </button>
            </div>

            {showDetails && (
              <div className="pt-1.5 border-t border-white/5 space-y-1">
                <p className="text-[11px] text-[#71717a]">
                  Conflicting accounts in archive records (the synthesis above prioritizes canonical sources):
                </p>
                <div className="flex flex-wrap gap-2 pt-0.5">
                  {sourceTitles.map((src) => (
                    <div
                      key={src.docId}
                      className="inline-flex items-center gap-1.5 rounded bg-white/5 px-2 py-0.5 text-[11px] text-[#d4d4d8]"
                    >
                      <span>{src.title}</span>
                      <span className="text-[10px] text-[#71717a]">({src.category})</span>
                      {onSelectDocument && (
                        <button
                          type="button"
                          onClick={() => onSelectDocument(src.docId)}
                          className="text-white/60 hover:text-white transition-colors ml-0.5 cursor-pointer"
                          title="Inspect document"
                        >
                          <BookOpen className="h-2.5 w-2.5" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
